import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
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


class TestConfig(Base):
    __tablename__ = "test_config"

    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), primary_key=True)
    question_quota = Column(Integer, nullable=False, default=5)
    max_marks = Column(Integer, nullable=False, default=50)
    penalty_off_topic = Column(Integer, nullable=False, default=-2)
    penalty_duplicate = Column(Integer, nullable=False, default=-5)
    penalty_fixation = Column(Integer, nullable=False, default=-1)

    test = relationship("Test", back_populates="config")


class TestMaterial(Base):
    __tablename__ = "test_materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    content_hash = Column(String(64), nullable=False, unique=True, index=True)
    token_count = Column(Integer, nullable=False, default=0)
    topic_outline = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    test = relationship("Test", back_populates="materials")


class StudentSession(Base):
    __tablename__ = "student_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True)
    student_name = Column(String(255), nullable=False)
    total_raw_score = Column(Float, nullable=False, default=0.0)
    final_clamped_score = Column(Float, nullable=False, default=0.0)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    test = relationship("Test", back_populates="sessions")
    question_logs = relationship("QuestionLog", back_populates="session", cascade="all, delete-orphan")


class QuestionLog(Base):
    __tablename__ = "question_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("student_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    r_score = Column(Float, nullable=False)
    b_score = Column(Integer, nullable=False)
    d_score = Column(Integer, nullable=False)
    momentum_bonus = Column(Integer, nullable=False, default=0)
    topic_fixation_penalty = Column(Integer, nullable=False, default=0)
    penalties_applied = Column(JSON, nullable=False, default=dict)
    feedback = Column(Text, nullable=False)
    final_question_score = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("StudentSession", back_populates="question_logs")
