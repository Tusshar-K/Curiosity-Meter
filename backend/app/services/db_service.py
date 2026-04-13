from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from redis.asyncio import Redis
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.models import RawDocument, Base
from app.db.session import engine
import asyncio
import uuid

class DBService:
    def __init__(self):
        # Initialize Database schemas
        Base.metadata.create_all(bind=engine)
        
        # Connect to Redis
        self.redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        
        # Try to connect to Qdrant, fail gracefully if container isn't up
        try:
            self.qdrant = QdrantClient(url=settings.QDRANT_URL)
            self.collection_name = "curiosity_chunks_3072"
            
            # Check if collection exists, if not, create it
            collections = self.qdrant.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                self.qdrant.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
                )
        except Exception as e:
            print(f"Warning: Qdrant connection failed: {e}")
            self.qdrant = None

    def save_raw_text(self, db: Session, text: str, source: str, token_count: int):
        doc = RawDocument(
            source_name=source,
            content=text,
            token_count=token_count
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc

    def get_all_documents(self, db: Session):
        return db.query(RawDocument).all()

    async def store_chunk_vectors(self, chunks: list[str], vectors: list[list[float]], source: str):
        if not self.qdrant:
            raise Exception("Qdrant database is not initialized.")
            
        points = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            if not vector: continue
            
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"source": source, "index": i, "content": chunk}
            )
            points.append(point)
            
        self.qdrant.upsert(
            collection_name=self.collection_name,
            points=points
        )

    async def search_vectors(self, query_vector: list[float], top_k: int = 3) -> list[str]:
        if not self.qdrant:
            return []
            
        search_result = self.qdrant.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=top_k
        )
        # return the raw text chunks
        return [hit.payload.get("content", "") for hit in search_result]

    async def get_session_questions(self, session_id: str) -> list[str]:
        # Fetch the list of questions previously asked in this session (Max 50 to avoid bloat)
        key = f"session:{session_id}:questions"
        questions = await self.redis.lrange(key, 0, 50)
        return questions

    async def save_session_question(self, session_id: str, question: str):
        key = f"session:{session_id}:questions"
        await self.redis.lpush(key, question)
        # expire the session list after 2 hours
        await self.redis.expire(key, 7200) 

db_service = DBService()
