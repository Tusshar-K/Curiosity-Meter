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


class ScoreProgressionItem(BaseModel):
    question_index: int
    composite_score: float

class SessionSummaryResponse(BaseModel):
    avg_relevance: float
    avg_bloom: float
    avg_depth: float
    total_bridging_bonuses: int
    total_questions: int
    score_progression: list[ScoreProgressionItem]
    archetype: str

class SubmitQuestionScores(BaseModel):
    relevance_r: float
    bloom_b: int
    depth_d: int
    bridging_bonus: int
    composite_score: float

class SubmitQuestionSessionStats(BaseModel):
    question_count: int
    bridging_bonus_total: int
    same_topic_streak: int
    is_deepening: bool

class SubmitQuestionResponse(BaseModel):
    feedback: str
    scores: Optional[SubmitQuestionScores] = None
    scaffold_strategy: Optional[str] = None
    session_stats: Optional[SubmitQuestionSessionStats] = None


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
