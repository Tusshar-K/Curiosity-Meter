import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Numeric,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Test(Base):
    __tablename__ = "tests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    faculty_name = Column(String(255), nullable=False)
    subject_name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    config = relationship("TestConfig", back_populates="test", uselist=False, cascade="all, delete-orphan")
    materials = relationship("TestMaterial", back_populates="test", cascade="all, delete-orphan")
    sessions = relationship("StudentSession", back_populates="test", cascade="all, delete-orphan")


class Student(Base):
    __tablename__ = "students"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    sessions = relationship("StudentSession", back_populates="student", cascade="all, delete-orphan")


class TestConfig(Base):
    __tablename__ = "test_config"

    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), primary_key=True)
    question_quota = Column(Integer, nullable=False, default=5)
    max_marks = Column(Integer, nullable=False, default=50)

    test = relationship("Test", back_populates="config")


class TestMaterial(Base):
    __tablename__ = "test_materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    token_count = Column(Integer, nullable=False, default=0)
    topic_outline = Column(JSON, nullable=False, default=list)
    # Part 2A: OpenAI vector store id for File Search
    vector_store_id = Column(String(64), nullable=True)
    # Part 2B Step 5: LLM-generated topic map for Give Up nudge
    topic_map = Column(JSONB, nullable=True, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    test = relationship("Test", back_populates="materials")


class StudentSession(Base):
    __tablename__ = "student_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    student_name = Column(String(255), nullable=False)
    total_raw_score = Column(Float, nullable=False, default=0.0)
    final_clamped_score = Column(Float, nullable=False, default=0.0)
    status = Column(String(20), nullable=False, default="active")
    # Part 5A: question budget drives give_up_uses_remaining initialization
    question_budget = Column(Integer, nullable=False, default=20)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    test = relationship("Test", back_populates="sessions")
    student = relationship("Student", back_populates="sessions")
    question_logs = relationship("Question", back_populates="session", cascade="all, delete-orphan")
    give_up_events = relationship("GiveUpEvent", back_populates="session", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("student_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    dedup_status = Column(String(50), nullable=False, default="unique")
    relevance_r = Column(Float, nullable=True)
    bloom_b = Column(Integer, nullable=True)
    depth_d = Column(Integer, nullable=True)
    bridging_bonus = Column(Integer, nullable=True)
    composite_score = Column(Numeric(4, 2), nullable=True)
    current_topic = Column(String(60), nullable=True)
    feedback_text = Column(Text, nullable=True)
    scaffold_strategy = Column(String(40), nullable=True)
    scaffold_parameters = Column(JSON, nullable=True, default=list)
    chain_of_thought = Column(JSON, nullable=True, default=dict)
    # Part 5D: marks questions that followed a Give Up nudge
    post_nudge = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("StudentSession", back_populates="question_logs")
    student = relationship("Student")


class GiveUpEvent(Base):
    """
    Recorded each time a student uses the Give Up button (Part 5C step 8).
    """
    __tablename__ = "give_up_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("student_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    covered_topics = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    uncovered_topics = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    nudge_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    session = relationship("StudentSession", back_populates="give_up_events")
    student = relationship("Student")
