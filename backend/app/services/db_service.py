import json
import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, Filter, FieldCondition, MatchValue, PointStruct, VectorParams
from redis.asyncio import Redis
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Base, QuestionLog, StudentSession, Test, TestConfig, TestMaterial
from app.db.session import engine

logger = logging.getLogger(__name__)


class DBService:
	def __init__(self):
		self.redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
		self.collection_name = "curiosity_chunks"
		self.embedding_dim = 3072

		try:
			self.qdrant = QdrantClient(url=settings.QDRANT_URL)
			self._ensure_collection()
		except Exception as exc:
			logger.warning("Qdrant connection failed: %s", exc)
			self.qdrant = None

	def _ensure_collection(self) -> None:
		collections = self.qdrant.get_collections().collections
		collection_names = [c.name for c in collections]
		if self.collection_name in collection_names:
			try:
				collection = self.qdrant.get_collection(self.collection_name)
				vectors_cfg = collection.config.params.vectors
				if hasattr(vectors_cfg, "size"):
					self.embedding_dim = int(vectors_cfg.size)
				elif isinstance(vectors_cfg, dict) and vectors_cfg:
					first_key = next(iter(vectors_cfg))
					self.embedding_dim = int(vectors_cfg[first_key].size)
				logger.info("Using existing Qdrant collection dimension: %d", self.embedding_dim)
			except Exception as exc:
				logger.warning("Could not read Qdrant collection dimension, using default %d: %s", self.embedding_dim, exc)
			return

		# Hybrid-ready shape: dense vectors in Qdrant + lexical fallback rerank in app layer.
		self.qdrant.create_collection(
			collection_name=self.collection_name,
			vectors_config=VectorParams(size=self.embedding_dim, distance=Distance.COSINE),
		)

	def _normalize_vector_dim(self, vector: list[float]) -> list[float]:
		if not vector:
			return [0.0] * self.embedding_dim
		if len(vector) == self.embedding_dim:
			return vector
		if len(vector) > self.embedding_dim:
			return vector[: self.embedding_dim]
		return vector + ([0.0] * (self.embedding_dim - len(vector)))

	def initialize_database(self):
		try:
			Base.metadata.create_all(bind=engine)
			self._apply_schema_patches()
		except Exception as exc:
			logger.warning("Database schema initialization failed: %s", exc)

	def _apply_schema_patches(self):
		# Minimal migration guard for environments without Alembic.
		with engine.begin() as conn:
			conn.execute(
				text(
					"""
					ALTER TABLE IF EXISTS test_config
					ADD COLUMN IF NOT EXISTS penalty_fixation INTEGER NOT NULL DEFAULT -1
					"""
				)
			)
			conn.execute(
				text(
					"""
					ALTER TABLE IF EXISTS test_materials
					ADD COLUMN IF NOT EXISTS topic_outline JSON NOT NULL DEFAULT '[]'
					"""
				)
			)

	def get_or_create_test(self, db: Session, test_id: str | None, faculty_name: str, subject_name: str) -> Test:
		if test_id:
			try:
				test_uuid = uuid.UUID(test_id)
			except ValueError:
				test_uuid = None
			test = db.query(Test).filter(Test.id == test_uuid).first() if test_uuid else None
			if test:
				if not test.config:
					test.config = TestConfig()
					db.commit()
					db.refresh(test)
				return test

		test = Test(faculty_name=faculty_name, subject_name=subject_name, status="draft")
		test.config = TestConfig()
		db.add(test)
		db.commit()
		db.refresh(test)
		return test

	def get_material_by_hash(self, db: Session, content_hash: str) -> TestMaterial | None:
		return db.query(TestMaterial).filter(TestMaterial.content_hash == content_hash).first()

	def create_test_material(self, db: Session, test: Test, file_name: str, content_hash: str, token_count: int) -> TestMaterial:
		material = TestMaterial(
			test_id=test.id,
			file_name=file_name,
			content_hash=content_hash,
			token_count=token_count,
		)
		db.add(material)
		db.commit()
		db.refresh(material)
		return material

	def set_test_active(self, db: Session, test: Test) -> None:
		test.status = "active"
		db.commit()

	def set_test_config(
		self,
		db: Session,
		test: Test,
		question_quota: int,
		max_marks: int,
		penalty_off_topic: int,
		penalty_duplicate: int,
		penalty_fixation: int,
	) -> None:
		if not test.config:
			test.config = TestConfig()

		test.config.question_quota = question_quota
		test.config.max_marks = max_marks
		test.config.penalty_off_topic = penalty_off_topic
		test.config.penalty_duplicate = penalty_duplicate
		test.config.penalty_fixation = penalty_fixation
		db.commit()

	async def store_chunk_vectors(self, test_id: str, material_id: str, chunks: list[str], vectors: list[list[float]], source: str):
		if not self.qdrant:
			raise RuntimeError("Qdrant database is not initialized.")

		points = []
		for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
			if not vector:
				continue
			normalized_vector = self._normalize_vector_dim(vector)

			points.append(
				PointStruct(
					id=str(uuid.uuid4()),
					vector=normalized_vector,
					payload={
						"test_id": test_id,
						"material_id": material_id,
						"source": source,
						"index": idx,
						"content": chunk,
					},
				)
			)

		if points:
			self.qdrant.upsert(collection_name=self.collection_name, points=points)

	async def search_vectors(self, test_id: str, query_vector: list[float], question_text: str, top_k: int = 5) -> list[str]:
		if not self.qdrant:
			return []

		normalized_query_vector = self._normalize_vector_dim(query_vector)

		dense_hits = self.qdrant.search(
			collection_name=self.collection_name,
			query_vector=normalized_query_vector,
			limit=max(top_k * 2, 8),
			query_filter=Filter(
				must=[
					FieldCondition(
						key="test_id",
						match=MatchValue(value=test_id),
					)
				]
			),
		)

		# Light lexical rerank to support hybrid retrieval without extra sparse-model infra.
		question_terms = {t for t in question_text.lower().split() if len(t) > 2}

		scored: list[tuple[float, str]] = []
		for hit in dense_hits:
			chunk = hit.payload.get("content", "")
			if not chunk:
				continue
			chunk_terms = {t for t in chunk.lower().split() if len(t) > 2}
			lexical = 0.0
			if question_terms and chunk_terms:
				lexical = len(question_terms.intersection(chunk_terms)) / max(len(question_terms), 1)
			score = float(hit.score) + 0.15 * lexical
			scored.append((score, chunk))

		scored.sort(key=lambda x: x[0], reverse=True)
		return [chunk for _, chunk in scored[:top_k]]

	def get_or_create_student_session(
		self,
		db: Session,
		test_id: str,
		session_id: str | None,
		student_name: str,
	) -> StudentSession:
		try:
			test_uuid = uuid.UUID(test_id)
		except ValueError as exc:
			raise ValueError("Invalid test_id") from exc

		if session_id:
			try:
				session_uuid = uuid.UUID(session_id)
			except ValueError:
				session_uuid = None
			session = db.query(StudentSession).filter(StudentSession.id == session_uuid).first() if session_uuid else None
			if session:
				return session

		session = StudentSession(test_id=test_uuid, student_name=student_name, status="active")
		db.add(session)
		db.commit()
		db.refresh(session)
		return session

	async def get_session_history(self, session_id: str) -> list[dict[str, str]]:
		key = f"session:{session_id}:history"
		rows = await self.redis.lrange(key, 0, 100)
		history: list[dict[str, str]] = []
		for row in rows:
			try:
				parsed = json.loads(row)
				if isinstance(parsed, dict):
					history.append(parsed)
			except Exception:
				continue
		return history

	async def append_session_history(self, session_id: str, question: str, feedback: str):
		key = f"session:{session_id}:history"
		payload = json.dumps({"q": question, "feedback": feedback}, ensure_ascii=True)
		await self.redis.rpush(key, payload)
		await self.redis.expire(key, 7200)

	def save_question_log(
		self,
		db: Session,
		session_id: str,
		question_text: str,
		r_score: float,
		b_score: int,
		d_score: int,
		momentum_bonus: int,
		topic_fixation_penalty: int,
		penalties_applied: dict[str, Any],
		feedback: str,
		final_question_score: float,
	) -> QuestionLog:
		log = QuestionLog(
			session_id=uuid.UUID(session_id),
			question_text=question_text,
			r_score=r_score,
			b_score=b_score,
			d_score=d_score,
			momentum_bonus=momentum_bonus,
			topic_fixation_penalty=topic_fixation_penalty,
			penalties_applied=penalties_applied,
			feedback=feedback,
			final_question_score=final_question_score,
		)
		db.add(log)
		db.commit()
		db.refresh(log)
		return log

	def update_session_scores(self, db: Session, session_id: str) -> tuple[StudentSession, int, int]:
		session = db.query(StudentSession).filter(StudentSession.id == uuid.UUID(session_id)).first()
		if not session:
			raise ValueError("Session not found")

		total_raw = (
			db.query(func.coalesce(func.sum(QuestionLog.final_question_score), 0.0))
			.filter(QuestionLog.session_id == session.id)
			.scalar()
		)
		log_count = db.query(func.count(QuestionLog.id)).filter(QuestionLog.session_id == session.id).scalar() or 0

		quota = session.test.config.question_quota if session.test and session.test.config else 5
		session.total_raw_score = float(total_raw)
		session.final_clamped_score = max(0.0, float(total_raw))
		if log_count >= quota:
			session.status = "completed"
		db.commit()
		db.refresh(session)
		return session, int(log_count), int(quota)

	def get_active_tests(self, db: Session) -> list[Test]:
		return db.query(Test).order_by(Test.created_at.desc()).all()

	def get_test_by_id(self, db: Session, test_id: str) -> Test | None:
		try:
			test_uuid = uuid.UUID(test_id)
		except ValueError:
			return None
		return db.query(Test).filter(Test.id == test_uuid).first()

	def start_student_session(self, db: Session, test_id: str, student_name: str) -> StudentSession:
		test = self.get_test_by_id(db, test_id)
		if not test:
			raise ValueError("Invalid test_id")

		session = StudentSession(test_id=test.id, student_name=student_name.strip() or "Student", status="active")
		db.add(session)
		db.commit()
		db.refresh(session)
		return session

	def get_session_report(self, db: Session, session_id: str) -> dict[str, Any]:
		try:
			session_uuid = uuid.UUID(session_id)
		except ValueError as exc:
			raise ValueError("Invalid session_id") from exc

		session = db.query(StudentSession).filter(StudentSession.id == session_uuid).first()
		if not session:
			raise ValueError("Session not found")

		updated_session, log_count, quota = self.update_session_scores(db, str(session.id))
		logs = (
			db.query(QuestionLog)
			.filter(QuestionLog.session_id == updated_session.id)
			.order_by(QuestionLog.created_at.asc())
			.all()
		)

		max_marks = updated_session.test.config.max_marks if updated_session.test and updated_session.test.config else 50
		subject_name = updated_session.test.subject_name if updated_session.test else "Unknown"

		return {
			"session_id": str(updated_session.id),
			"subject_name": subject_name,
			"final_clamped_score": round(updated_session.final_clamped_score, 2),
			"max_marks": int(max_marks),
			"total_questions": int(log_count),
			"question_quota": int(quota),
			"questions": [
				{
					"question_text": q.question_text,
					"feedback": q.feedback,
					"r_score": q.r_score,
					"b_score": q.b_score,
					"d_score": q.d_score,
					"momentum_bonus": q.momentum_bonus,
					"topic_fixation_penalty": q.topic_fixation_penalty,
					"penalties_applied": q.penalties_applied,
					"final_question_score": q.final_question_score,
				}
				for q in logs
			],
		}


db_service = DBService()
