"""
Classifier service — lightweight single-token classification using CLASSIFIER_MODEL.
Used for deduplication and any off-topic pre-checks.
"""
import logging

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
) -> str:
    """
    Generic single-token classifier using CLASSIFIER_MODEL (gpt-5.4-nano).
    Returns one of valid_tokens. Falls back to valid_tokens[-1] on failure.
    """
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

    fallback = valid_tokens[-1]
    log.warning("Classifier fallback triggered — returning '%s'", fallback)
    return fallback


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
    )
    log.info("Dedup result: %s | question prefix: %.50s", result, new_question)
    return result
