"""Combines health, session, Responses proxy, and call-center routes into the FastAPI app."""
from fastapi import APIRouter

from app.api.routes.callcenter import router as callcenter_router
from app.api.routes.health import router as health_router
from app.api.routes.responses import router as responses_router
from app.api.routes.session import router as session_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(session_router, tags=["session"])
api_router.include_router(responses_router, tags=["responses"])
api_router.include_router(callcenter_router, prefix="/api/v1/callcenter", tags=["callcenter"])
