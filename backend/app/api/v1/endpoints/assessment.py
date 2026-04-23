import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Question, TestMaterial
from app.db.session import get_db
from app.schemas.domain import (
    AssessmentRequest,
    SubmitQuestionResponse,
    SubmitQuestionScores,
    SubmitQuestionSessionStats,
)
from app.services.classifier import classify_duplicate
from app.services.db_service import db_service
from app.services.evaluator import call_evaluator

logger = logging.getLogger(__name__)
router = APIRouter()


def update_give_up_availability(state: dict) -> dict:
    """
    Recomputes give_up_available after every scored submission (Part 5B).
    Must be called as the final step of the Redis state update.
    """
    # Decrement cooldown if active
    if state["give_up_cooldown_questions"] > 0:
        state["give_up_cooldown_questions"] -= 1

    # Locked until question 3
    if state["question_count"] < 3:
        state["give_up_available"] = False
        return state

    # Available when: cooldown expired, uses remain, past question 3
    state["give_up_available"] = (
        state["give_up_cooldown_questions"] == 0
        and state["give_up_uses_remaining"] > 0
    )
    return state


@router.post("/submit-question", response_model=SubmitQuestionResponse)
async def submit_question(req: AssessmentRequest, db: Session = Depends(get_db)):
    if not req.question_text.strip():
        raise HTTPException(status_code=400, detail="question_text must not be empty")

    # ── 1. Resolve session from DB ────────────────────────────────────────
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
    test_id_str = str(session.test_id)

    # ── 2. Load Redis session state ───────────────────────────────────────
    question_budget = getattr(session, "question_budget", 20) or 20
    session_state = await db_service.get_session_state(
        test_id=test_id_str,
        session_id=session_id_str,
        question_budget=question_budget,
    )
    session_state["session_id"] = session_id_str

    # ── 3. Load question history for deduplication ────────────────────────
    past_questions = (
        db.query(Question)
        .filter(
            Question.session_id == session.id,
            Question.dedup_status != "duplicate",
        )
        .order_by(Question.created_at.asc())
        .all()
    )
    history_for_dedup = [{"q": q.question_text} for q in past_questions]

    # ── 4. Deduplication (Part 4) ─────────────────────────────────────────
    intent = await classify_duplicate(history_for_dedup, req.question_text)
    logger.info("Dedup result: %s | session=%s", intent, session_id_str)

    if intent == "DUPLICATE":
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
            feedback_text=(
                "This looks like a duplicate question. "
                "Try asking something new or taking a different angle!"
            ),
            scaffold_strategy="duplicate",
            scaffold_parameters=[],
            chain_of_thought={},
            post_nudge=False,
        )
        return SubmitQuestionResponse(
            feedback="This looks like a duplicate question. Try asking something new or taking a different angle!",
            scores=SubmitQuestionScores(
                relevance_r=0, bloom_b=0, depth_d=0, bridging_bonus=0, composite_score=0
            ),
            scaffold_strategy="duplicate",
            session_stats=SubmitQuestionSessionStats(
                question_count=session_state.get("question_count", 0),
                bridging_bonus_total=session_state.get("bridging_bonus_total", 0),
                same_topic_streak=session_state.get("same_topic_streak", 0),
                is_deepening=session_state.get("is_deepening", False),
                give_up_available=session_state.get("give_up_available", False),
                give_up_uses_remaining=session_state.get("give_up_uses_remaining", 0),
            ),
        )

    dedup_status = intent.lower()

    # ── 5. Read and reset post_nudge flag BEFORE evaluator call (Part 5D) ─
    post_nudge = bool(session_state.get("post_nudge_active", False))
    session_state["post_nudge_active"] = False  # will be persisted after save

    # ── 6. Look up vector_store_id for File Search retrieval ──────────────
    material = (
        db.query(TestMaterial)
        .filter(TestMaterial.test_id == session.test_id)
        .first()
    )
    if not material:
        raise HTTPException(status_code=400, detail="Test material not found")

    vector_store_id = material.vector_store_id
    if not vector_store_id:
        raise HTTPException(
            status_code=400,
            detail="Material has no vector store — please re-ingest the PDF.",
        )

    # ── 7. SKIP_BRIDGING_BONUS ────────────────────────────────────────────
    skip_bridging_bonus = dedup_status == "escalation"

    # ── 8. Build slim session state for evaluator LLM ────────────────────
    slim_session_state = {
        "current_topic": session_state.get("current_topic", ""),
        "same_topic_streak": session_state.get("same_topic_streak", 0),
        "is_deepening": session_state.get("is_deepening", False),
        "previous_scaffold": session_state.get(
            "previous_scaffold", {"strategy": "", "parameters": []}
        ),
        "previous_bloom": session_state.get("previous_bloom", 0),
        "previous_depth": session_state.get("previous_depth", 0),
        "consecutive_low_score_count": session_state.get("consecutive_low_score_count", 0),
    }
    logger.info(
        "Slim session state for evaluator: %s",
        json.dumps(slim_session_state),
    )

    # ── 9. Evaluator call (Part 3 + retrieval) ────────────────────────────
    evaluator_output = await call_evaluator(
        student_question=req.question_text,
        vector_store_id=vector_store_id,
        session_state=slim_session_state,
        skip_bridging_bonus=skip_bridging_bonus,
    )

    scores_out = evaluator_output.get("scores", {})
    relevance_r = float(scores_out.get("relevance_r", 0.5))
    bloom_b = int(scores_out.get("bloom_b", 1))
    depth_d = int(scores_out.get("depth_d", 1))
    bridging_bonus = int(scores_out.get("bridging_bonus", 0))

    if skip_bridging_bonus:
        bridging_bonus = 0

    # ── 11. Composite score ───────────────────────────────────────────────
    composite_score = round(
        (
            (relevance_r * 0.35)
            + ((bloom_b / 6) * 0.40)
            + ((depth_d / 4) * 0.25)
        )
        * 10,
        2,
    )

    scaffold = evaluator_output.get("scaffold_assigned", {})
    strategy = scaffold.get("strategy", "constraint_scaffolding")
    parameters = scaffold.get("parameters", [])
    cot = evaluator_output.get("chain_of_thought", {})
    feedback = evaluator_output.get("feedback", "Excellent thinking.")
    current_topic = evaluator_output.get("current_topic", "General Topic")[:60]

    # ── 12. Write question record (post_nudge included) ───────────────────
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
        post_nudge=post_nudge,
    )

    db_service.update_session_scores(db, session_id_str)

    # ── 13. Update Redis session state ────────────────────────────────────
    prev_topic = session_state.get("current_topic", "")
    if current_topic == prev_topic and prev_topic:
        session_state["same_topic_streak"] = session_state.get("same_topic_streak", 1) + 1
    else:
        session_state["same_topic_streak"] = 1
        session_state["current_topic"] = current_topic

    prev_b = session_state.get("previous_bloom", 0)
    prev_d = session_state.get("previous_depth", 0)
    session_state["is_deepening"] = (bloom_b > prev_b) or (depth_d > prev_d)
    session_state["previous_bloom"] = bloom_b
    session_state["previous_depth"] = depth_d
    session_state["previous_scaffold"] = {"strategy": strategy, "parameters": parameters}

    if bridging_bonus == 1:
        session_state["bridging_bonus_total"] = session_state.get("bridging_bonus_total", 0) + 1

    session_state["question_count"] = session_state.get("question_count", 0) + 1

    # Part 7: Update consecutive_low_score_count
    if composite_score < 4.0:
        session_state["consecutive_low_score_count"] = (
            session_state.get("consecutive_low_score_count", 0) + 1
        )
    else:
        session_state["consecutive_low_score_count"] = 0

    # post_nudge_active was already reset above; ensure it's persisted as False
    session_state["post_nudge_active"] = False

    # Final step of Redis update: recompute give_up_available (Part 5B)
    session_state = update_give_up_availability(session_state)

    await db_service.update_session_state(
        test_id=test_id_str,
        session_id=session_id_str,
        state=session_state,
    )

    logger.info(
        "Submit complete | session=%s composite=%.2f give_up_available=%s uses_remaining=%d",
        session_id_str,
        composite_score,
        session_state["give_up_available"],
        session_state["give_up_uses_remaining"],
    )

    # ── 14. Return response ───────────────────────────────────────────────
    return SubmitQuestionResponse(
        feedback=feedback,
        scores=SubmitQuestionScores(
            relevance_r=relevance_r,
            bloom_b=bloom_b,
            depth_d=depth_d,
            bridging_bonus=bridging_bonus,
            composite_score=composite_score,
        ),
        scaffold_strategy=strategy,
        session_stats=SubmitQuestionSessionStats(
            question_count=session_state["question_count"],
            bridging_bonus_total=session_state.get("bridging_bonus_total", 0),
            same_topic_streak=session_state["same_topic_streak"],
            is_deepening=session_state["is_deepening"],
            give_up_available=session_state["give_up_available"],
            give_up_uses_remaining=session_state["give_up_uses_remaining"],
        ),
    )


@router.post("/evaluate")
async def evaluate_question_stream(req: AssessmentRequest, db: Session = Depends(get_db)):
    raise HTTPException(
        status_code=410,
        detail="The SSE evaluate endpoint is deprecated. Use POST /submit-question instead.",
    )
