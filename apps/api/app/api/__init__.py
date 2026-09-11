# IP — Caramurú Construções — assinatura do autor

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.safety import router as safety_router
from app.api.sync import router as sync_router
from app.api.uploads import router as uploads_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(sync_router)
api_router.include_router(safety_router)
api_router.include_router(uploads_router)
