from typing import Optional

from pydantic import BaseModel, Field


class IngestionResponse(BaseModel):
    status: str
    test_id: str
    material_id: str
    token_count: int
    duplicate_material: bool


class AssessmentRequest(BaseModel):
    test_id: str
    session_id: Optional[str] = None
    student_name: str = Field(default="Student")
    question_text: str


class SessionSummary(BaseModel):
    session_id: str
    total_questions: int
    question_quota: int
    total_raw_score: float
    final_clamped_score: float
    status: str


class StartSessionRequest(BaseModel):
    student_name: str
    test_id: str


class SessionMaterialSummary(BaseModel):
    id: str
    file_name: str
    token_count: int
    topic_outline: list[str]


class StartSessionResponse(BaseModel):
    session_id: str
    test_id: str
    subject_name: str
    question_quota: int
    materials: list[SessionMaterialSummary]


class SessionQuestionReportItem(BaseModel):
    question_text: str
    feedback: str
    r_score: float
    b_score: int
    d_score: int
    momentum_bonus: int
    topic_fixation_penalty: int
    penalties_applied: dict
    final_question_score: float


class SessionReportResponse(BaseModel):
    session_id: str
    subject_name: str
    final_clamped_score: float
    max_marks: int
    total_questions: int
    question_quota: int
    questions: list[SessionQuestionReportItem]
