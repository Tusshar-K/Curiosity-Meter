"""
POST /give-up endpoint — Part 5C
10-step processing pipeline for the "I Give Up" student nudge feature.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Question, TestMaterial
from app.db.session import get_db
from app.schemas.domain import GiveUpRequest, GiveUpResponse, GiveUpSessionStats, GiveUpUnavailableResponse
from app.services.db_service import db_service
from app.services.llm_client import client, NUDGE_MODEL

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/give-up")
async def give_up(req: GiveUpRequest, db: Session = Depends(get_db)):
    session_id = req.session_id
    student_id = req.student_id

    # ── Step 1: Load session state from Redis ─────────────────────────────
    key = f"session:{session_id}:state"
    state = await db_service.get_session_state(session_id)
    # Detect if key was truly absent (fresh default with no question_count activity)
    raw = await db_service.redis.get(key)
    if raw is None:
        logger.warning("Give Up: session key missing for session_id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session state not found.")

    # ── Step 2: Validate availability ────────────────────────────────────
    give_up_available = state.get("give_up_available", False)
    question_count = state.get("question_count", 0)
    uses_remaining = state.get("give_up_uses_remaining", 0)
    cooldown = state.get("give_up_cooldown_questions", 0)

    if not give_up_available:
        if question_count < 3:
            reason = "too_early"
            feedback_msg = (
                "The Give Up option unlocks after your third question. "
                "Keep exploring — you're just getting started."
            )
        elif uses_remaining == 0:
            reason = "exhausted"
            feedback_msg = (
                "You've used all your Give Up hints for this session. "
                "Trust the questions you've been building — keep going."
            )
        else:
            reason = "cooldown"
            feedback_msg = (
                f"The Give Up option is on cooldown for {cooldown} more "
                "question(s). Take a fresh angle on the material."
            )
        logger.info(
            "Give Up unavailable | session=%s reason=%s", session_id, reason
        )
        raise HTTPException(
            status_code=403,
            detail={
                "status": "unavailable",
                "reason": reason,
                "feedback": feedback_msg,
            },
        )

    logger.info("Give Up activated | session=%s", session_id)

    # ── Step 3: Load covered topics from PostgreSQL ───────────────────────
    from sqlalchemy import text as sa_text
    from app.db.models import StudentSession
    import uuid

    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    covered_rows = (
        db.query(Question.current_topic)
        .filter(
            Question.session_id == session_uuid,
            Question.dedup_status != "duplicate",
            Question.current_topic.isnot(None),
            Question.current_topic != "",
        )
        .distinct()
        .order_by(Question.created_at.asc())
        .all()
    )
    covered: set[str] = {row[0] for row in covered_rows if row[0]}
    logger.info("Give Up: covered topics (%d): %s", len(covered), list(covered))

    # ── Step 4: Load document topic map from PostgreSQL ───────────────────
    session_record = (
        db.query(StudentSession)
        .filter(StudentSession.id == session_uuid)
        .first()
    )
    if not session_record:
        raise HTTPException(status_code=404, detail="Session record not found")

    material = (
        db.query(TestMaterial)
        .filter(TestMaterial.test_id == session_record.test_id)
        .first()
    )
    all_topics_raw: list[str] = []
    if material and material.topic_map:
        tm = material.topic_map
        if isinstance(tm, list):
            all_topics_raw = [str(t) for t in tm]

    all_topics: set[str] = set(all_topics_raw)

    # ── Step 5: Compute uncovered topics ─────────────────────────────────
    uncovered = all_topics - covered
    if not uncovered:
        # Student has touched everything — nudge toward deeper connections
        uncovered = all_topics
    logger.info(
        "Give Up: uncovered topics (%d): %s", len(uncovered), list(uncovered)[:5]
    )

    # ── Step 6: Generate nudge with NUDGE_MODEL ───────────────────────────
    nudge_system_prompt = (
        "You are an encouraging academic guide. A student is stuck "
        "and has asked for a hint about what to explore next.\n\n"
        "You will receive:\n"
        "- COVERED: topics the student has already asked about\n"
        "- UNCOVERED: topics from the material not yet explored\n\n"
        "Your task: Write 2-3 sentences that warmly encourage the "
        "student and point them toward 1-2 uncovered areas worth "
        "exploring. Do not name specific questions. Do not give "
        "specific nouns or named concepts. Describe the territory "
        "in terms of abstract properties or phenomena (e.g., "
        "'processes where energy changes form' not 'ATP synthesis'). "
        "End with a period. No question marks."
    )
    nudge_user_message = (
        f"COVERED TOPICS: {json.dumps(list(covered))}\n"
        f"UNCOVERED TOPICS: {json.dumps(list(uncovered)[:5])}"
    )

    nudge_text = ""
    try:
        nudge_response = client.chat.completions.create(
            model=NUDGE_MODEL,
            temperature=0.7,
            messages=[
                {"role": "system", "content": nudge_system_prompt},
                {"role": "user", "content": nudge_user_message},
            ],
        )
        nudge_text = (nudge_response.choices[0].message.content or "").strip()
        logger.info("Give Up nudge generated: %.50s...", nudge_text)
    except Exception as exc:
        logger.error("Give Up nudge generation failed: %s", exc)
        nudge_text = (
            "There's still territory in this material worth exploring. "
            "Consider the parts of the topic you haven't questioned yet — "
            "the most interesting connections often come from unexpected angles."
        )

    # ── Step 7: Update Redis state ────────────────────────────────────────
    state["give_up_uses_remaining"] = max(0, uses_remaining - 1)
    state["give_up_cooldown_questions"] = 3
    state["give_up_available"] = False
    state["post_nudge_active"] = True  # Step 9: flag for next submission
    await db_service.update_session_state(session_id, state)  # refreshes TTL to 7200s

    new_uses_remaining = state["give_up_uses_remaining"]

    # ── Step 8: Write give_up_events record to PostgreSQL ─────────────────
    db_service.save_give_up_event(
        db=db,
        session_id=session_id,
        student_id=student_id,
        covered_topics=list(covered),
        uncovered_topics=list(uncovered)[:5],
        nudge_text=nudge_text,
    )

    logger.info(
        "Give Up event saved | session=%s uses_remaining=%d",
        session_id,
        new_uses_remaining,
    )

    # ── Step 10: Return response ──────────────────────────────────────────
    return GiveUpResponse(
        status="ok",
        feedback=nudge_text,
        uses_remaining=new_uses_remaining,
        session_stats=GiveUpSessionStats(
            give_up_available=False,
            give_up_uses_remaining=new_uses_remaining,
            give_up_cooldown_questions=3,
        ),
    )
