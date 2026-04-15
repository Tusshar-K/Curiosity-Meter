from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.domain import SessionMaterialSummary, SessionReportResponse, StartSessionRequest, StartSessionResponse
from app.services.db_service import db_service

router = APIRouter()


@router.post("/sessions/start", response_model=StartSessionResponse)
async def start_session(payload: StartSessionRequest, db: Session = Depends(get_db)):
    test = db_service.get_test_by_id(db, payload.test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    session = db_service.start_student_session(
        db=db,
        test_id=payload.test_id,
        student_name=payload.student_name,
    )

    quota = test.config.question_quota if test.config else 5
    return StartSessionResponse(
        session_id=str(session.id),
        test_id=str(test.id),
        subject_name=test.subject_name,
        question_quota=quota,
        materials=[
            SessionMaterialSummary(
                id=str(material.id),
                file_name=material.file_name,
                token_count=material.token_count,
                topic_outline=list(material.topic_outline or []),
            )
            for material in sorted(test.materials, key=lambda item: item.created_at)
        ],
    )


@router.get("/sessions/{session_id}/report", response_model=SessionReportResponse)
async def get_session_report(session_id: str, db: Session = Depends(get_db)):
    try:
        report = db_service.get_session_report(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return SessionReportResponse(**report)
