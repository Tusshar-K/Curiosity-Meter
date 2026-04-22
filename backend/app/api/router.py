from fastapi import APIRouter
from app.api.v1.endpoints import ingestion, assessment, sessions, give_up

api_router = APIRouter()

api_router.include_router(ingestion.router, tags=["Ingestion"])
api_router.include_router(assessment.router, tags=["Assessment"])
api_router.include_router(sessions.router, tags=["Sessions"])
api_router.include_router(give_up.router, tags=["Give Up"])
