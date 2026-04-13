from sentence_transformers import CrossEncoder
from google import genai
from google.genai import types
from app.core.config import settings
import json
import logging

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        # Initialize Cross-Encoder for Deduplication natively on CPU
        self.cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        # Setup Gemini Client
        self.genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def check_duplicate(self, new_question: str, past_questions: list[str]) -> float:
        if not past_questions:
            return 0.0
            
        # Cross encoder returns a similarity score usually mapped roughly to semantic overlap.
        # We pair the new question with all past questions.
        pairs = [[new_question, past_q] for past_q in past_questions]
        scores = self.cross_encoder.predict(pairs)
        max_score = float(max(scores))
        
        # Depending on the model, MS-Marco logits are usually high (e.g. 5+). 
        # A simpler cosine similarity transformer might be bounded 0-1, but for safety in this MVP:
        return max_score

    async def embed_question(self, text: str) -> list[float]:
        # Handle the known dummy key gracefully
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("AIzaSyAXXT"):
             return [0.0]*3072 # Dummy vector if no key is present during dev

        try:
            # Call Gemini Text Embedding API
            response = self.genai_client.models.embed_content(
                model='gemini-embedding-001',
                contents=text
            )
            return response.embeddings[0].values
        except Exception as e:
            print(f"Warning: Gemini Embedding API failed: {e}")
            return [0.0]*3072

    async def evaluate_question(self, question: str, contexts: list[str]) -> dict:
        fallback = {
             "chain_of_thought": {"claimed_action": "", "cognitive_payload": "", "congruence_check": ""},
             "scores": {"relevance": 0.0, "bloom_level": 1, "depth": 1},
             "feedback": "API Key missing or failed to parse LLM evaluation."
        }
        if not settings.GEMINI_API_KEY:
             return fallback

        context_str = "\n\n".join([f"Context {i+1}: {c}" for i, c in enumerate(contexts)])
        
        prompt = f"""
        Role: You are an expert pedagogical evaluator and cognitive scientist. Your task is to evaluate a student's question based on the provided reference text. You will grade the question on Relevance (R), Bloom's Level (B), and Depth (D), and provide constructive feedback.

        The "Semantic Congruence" Protocol (CRITICAL):
        Students frequently attempt to inflate their Bloom's Level by using high-level action verbs (e.g., "Synthesize", "Evaluate", "Design") for tasks that only require basic recall or summarization. You must ignore the assumed difficulty of the verb and evaluate the actual cognitive effort required to answer the question.

        You must follow these steps strictly in your chain_of_thought:

        Identify Claimed Action: Isolate the primary action verb or introductory phrase the student used (e.g., "Create a scenario where...").

        Identify Cognitive Payload: Strip away the introductory phrasing. What specific data, facts, or mental connections are actually required from the reference text to formulate an answer?

        Congruence Check: Compare the Claimed Action against the Cognitive Payload. Does the payload justify the verb? If a student asks to "Design an explanation of [Fact X]", the payload is just recall (Level 1), regardless of the word "Design".

        The Cognitive Payload Rubric:
        Use ONLY the required payload to determine the final Bloom's Level (1-6):

        Level 1 (Remember): Payload requires only retrieving or defining a fact explicitly stated in the text.

        Level 2 (Understand): Payload requires summarizing, translating, or explaining a concept in their own words.

        Level 3 (Apply): Payload requires using the textbook rules/formulas in a novel, specific scenario provided by the student.

        Level 4 (Analyze): Payload requires breaking a complex system from the text into parts and comparing/contrasting them under stress or changing variables.

        Level 5 (Evaluate): Payload requires the student to establish a specific metric or criteria (e.g., cost, efficiency, ethics) and make a judgment based on it.

        Level 6 (Create): Payload requires inventing a new structure, protocol, or solution that synthesizes rules from the text to solve a novel problem.

        Scoring Parameters:

        Relevance (R): Is the core payload grounded in the text? (0 = No, 0.25 = Tangential, 0.5 = Partial, 0.75 = Near-Miss, 1 = Fully Grounded).

        Depth (D): How specific is the inquiry? (1 = Broad topic, 4 = Laser-focused on a specific sub-system or variable).

        Output Format:
        You must output a raw, strictly valid JSON object exactly matching this schema. Do not include markdown formatting like ```json.

        {{
            "chain_of_thought": {{
                "claimed_action": "<string>",
                "cognitive_payload": "<string>",
                "congruence_check": "<string explaining the mismatch or match>"
            }},
            "scores": {{
                "relevance": <number 0 to 1>,
                "bloom_level": <number 1 to 6>,
                "depth": <number 1 to 4>
            }},
            "feedback": "<string: empathetic, 2-3 sentences. Do not mention the numerical scores directly. Guide them on how to ask a deeper question if the score is low.>"
        }}
        
        Context Material:
        {context_str}
        
        Student's Question:
        {question}
        """

        try:
            response = self.genai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"Warning: Gemini Generate Content API failed: {e}")
            return fallback
    
llm_service = LLMService()
