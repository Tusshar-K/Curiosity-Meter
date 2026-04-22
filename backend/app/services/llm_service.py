"""
llm_service.py — thin delegation wrapper.

All Gemini code has been removed. Logic now lives in:
  - app.services.evaluator  (call_evaluator, EVALUATOR_SYSTEM_PROMPT)
  - app.services.classifier (classify_text, classify_duplicate)
  - app.services.vector_store (retrieve_chunks, upload helpers)

This module is kept for any remaining backward-compatible imports.
"""
from app.services.classifier import classify_duplicate
from app.services.evaluator import call_evaluator, build_fallback_response
from app.services.vector_store import retrieve_chunks

__all__ = [
    "classify_duplicate",
    "call_evaluator",
    "build_fallback_response",
    "retrieve_chunks",
]
