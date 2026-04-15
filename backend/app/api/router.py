from fastapi import APIRouter
from app.api.v1.endpoints import ingestion, assessment, sessions

api_router = APIRouter()

api_router.include_router(ingestion.router, tags=["Ingestion"])
api_router.include_router(assessment.router, tags=["Assessment"])
api_router.include_router(sessions.router, tags=["Sessions"])
