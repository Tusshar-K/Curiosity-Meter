from typing import Optional

from pydantic import BaseModel, Field


class IngestionResponse(BaseModel):
    status: str
    test_id: str
    material_id: str
    token_count: int
    duplicate_material: bool
    time_limit_minutes: Optional[int] = None


class AssessmentRequest(BaseModel):
    test_id: str
    session_id: Optional[str] = None
    student_name: str = Field(default="Student")
    question_text: str


# ── Score progression (Part 5D & 9) ──────────────────────────
class ScoreProgressionItem(BaseModel):
    question_index: int
    composite_score: float
    post_nudge: bool


# ── Give Up summary (Part 9) ─────────────────────────────────
class GiveUpSummary(BaseModel):
    total_used: int
    topics_never_explored: list[str]


# ── Session summary response (Part 9) ────────────────────────
class SessionSummaryResponse(BaseModel):
    avg_relevance: float
    avg_bloom: float
    avg_depth: float
    total_bridging_bonuses: int
    total_questions: int
    score_progression: list[ScoreProgressionItem]
    give_up_summary: GiveUpSummary
    archetype: str


# ── Submit-question response (Part 5B) ───────────────────────
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
    give_up_available: bool
    give_up_uses_remaining: int


class SubmitQuestionResponse(BaseModel):
    feedback: str
    scores: Optional[SubmitQuestionScores] = None
    scaffold_strategy: Optional[str] = None
    session_stats: Optional[SubmitQuestionSessionStats] = None


# ── Session start ─────────────────────────────────────────────
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
    student_id: str
    test_id: str
    subject_name: str
    question_quota: int
    time_limit_minutes: Optional[int] = None
    materials: list[SessionMaterialSummary]


# ── Legacy session report ─────────────────────────────────────
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


# ── Give Up endpoint (Part 5C) ────────────────────────────────
class GiveUpRequest(BaseModel):
    session_id: str
    student_id: str


class GiveUpSessionStats(BaseModel):
    give_up_available: bool
    give_up_uses_remaining: int
    give_up_cooldown_questions: int


class GiveUpResponse(BaseModel):
    status: str
    feedback: str
    uses_remaining: int
    session_stats: GiveUpSessionStats
