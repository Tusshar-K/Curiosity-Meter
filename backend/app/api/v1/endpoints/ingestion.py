import hashlib
import importlib
import logging
import re

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.domain import IngestionResponse
from app.services.db_service import db_service
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)
router = APIRouter()

try:
    tiktoken = importlib.import_module("tiktoken")
    _ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:
    _ENCODER = None


def count_tokens(text: str) -> int:
    if _ENCODER:
        return len(_ENCODER.encode(text))
    return len(text.split())


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be larger than overlap")

    if _ENCODER:
        tokens = _ENCODER.encode(text)
        chunks = []
        start = 0
        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunks.append(_ENCODER.decode(chunk_tokens))
            if end == len(tokens):
                break
            start = end - overlap
        return chunks

    words = re.split(r"\s+", text.strip())
    if not words or words == [""]:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(0, end - overlap)
    return chunks


def extract_topic_outline(text: str, max_topics: int = 8) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(raw_value: str):
        candidate = re.sub(r"\s+", " ", raw_value).strip(" \t-*•:;")
        candidate = re.sub(r"^\d+(?:\.\d+)*[\)\.-:]?\s*", "", candidate).strip()
        if not candidate:
            return
        if len(candidate.split()) > 10 or len(candidate) > 90:
            return
        normalized = candidate.lower()
        if normalized in seen:
            return
        seen.add(normalized)
        candidates.append(candidate)

    for line in text.splitlines():
        stripped = re.sub(r"\s+", " ", line).strip()
        if not stripped:
            continue

        if stripped.startswith(("- ", "* ", "• ")):
            add_candidate(stripped[2:])
            continue

        if re.match(r"^\d+(?:\.\d+)*[\)\.-]\s+", stripped):
            add_candidate(stripped)
            continue

        words = stripped.split()
        if len(words) <= 8 and any(char.isalpha() for char in stripped):
            title_case_score = sum(1 for word in words if word[:1].isupper())
            uppercase_score = 1 if stripped.isupper() else 0
            if title_case_score >= max(2, len(words) // 2) or uppercase_score:
                add_candidate(stripped)

        if len(candidates) >= max_topics:
            break

    if len(candidates) < 3:
        for paragraph in re.split(r"\n+", text):
            stripped = re.sub(r"\s+", " ", paragraph).strip()
            if not stripped:
                continue
            first_clause = re.split(r"[.!?]", stripped, maxsplit=1)[0].strip()
            if 3 <= len(first_clause.split()) <= 10:
                add_candidate(first_clause)
            if len(candidates) >= max_topics:
                break

    return candidates[:max_topics]


@router.post("/ingest", response_model=IngestionResponse)
async def ingest_pdf(
    file: UploadFile = File(...),
    test_id: str | None = Form(default=None),
    faculty_name: str = Form(default="Faculty"),
    subject_name: str = Form(default="General"),
    question_quota: int = Form(default=5),
    max_marks: int = Form(default=50),
    penalty_off_topic: int = Form(default=-2),
    penalty_duplicate: int = Form(default=-5),
    penalty_fixation: int = Form(default=-1),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        pages = [page.get_text() for page in doc]
        doc.close()
        full_text = "\n".join(pages).strip()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {exc}") from exc

    if not full_text:
        raise HTTPException(status_code=400, detail="No extractable text found in the PDF.")

    content_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    existing_material = db_service.get_material_by_hash(db, content_hash)
    
    skip_embedding = False
    if existing_material:
        skip_embedding = True
        token_count = existing_material.token_count
        topic_outline = existing_material.topic_outline
    else:
        token_count = count_tokens(full_text)
        topic_outline = extract_topic_outline(full_text)
        chunks = chunk_text(full_text, chunk_size=500, overlap=50)
        if not chunks:
            raise HTTPException(status_code=400, detail="Unable to chunk the extracted text.")

    test = db_service.get_or_create_test(
        db=db,
        test_id=test_id,
        faculty_name=faculty_name,
        subject_name=subject_name,
    )
    db_service.set_test_config(
        db=db,
        test=test,
        question_quota=max(1, question_quota),
        max_marks=max(1, max_marks),
        penalty_off_topic=penalty_off_topic,
        penalty_duplicate=penalty_duplicate,
        penalty_fixation=penalty_fixation,
    )
    material = db_service.create_test_material(
        db=db,
        test=test,
        file_name=file.filename,
        content_hash=content_hash,
        token_count=token_count,
    )

    material.topic_outline = list(topic_outline) if isinstance(topic_outline, list) else []
    db.commit()
    db.refresh(material)

    if not skip_embedding:
        vectors = []
        for chunk in chunks:
            vectors.append(await llm_service.embed_text(chunk))

        await db_service.store_chunk_vectors(
            test_id=str(test.id),
            material_id=str(material.id),
            content_hash=content_hash,
            chunks=chunks,
            vectors=vectors,
            source=file.filename,
        )

    db_service.set_test_active(db, test)

    logger.info(
        "Ingested material=%s test=%s tokens=%d skipped_embedding=%s",
        material.id,
        test.id,
        token_count,
        skip_embedding
    )

    return IngestionResponse(
        status="success",
        test_id=str(test.id),
        material_id=str(material.id),
        token_count=token_count,
        duplicate_material=False,
    )


@router.get("/ingest/tests")
async def get_tests(db: Session = Depends(get_db)):
    tests = db_service.get_active_tests(db)
    return {
        "tests": [
            {
                "id": str(t.id),
                "faculty_name": t.faculty_name,
                "subject_name": t.subject_name,
                "status": t.status,
                "config": {
                    "question_quota": t.config.question_quota if t.config else 5,
                    "max_marks": t.config.max_marks if t.config else 50,
                    "penalty_off_topic": -2,
                    "penalty_duplicate": -5,
                    "penalty_fixation": -1,
                },
                "materials": [
                    {
                        "id": str(m.id),
                        "file_name": m.file_name,
                        "token_count": m.token_count,
                        "topic_outline": list(m.topic_outline or []),
                    }
                    for m in t.materials
                ],
            }
            for t in tests
        ]
    }

@router.delete("/ingest/tests/{test_id}")
async def delete_test(test_id: str, db: Session = Depends(get_db)):
    success = db_service.delete_test_and_vectors(db, test_id)
    if not success:
        raise HTTPException(status_code=404, detail="Test not found")
    return {"status": "success", "message": "Test deleted successfully"}
