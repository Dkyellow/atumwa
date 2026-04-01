"""
Atumwa Delivery Bot — FastAPI application entry point.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import create_all_tables
from app.routers import webhook

logging.basicConfig(
    level=logging.DEBUG if settings.app_env == "development" else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

app = FastAPI(
    title="Atumwa Delivery Bot",
    description="WhatsApp-first delivery service for Harare, Zimbabwe 🇿🇼",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook.router)


@app.on_event("startup")
async def startup():
    logger = logging.getLogger(__name__)
    try:
        await create_all_tables()
        logger.info("✅ Database tables ready")
    except Exception as e:
        logger.error("❌ Database connection failed: %s", e)
        logger.error("Check your DATABASE_URL environment variable on Render.")
        raise  # still exit so Render shows the error clearly
    logger.info("🛵 Atumwa bot is running!")


@app.get("/")
async def health():
    return {"status": "ok", "service": "Atumwa Delivery Bot 🛵"}
