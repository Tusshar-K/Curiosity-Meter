"""
Central OpenAI client module.
All services must import from here — never initialize their own clients.
"""
from openai import OpenAI

from app.core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Model assignments — change only here if models need updating
EVALUATOR_MODEL      = "gpt-5-mini"        # Evaluator Responses API
RETRIEVAL_MODEL      = "gpt-5-mini"        # File search tool call model
CLASSIFIER_MODEL     = "gpt-5-mini"        # Dedup classifier
NUDGE_MODEL          = "gpt-5-mini"         # Give Up nudge generator
EMBEDDING_MODEL      = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 512
