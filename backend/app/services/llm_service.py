import json
import logging
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)
ALLOWED_RELEVANCE_VALUES = [0.0, 0.25, 0.5, 0.75, 1.0]


EVALUATOR_SYSTEM_PROMPT = """
Role: You are an expert pedagogical evaluator and an encouraging, empathetic teaching assistant evaluating an undergrad's question.
Tone: Build confidence. Validate effort first. If depth is low, frame it as an opportunity to dig deeper. NEVER explicitly mention numerical scores in the feedback.

Semantic Congruence Protocol: Ignore high-level verbs (e.g., "Design", "Evaluate") if the actual cognitive payload is just basic recall. Do a chain_of_thought to verify the verb matches the payload.

Bloom's Taxonomy (Undergraduate Rubric - BE ENCOURAGING):
Reward reasonable attempts.
1 (Remember): Basic fact, definition, or list.
2 (Understand): Explanation or summary ("How does this work?").
3 (Apply): Applies a concept to a standard, straightforward scenario.
4 (Analyze): Breaks a concept down or asks about the relationship between two specific parts.
5 (Evaluate): Asks for a comparison, weighs trade-offs, or asks "Which is better/worse?" based on the text.
6 (Create): Asks a "What if?" hypothetical. Synthesizes concepts to predict an outcome in a new scenario.

Depth (D) Scale (Strict 1-4 Ladder):
1: Surface Level ("What is X?").
2: Operational ("How does X do Y?").
3: Variable Interaction ("If temperature drops, how does X change?").
4: Edge-Case / Boundary ("At absolute zero, does the rule break down?").
Rule: If Bloom's is 5 or 6, Depth should generally be 3 or 4.

Relevance (R) Scale (Strict Enum based on outside knowledge):
1.0: Fully Grounded (Uses ONLY provided text).
0.75: Near-Miss (Introduces a minor, reasonable outside variable).
0.50: Partial Bridge (Takes core concept and applies to outside domain).
0.25: Tangential (Grabs a minor keyword, but premise is outside material).
0.0: Off-Topic (No conceptual overlap).

Stateful Evaluation (History): Review the <student_session_history>.

Momentum Bonus: If the student applied previous feedback to improve this question, or if it's a logical deep-dive follow-up, set momentum_bonus to 1. Else 0.

Topic Fixation Penalty: If the student is asking multiple questions about the exact same sub-topic at the same low cognitive depth (e.g., asking for four different definitions within fluid dynamics), apply the topic_fixation_penalty as -1. HOWEVER, if the questions show increasing Depth (D) and Bloom's (B) on the same topic (e.g., moving from definition to application to synthesis), this is Deep Exploration, NOT fixation. Do not penalize (set to 0).

Output Schema:
{
"chain_of_thought": {
"claimed_action": "<verb used>",
"cognitive_payload": "<actual knowledge required>",
"congruence_check": "<brief explanation of match/mismatch>"
},
"scores": {
"relevance_r": <float 0-1>,
"bloom_b": <int 1-6>,
"depth_d": <int 1-4>,
"momentum_bonus": <int 0 or 1>,
"topic_fixation_penalty": <int 0 or -1>
},
"feedback": "<Empathetic, 2-3 sentences. Nudge to next Bloom level or enhancing the Depth level.>"
}
""".strip()


INTENT_ROUTER_PROMPT = """
You are a Deduplication Router. Compare [New Question] to [History]. If it asks for the exact same conceptual answer/definition, output DUPLICATE. If it introduces a new variable or asks why a previous concept happens, output UNIQUE.
Return ONLY one token: DUPLICATE or UNIQUE.
""".strip()


