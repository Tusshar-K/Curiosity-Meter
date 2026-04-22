import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.db.session import get_db
from app.schemas.domain import AssessmentRequest, SubmitQuestionResponse, SubmitQuestionScores, SubmitQuestionSessionStats
from app.services.db_service import db_service
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/submit-question", response_model=SubmitQuestionResponse)
async def submit_question(req: AssessmentRequest, db: Session = Depends(get_db)):
    if not req.question_text.strip():
        raise HTTPException(status_code=400, detail="question_text must not be empty")

    # 1. Load session state from Redis.
    session_state = await db_service.get_session_state(req.session_id or str(req.test_id)) 
    # Use full UUID lookup
    try:
        session = db_service.get_or_create_student_session(
            db=db,
            test_id=req.test_id,
            session_id=req.session_id,
            student_name=req.student_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_id_str = str(session.id)
    session_state["session_id"] = session_id_str

    # 2. Load question history
    history = await db_service.get_session_history(session_id_str) if hasattr(db_service, 'get_session_history') else []
    # Actually, we should just query DB for previous questions if needed by deduplication,
    # but the deduplication service takes a list of dicts: {"q": "text"}.
    # Let's get it from DB.
    from app.db.models import Question
    past_questions = db.query(Question).filter(Question.session_id == session.id).order_by(Question.created_at.asc()).all()
    history_for_dedup = [{"q": q.question_text} for q in past_questions]

    # 3. Run deduplication
    intent = await llm_service.classify_duplicate(history_for_dedup, req.question_text)
    if intent == "DUPLICATE":
        # Write question record
        db_service.save_question(
            db=db,
            session_id=session_id_str,
            student_id=str(session.student_id),
            question_text=req.question_text,
            dedup_status="duplicate",
            relevance_r=0.0,
            bloom_b=0,
            depth_d=0,
            bridging_bonus=0,
            composite_score=0.0,
            current_topic="Duplicate",
            feedback_text=("This looks like a duplicate question. "
                           "Try asking something new or taking a different angle!"),
            scaffold_strategy="duplicate",
            scaffold_parameters=[],
            chain_of_thought={},
        )
        return SubmitQuestionResponse(
            feedback="This looks like a duplicate question. Try asking something new or taking a different angle!",
            scores=SubmitQuestionScores(relevance_r=0, bloom_b=0, depth_d=0, bridging_bonus=0, composite_score=0),
            scaffold_strategy="duplicate",
            session_stats=SubmitQuestionSessionStats(
                question_count=session_state.get("question_count", 0),
                bridging_bonus_total=session_state.get("bridging_bonus_total", 0),
                same_topic_streak=session_state.get("same_topic_streak", 0),
                is_deepening=session_state.get("is_deepening", False)
            )
        )

    dedup_status = intent.lower()

    # 4. Build enriched query
    params = session_state.get("previous_scaffold", {}).get("parameters", [])
    if params:
        enriched_query = f"{req.question_text} [context: {' '.join(params)}]"
    else:
        enriched_query = req.question_text
    
    # 5. Retrieve top 3 chunks
    q_vector = await llm_service.embed_text(enriched_query)
    
    from app.db.models import TestMaterial
    material = db.query(TestMaterial).filter(TestMaterial.test_id == session.test_id).first()
    if not material:
        raise HTTPException(status_code=400, detail="Test material not found")
        
    contexts = await db_service.search_vectors(
        content_hash=material.content_hash,
        query_vector=q_vector,
        question_text=enriched_query,
        top_k=3,
    )

    # 6. SKIP_BRIDGING_BONUS
    skip_bridging_bonus = (dedup_status == "escalation")

    # 7. Build slim session state object for LLM
    slim_session_state = {
        "current_topic": session_state.get("current_topic", ""),
        "same_topic_streak": session_state.get("same_topic_streak", 0),
        "is_deepening": session_state.get("is_deepening", False),
        "previous_scaffold": session_state.get("previous_scaffold", {"strategy": "", "parameters": []}),
        "previous_bloom": session_state.get("previous_bloom", 0),
        "previous_depth": session_state.get("previous_depth", 0)
    }

    # 8 & 9 inside llm_service.evaluate_question (fallback & validation)
    evaluator_output = await llm_service.evaluate_question(
        question=req.question_text,
        contexts=contexts,
        session_state_json=json.dumps(slim_session_state),
        skip_bridging_bonus=skip_bridging_bonus,
    )

    scores_out = evaluator_output.get("scores", {})
    relevance_r = float(scores_out.get("relevance_r", 0.5))
    bloom_b = int(scores_out.get("bloom_b", 1))
    depth_d = int(scores_out.get("depth_d", 1))
    bridging_bonus = int(scores_out.get("bridging_bonus", 0))

    if skip_bridging_bonus:
        bridging_bonus = 0
    
    # 11. Compute composite_score
    composite_score = round(
        (
            (relevance_r * 0.35) +
            ((bloom_b / 6) * 0.40) +
            ((depth_d / 4) * 0.25) 
            #(bridging_bonus * 0.10)
        ) * 10,
        2
    )

    scaffold = evaluator_output.get("scaffold_assigned", {})
    strategy = scaffold.get("strategy", "constraint_scaffolding")
    parameters = scaffold.get("parameters", [])
    cot = evaluator_output.get("chain_of_thought", {})
    feedback = evaluator_output.get("feedback", "Excellent thinking.")
    current_topic = evaluator_output.get("current_topic", "General Topic")[:60]

    # 12. Write question record
    db_service.save_question(
        db=db,
        session_id=session_id_str,
        student_id=str(session.student_id),
        question_text=req.question_text,
        dedup_status=dedup_status,
        relevance_r=relevance_r,
        bloom_b=bloom_b,
        depth_d=depth_d,
        bridging_bonus=bridging_bonus,
        composite_score=composite_score,
        current_topic=current_topic,
        feedback_text=feedback,
        scaffold_strategy=strategy,
        scaffold_parameters=parameters,
        chain_of_thought=cot,
    )

    db_service.update_session_scores(db, session_id_str)

    # 13. Update Redis session state (Section 2B logic)
    prev_topic = session_state.get("current_topic", "")
    if current_topic == prev_topic and prev_topic:
        session_state["same_topic_streak"] = session_state.get("same_topic_streak", 1) + 1
    else:
        session_state["same_topic_streak"] = 1
        session_state["current_topic"] = current_topic
    
    prev_b = session_state.get("previous_bloom", 0)
    prev_d = session_state.get("previous_depth", 0)
    
    # True if B > prev B OR D > prev D
    session_state["is_deepening"] = (bloom_b > prev_b) or (depth_d > prev_d)
    
    session_state["previous_bloom"] = bloom_b
    session_state["previous_depth"] = depth_d
    session_state["previous_scaffold"] = {"strategy": strategy, "parameters": parameters}
    
    if bridging_bonus == 1:
        session_state["bridging_bonus_total"] = session_state.get("bridging_bonus_total", 0) + 1
    
    session_state["question_count"] = session_state.get("question_count", 0) + 1

    await db_service.update_session_state(session_id_str, session_state)

    # 14. Return response
    return SubmitQuestionResponse(
        feedback=feedback,
        scores=SubmitQuestionScores(
            relevance_r=relevance_r,
            bloom_b=bloom_b,
            depth_d=depth_d,
            bridging_bonus=bridging_bonus,
            composite_score=composite_score
        ),
        scaffold_strategy=strategy,
        session_stats=SubmitQuestionSessionStats(
            question_count=session_state["question_count"],
            bridging_bonus_total=session_state.get("bridging_bonus_total", 0),
            same_topic_streak=session_state["same_topic_streak"],
            is_deepening=session_state["is_deepening"]
        )
    )

@router.post("/evaluate")
async def evaluate_question_stream(req: AssessmentRequest, db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail="The SSE evaluate endpoint is deprecated. Use POST /submit-question instead.")
