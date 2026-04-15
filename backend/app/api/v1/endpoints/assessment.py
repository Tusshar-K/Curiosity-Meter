import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.db.session import get_db
from app.schemas.domain import AssessmentRequest
from app.services.db_service import db_service
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_scores(payload: dict) -> tuple[float, int, int, int, int, str]:
    scores = payload.get("scores", {}) if isinstance(payload, dict) else {}
    relevance = float(scores.get("relevance_r", 0.0) or 0.0)
    bloom = int(scores.get("bloom_b", 1) or 1)
    depth = int(scores.get("depth_d", 1) or 1)
    momentum_bonus = int(scores.get("momentum_bonus", 0) or 0)
    topic_fixation_penalty = int(scores.get("topic_fixation_penalty", 0) or 0)
    feedback = str(payload.get("feedback", "Good effort. Keep exploring with more specific, mechanism-focused questions."))

    relevance = max(0.0, min(1.0, relevance))
    bloom = max(1, min(6, bloom))
    depth = max(1, min(4, depth))
    momentum_bonus = 1 if momentum_bonus == 1 else 0
    topic_fixation_penalty = -1 if topic_fixation_penalty == -1 else 0

    return relevance, bloom, depth, momentum_bonus, topic_fixation_penalty, feedback


async def generate_assessment_stream(db: Session, req: AssessmentRequest):
    try:
        session = db_service.get_or_create_student_session(
            db=db,
            test_id=req.test_id,
            session_id=req.session_id,
            student_name=req.student_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_id = str(session.id)
    yield {"event": "status", "data": json.dumps({"message": "Session initialized."})}

    async def intent_judge_task():
        history = await db_service.get_session_history(session_id)
        intent = await llm_service.classify_duplicate(history, req.question_text)
        return history, intent

    async def retrieval_task():
        q_vector = await llm_service.embed_text(req.question_text)
        contexts = await db_service.search_vectors(
            test_id=req.test_id,
            query_vector=q_vector,
            question_text=req.question_text,
            top_k=5,
        )
        return contexts

    yield {"event": "status", "data": json.dumps({"message": "Running duplicate check + retrieval in parallel..."})}
    (history, intent), contexts = await asyncio.gather(intent_judge_task(), retrieval_task())

    yield {"event": "status", "data": json.dumps({"message": "Evaluating pedagogical quality..."})}
    evaluator_output = await llm_service.evaluate_question(
        question=req.question_text,
        contexts=contexts,
        history=history,
    )

    relevance, bloom, depth, momentum_bonus, topic_fixation_penalty, feedback = _safe_scores(evaluator_output)

    base_score = relevance * (bloom + depth)
    adjusted_score = min(10.0, base_score + momentum_bonus)

    penalty_duplicate = -5 if intent == "DUPLICATE" else 0
    penalty_off_topic = -2 if relevance == 0.0 else 0
    backend_penalties = penalty_duplicate + penalty_off_topic

    final_question_score = adjusted_score + topic_fixation_penalty + backend_penalties

    penalties_applied = {
        "duplicate": penalty_duplicate,
        "off_topic": penalty_off_topic,
    }

    db_service.save_question_log(
        db=db,
        session_id=session_id,
        question_text=req.question_text,
        r_score=relevance,
        b_score=bloom,
        d_score=depth,
        momentum_bonus=momentum_bonus,
        topic_fixation_penalty=topic_fixation_penalty,
        penalties_applied=penalties_applied,
        feedback=feedback,
        final_question_score=final_question_score,
    )

    await db_service.append_session_history(session_id, req.question_text, feedback)
    updated_session, log_count, quota = db_service.update_session_scores(db, session_id)

    words = feedback.split()
    for idx in range(0, len(words), 8):
        partial = " ".join(words[: idx + 8])
        yield {"event": "feedback", "data": json.dumps({"text": partial})}

    result_payload = {
        "session_id": session_id,
        "question_score": round(final_question_score, 2),
        "scores": {
            "relevance_r": relevance,
            "bloom_b": bloom,
            "depth_d": depth,
            "momentum_bonus": momentum_bonus,
            "topic_fixation_penalty": topic_fixation_penalty,
        },
        "penalties_applied": penalties_applied,
        "is_duplicate": intent == "DUPLICATE",
        "history_count": len(history) + 1,
        "feedback": feedback,
    }

    yield {"event": "result", "data": json.dumps(result_payload)}

    if updated_session.status == "completed":
        summary_payload = {
            "session_id": session_id,
            "total_questions": log_count,
            "question_quota": quota,
            "total_raw_score": round(updated_session.total_raw_score, 2),
            "final_clamped_score": round(updated_session.final_clamped_score, 2),
            "status": updated_session.status,
        }
        yield {"event": "summary", "data": json.dumps(summary_payload)}


@router.post("/evaluate")
async def evaluate_question_stream(req: AssessmentRequest, db: Session = Depends(get_db)):
    if not req.question_text.strip():
        raise HTTPException(status_code=400, detail="question_text must not be empty")

    return EventSourceResponse(generate_assessment_stream(db, req))
