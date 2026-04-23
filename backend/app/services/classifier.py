"""
Classifier service — lightweight single-token classification.
Used for deduplication and any off-topic pre-checks.
"""
import logging
import re

from app.services.llm_client import client, CLASSIFIER_MODEL

log = logging.getLogger(__name__)

_DEDUP_SYSTEM_PROMPT = (
    "You are a Deduplication Router. Compare [New Question] to [History]. "
    "If it asks for the exact same conceptual answer/definition, output DUPLICATE. "
    "If it introduces a new variable, asks why a previous concept happens, or escalates "
    "in cognitive demand, output ESCALATION. Otherwise output UNIQUE. "
    "Return ONLY one token: DUPLICATE, ESCALATION, or UNIQUE."
)


async def classify_text(
    system_prompt: str,
    user_content: str,
    valid_tokens: list[str],
    fallback_token: str | None = None,
) -> str:
    """
    Generic single-token classifier.
    Returns one of valid_tokens. Falls back to fallback_token (or first valid token) on failure.
    """
    resolved_fallback = (fallback_token or valid_tokens[0]).upper()
    if resolved_fallback not in valid_tokens:
        resolved_fallback = valid_tokens[0]

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=CLASSIFIER_MODEL,
                temperature=0,
                max_tokens=5,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
            result = (response.choices[0].message.content or "").strip().upper()
            if result in valid_tokens:
                log.info("Classifier result: %s (attempt %d)", result, attempt + 1)
                return result
            log.warning(
                "Classifier unexpected token '%s' (attempt %d)", result, attempt + 1
            )
        except Exception as exc:
            log.warning("Classifier attempt %d failed: %s", attempt + 1, exc)

    log.warning("Classifier fallback triggered — returning '%s'", resolved_fallback)
    return resolved_fallback


def _normalize_question(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    normalized = re.sub(r"[^a-z0-9\s?]", "", normalized)
    return normalized


async def classify_duplicate(
    history: list[dict[str, str]],
    new_question: str,
) -> str:
    """
    Classifies a new student question against session history.
    Returns: 'UNIQUE', 'ESCALATION', or 'DUPLICATE'.
    """
    if not history:
        log.info("Dedup: empty history — returning UNIQUE")
        return "UNIQUE"

    normalized_new = _normalize_question(new_question)
    normalized_history = {
        _normalize_question(item.get("q", ""))
        for item in history[-20:]
        if item.get("q")
    }
    if normalized_new and normalized_new in normalized_history:
        log.info("Dedup: exact normalized match found — returning DUPLICATE")
        return "DUPLICATE"

    history_text = "\n".join(
        f"- Q: {item.get('q', '')[:100]}" for item in history[-20:]
    )
    user_payload = (
        f"[History]\n{history_text}\n\n"
        f"[New Question]\n{new_question[:200]}"
    )

    result = await classify_text(
        system_prompt=_DEDUP_SYSTEM_PROMPT,
        user_content=user_payload,
        valid_tokens=["UNIQUE", "ESCALATION", "DUPLICATE"],
        fallback_token="UNIQUE",
    )
    log.info("Dedup result: %s | question prefix: %.50s", result, new_question)
    return result
