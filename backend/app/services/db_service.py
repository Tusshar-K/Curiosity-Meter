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
from app.db.models import Base, Question, Student, StudentSession, Test, TestConfig, TestMaterial
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
		pass
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
		db.commit()

	async def store_chunk_vectors(self, test_id: str, material_id: str, content_hash: str, chunks: list[str], vectors: list[list[float]], source: str):
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
						"content_hash": content_hash,
						"source": source,
						"index": idx,
						"content": chunk,
					},
				)
			)

		if points:
			self.qdrant.upsert(collection_name=self.collection_name, points=points)

	async def search_vectors(self, content_hash: str, query_vector: list[float], question_text: str, top_k: int = 5) -> list[str]:
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
						key="content_hash",
						match=MatchValue(value=content_hash),
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

	def delete_test_and_vectors(self, db: Session, test_id: str) -> bool:
		try:
			test_uuid = uuid.UUID(test_id)
		except ValueError:
			return False
			
		test = db.query(Test).filter(Test.id == test_uuid).first()
		if not test:
			return False
			
		# Check if the content_hash is used by any OTHER tests
		hashes_to_check = [m.content_hash for m in test.materials]
		
		# Delete postgres test (cascades)
		db.delete(test)
		db.commit()
		
		# Now for each hash, if no test_materials remain with this hash, delete Qdrant vectors
		if self.qdrant:
			for chash in hashes_to_check:
				remaining = db.query(TestMaterial).filter(TestMaterial.content_hash == chash).first()
				if not remaining:
					logger.info(f"No more tests use content_hash {chash}, deleting vectors from Qdrant")
					self.qdrant.delete(
						collection_name=self.collection_name,
						points_selector=Filter(
							must=[
								FieldCondition(key="content_hash", match=MatchValue(value=chash))
							]
						)
					)
		return True

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

		student = self.get_or_create_student(db, student_name)
		session = StudentSession(test_id=test_uuid, student_id=student.id, student_name=student_name, status="active")
		db.add(session)
		db.commit()
		db.refresh(session)
		return session

	async def get_session_state(self, session_id: str) -> dict[str, Any]:
		key = f"session:{session_id}:state"
		data = await self.redis.get(key)
		if data:
			try:
				return json.loads(data)
			except Exception:
				pass
		# Default schema
		return {
			"session_id": session_id,
			"student_id": "",
			"current_topic": "",
			"same_topic_streak": 0,
			"is_deepening": False,
			"previous_scaffold": {
				"strategy": "",
				"parameters": []
			},
			"previous_bloom": 0,
			"previous_depth": 0,
			"bridging_bonus_total": 0,
			"question_count": 0
		}

	async def update_session_state(self, session_id: str, state: dict[str, Any]):
		key = f"session:{session_id}:state"
		payload = json.dumps(state, ensure_ascii=True)
		await self.redis.set(key, payload, ex=7200) # 2 hours TTL

	def get_or_create_student(self, db: Session, student_name: str) -> Student:
		student = db.query(Student).filter(Student.name == student_name).first()
		if not student:
			student = Student(name=student_name)
			db.add(student)
			db.commit()
			db.refresh(student)
		return student

	def save_question(
		self,
		db: Session,
		session_id: str,
		student_id: str,
		question_text: str,
		dedup_status: str,
		relevance_r: float,
		bloom_b: int,
		depth_d: int,
		bridging_bonus: int,
		composite_score: float,
		current_topic: str,
		feedback_text: str,
		scaffold_strategy: str,
		scaffold_parameters: list,
		chain_of_thought: dict,
	) -> Question:
		question = Question(
			session_id=uuid.UUID(session_id),
			student_id=uuid.UUID(student_id),
			question_text=question_text,
			dedup_status=dedup_status,
			relevance_r=relevance_r,
			bloom_b=bloom_b,
			depth_d=depth_d,
			bridging_bonus=bridging_bonus,
			composite_score=composite_score,
			current_topic=current_topic,
			feedback_text=feedback_text,
			scaffold_strategy=scaffold_strategy,
			scaffold_parameters=scaffold_parameters,
			chain_of_thought=chain_of_thought,
		)
		db.add(question)
		db.commit()
		db.refresh(question)
		return question

	def update_session_scores(self, db: Session, session_id: str) -> tuple[StudentSession, int, int]:
		session = db.query(StudentSession).filter(StudentSession.id == uuid.UUID(session_id)).first()
		if not session:
			raise ValueError("Session not found")

		total_raw = (
			db.query(func.coalesce(func.sum(Question.composite_score), 0.0))
			.filter(Question.session_id == session.id)
			.scalar()
		)
		log_count = db.query(func.count(Question.id)).filter(Question.session_id == session.id).scalar() or 0


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

		student = self.get_or_create_student(db, student_name.strip() or "Student")
		session = StudentSession(test_id=test.id, student_id=student.id, student_name=student.name, status="active")
		db.add(session)
		db.commit()
		db.refresh(session)
		return session

	async def get_session_summary(self, db: Session, session_id: str) -> dict[str, Any]:
		try:
			session_uuid = uuid.UUID(session_id)
		except ValueError as exc:
			raise ValueError("Invalid session_id") from exc

		session = db.query(StudentSession).filter(StudentSession.id == session_uuid).first()
		if not session:
			raise ValueError("Session not found")

		updated_session, log_count, quota = self.update_session_scores(db, str(session.id))
		logs = (
			db.query(Question)
			.filter(Question.session_id == updated_session.id)
			.order_by(Question.created_at.asc())
			.all()
		)

		total_bridging_bonuses = sum(q.bridging_bonus or 0 for q in logs)
		total_questions = len(logs)
		
		avg_relevance = sum(q.relevance_r or 0 for q in logs) / total_questions if total_questions > 0 else 0.0
		avg_bloom = sum(q.bloom_b or 0 for q in logs) / total_questions if total_questions > 0 else 0.0
		avg_depth = sum(q.depth_d or 0 for q in logs) / total_questions if total_questions > 0 else 0.0

		archetype = "The Seeker"
		if avg_bloom >= 5.0 and avg_depth >= 3.0:
			archetype = "The Visionary"
		elif avg_bloom >= 4.0 and total_bridging_bonuses >= 3:
			archetype = "The Connector"
		elif avg_relevance >= 0.85 and avg_bloom >= 3.0:
			archetype = "The Scholar"
		elif avg_depth >= 3.0 and avg_bloom < 4.0:
			archetype = "The Analyst"

		score_progression = [
			{"question_index": idx + 1, "composite_score": float(q.composite_score) if q.composite_score is not None else 0.0}
			for idx, q in enumerate(logs)
		]

		# Fetch final state's current_topic from DB (specifically, the last question's topic)
		current_topic = None
		if logs:
			current_topic = logs[-1].current_topic

		# Delete redis session directly
		await self.redis.delete(f"session:{session_id}:state")

		return {
			"avg_relevance": float(avg_relevance),
			"avg_bloom": float(avg_bloom),
			"avg_depth": float(avg_depth),
			"total_bridging_bonuses": int(total_bridging_bonuses),
			"total_questions": int(total_questions),
			"score_progression": score_progression,
			"archetype": archetype,
			"current_topic": current_topic
		}


	async def get_session_report(self, db: Session, session_id: str) -> dict[str, Any]:
		try:
			session_uuid = uuid.UUID(session_id)
		except ValueError as exc:
			raise ValueError("Invalid session_id") from exc

		session = db.query(StudentSession).filter(StudentSession.id == session_uuid).first()
		if not session:
			raise ValueError("Session not found")

		self.update_session_scores(db, str(session.id))
		logs = (
			db.query(Question)
			.filter(Question.session_id == session.id)
			.order_by(Question.created_at.asc())
			.all()
		)
		
		q_items = []
		for q in logs:
			q_items.append({
				"question_text": q.question_text,
				"feedback": q.feedback_text or "",
				"r_score": float(q.relevance_r) if q.relevance_r is not None else 0.0,
				"b_score": int(q.bloom_b) if q.bloom_b is not None else 0,
				"d_score": int(q.depth_d) if q.depth_d is not None else 0,
				"momentum_bonus": int(q.bridging_bonus) if q.bridging_bonus is not None else 0,
				"topic_fixation_penalty": 0,
				"penalties_applied": {},
				"final_question_score": float(q.composite_score) if q.composite_score is not None else 0.0
			})
			
		quota = session.test.config.question_quota if session.test and session.test.config else 5
		max_marks = session.test.config.max_marks if session.test and session.test.config else 50
		subject_name = session.test.subject_name if session.test else "Unknown"
		
		await self.redis.delete(f"session:{session_id}:state")
		
		return {
			"session_id": str(session.id),
			"subject_name": subject_name,
			"final_clamped_score": float(session.final_clamped_score),
			"max_marks": max_marks,
			"total_questions": len(logs),
			"question_quota": quota,
			"questions": q_items
		}

db_service = DBService()
