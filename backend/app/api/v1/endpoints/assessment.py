from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
import asyncio
import json
from app.schemas.domain import AssessmentRequest
from app.services.db_service import db_service
from app.services.llm_service import llm_service
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

async def generate_assessment_stream(session_id: str, question: str):
    """
    Generator function to yield Server-Sent Events (SSE) back to the client.
    Executes Thread A (Deduplication) and Thread B (RAG) concurrently.
    """
    yield {
         "event": "status", 
         "data": json.dumps({"message": "Initializing Semantic Pipeline..."})
    }
    
    # ----------------------------------------------------
    # PHASE 1: Concurrent Search & Deduplication
    # ----------------------------------------------------
    yield {
         "event": "status", 
         "data": json.dumps({"message": "Running deduplication check and Qdrant retrieval concurrently..."})
    }
    
    async def get_contexts():
        # Embed the new question and query Qdrant (Thread B)
        query_vec = await llm_service.embed_question(question)
        return await db_service.search_vectors(query_vec, top_k=3)

    async def get_duplicate_penalty():
        # Fetch Redis history and cross-encode (Thread A)
        past_Qs = await db_service.get_session_questions(session_id)
        if not past_Qs:
            return 0.0 # No penalty
            
        max_sim = await llm_service.check_duplicate(question, past_Qs)
        # Apply strict -5 penalty if > 85% duplicate
        return 5.0 if max_sim > 0.85 else 0.0
        
    # Execute Thread A & B concurrently
    contexts, duplicate_penalty = await asyncio.gather(
        get_contexts(),
        get_duplicate_penalty()
    )
    
    logger.info(f"Stream [Session: {session_id}] - Context retrieved: {len(contexts)} chunks. Duplicate Penalty: {duplicate_penalty}")
    
    is_duplicate = duplicate_penalty > 0
    yield {
         "event": "status", 
         "data": json.dumps({
             "message": f"Pipeline finished. Duplication penalty detected: {is_duplicate}"
        })
    }

    # ----------------------------------------------------
    # PHASE 2: Heavy LLM Evaluation via Gemini
    # ----------------------------------------------------
    yield {
         "event": "status", 
         "data": json.dumps({"message": "Evaluating Cognitive Payload using Gemini CoT..."})
    }
    
    raw_eval = await llm_service.evaluate_question(question, contexts)
    
    # Extract values safely from nested schemas
    scores = raw_eval.get("scores", {})
    relevance = scores.get("relevance", 0.0)
    bloom_score = scores.get("bloom_level", 1)
    depth_score = scores.get("depth", 1)
    feedback = raw_eval.get("feedback", "No feedback provided.")
    
    # The UI is now updated to expect scores out of 10, removing normalization
    base_score = relevance * (bloom_score + depth_score)
    
    # ----------------------------------------------------
    # PHASE 3: Apply Rules & Penalties
    # ----------------------------------------------------
    final_score = base_score
    if relevance == 0.0:
        final_score -= 2.0  # Off-Topic Penalty
    
    final_score -= duplicate_penalty # Semantic Duplicate Penalty
    
    # Floor the score at 0
    final_score = max(0.0, round(final_score, 2))
    
    logger.info(f"Stream [Session: {session_id}] - Generated Final Score: {final_score}/10.0 (Relevance: {relevance}, Bloom: {bloom_score}, Depth: {depth_score})")
    
    # Finally, append the new question to the Redis session queue
    await db_service.save_session_question(session_id, question)

    # Yield final calculated result block
    result = {
        "session_id": session_id,
        "score": final_score,
        "bloom": bloom_score,
        "depth": depth_score,
        "relevance": relevance,
        "feedback": feedback,
        "is_duplicate": is_duplicate,
        "duplicate_penalty": duplicate_penalty
    }
    
    yield {
        "event": "result",
        "data": json.dumps(result)
    }


@router.post("/stream")
async def stream_assessment(request: Request, assessment_req: AssessmentRequest):
    return EventSourceResponse(
        generate_assessment_stream(assessment_req.session_id, assessment_req.question_text)
    )