class LLMService:
    def __init__(self):
        self.genai_client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

    async def embed_text(self, text: str) -> list[float]:
        if not self.genai_client:
            return [0.0] * 3072

        try:
            response = self.genai_client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
            )
            return response.embeddings[0].values
        except Exception as exc:
            logger.warning("Embedding call failed: %s", exc)
            return [0.0] * 3072

    async def classify_duplicate(self, history: list[dict[str, str]], new_question: str) -> str:
        if not history:
            return "UNIQUE"
        if not self.genai_client:
            return "UNIQUE"

        history_text = "\n".join([f"- Q: {item.get('q', '')}" for item in history[-20:]])
        user_payload = f"[History]\n{history_text}\n\n[New Question]\n{new_question}"
        try:
            response = self.genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(role="user", parts=[types.Part(text=f"{INTENT_ROUTER_PROMPT}\n\n{user_payload}")]),
                ],
                config=types.GenerateContentConfig(temperature=0),
            )
            token = (response.text or "").strip().upper()
            return "DUPLICATE" if "DUPLICATE" in token else "UNIQUE"
        except Exception as exc:
            logger.warning("Duplicate classification failed: %s", exc)
            return "UNIQUE"

    async def evaluate_question(
        self,
        question: str,
        contexts: list[str],
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        fallback = {
            "chain_of_thought": {
                "claimed_action": "",
                "cognitive_payload": "",
                "congruence_check": "",
            },
            "scores": {
                # Use a neutral relevance when evaluator API fails to avoid unfair off-topic auto-penalty.
                "relevance_r": 0.5,
                "bloom_b": 1,
                "depth_d": 1,
                "momentum_bonus": 0,
                "topic_fixation_penalty": 0,
            },
            "feedback": "Great effort asking a question. Try anchoring it to one specific mechanism from the material and then ask how changing one variable would alter the outcome.",
        }

        if not self.genai_client:
            return fallback

        context_block = "\n\n".join([f"Context {idx + 1}: {chunk}" for idx, chunk in enumerate(contexts)])
        history_block = "\n".join(
            [f"- q: {item.get('q', '')} | feedback: {item.get('feedback', '')}" for item in history[-20:]]
        )
        user_payload = (
            f"<context>\n{context_block}\n</context>\n"
            f"<student_session_history>\n{history_block}\n</student_session_history>\n"
            f"<new_question>\n{question}\n</new_question>"
        )

        schema = {
            "type": "object",
            "properties": {
                "chain_of_thought": {
                    "type": "object",
                    "properties": {
                        "claimed_action": {"type": "string"},
                        "cognitive_payload": {"type": "string"},
                        "congruence_check": {"type": "string"},
                    },
                    "required": ["claimed_action", "cognitive_payload", "congruence_check"],
                },
                "scores": {
                    "type": "object",
                    "properties": {
                        "relevance_r": {
                            # Gemini response_schema currently expects enum entries as strings.
                            "type": "string",
                            "enum": ["0.0", "0.25", "0.5", "0.75", "1.0"],
                        },
                        "bloom_b": {"type": "integer"},
                        "depth_d": {"type": "integer"},
                        "momentum_bonus": {"type": "integer"},
                        "topic_fixation_penalty": {"type": "integer"},
                    },
                    "required": [
                        "relevance_r",
                        "bloom_b",
                        "depth_d",
                        "momentum_bonus",
                        "topic_fixation_penalty",
                    ],
                },
                "feedback": {"type": "string"},
            },
            "required": ["chain_of_thought", "scores", "feedback"],
        }

        try:
            response = self.genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=[types.Part(text=user_payload)])],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    system_instruction=EVALUATOR_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            parsed = json.loads(response.text)
            scores = parsed.get("scores", {}) if isinstance(parsed, dict) else {}
            relevance_raw = scores.get("relevance_r", 0.5)
            try:
                relevance = float(relevance_raw)
            except (TypeError, ValueError):
                relevance = 0.5
            snapped_relevance = min(ALLOWED_RELEVANCE_VALUES, key=lambda x: abs(x - relevance))
            scores["relevance_r"] = snapped_relevance
            parsed["scores"] = scores
            return parsed
        except Exception as exc:
            logger.warning("Evaluator call failed: %s", exc)
            return fallback


llm_service = LLMService()
