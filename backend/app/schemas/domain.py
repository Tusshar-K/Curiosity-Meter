from pydantic import BaseModel
from typing import List, Optional, Any

class IngestionRequest(BaseModel):
    content_type: str        # 'pdf' or 'url'
    source: str              # URL or Base64/path
    metadata: Optional[dict] = None

class IngestionResponse(BaseModel):
    status: str
    token_count: int
    storage: str             # 'postgres' or 'qdrant'

class AssessmentRequest(BaseModel):
    session_id: str
    student_id: str
    question_text: str

class AssessmentResponse(BaseModel):
    session_id: str
    score: float
    feedback: str
    is_duplicate: bool
    duplicate_penalty: float
