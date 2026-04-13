from fastapi import APIRouter
from app.api.v1.endpoints import ingestion, assessment

api_router = APIRouter()

api_router.include_router(ingestion.router, prefix="/ingestion", tags=["Ingestion"])
api_router.include_router(assessment.router, prefix="/assessment", tags=["Assessment"])
