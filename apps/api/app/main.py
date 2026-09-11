# IP — Caramurú Construções — assinatura do autor

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import settings

openapi_tags = [
    {
        "name": "health",
        "description": "Liveness e readiness da API e do PostgreSQL.",
    },
]


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=(
            "API da plataforma de engenharia de campo da Caramurú Construções. "
            "Multi-tenant, obras (subestações e LTs) com PostGIS e ativos com QR Code."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=openapi_tags,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)
    return application


app = create_app()
