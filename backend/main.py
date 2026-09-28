"""Main FastAPI application entrypoint.
Mounts interview and reports routers, initializes DB schema, and configures CORS.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings, check_and_log_mock_status
from app.db.database import client
from app.interview.router import router as interview_router
from app.reports.router import router as reports_router
from app.proctoring.router import router as proctoring_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Verify MongoDB connection
    try:
        client.admin.command("ping")
    except Exception as e:
        import logging
        logging.getLogger("ai_interviewer").error(f"Failed to connect to MongoDB: {e}")
    # 2. Check and log loud warning if Mock Mode is active
    check_and_log_mock_status()
    yield
    # Shutdown logic if needed

app = FastAPI(
    title="AI Interviewer API",
    description="AI Interviewer Platform API",
    version="0.3.0",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles

# Ensure upload directories exist and mount static files route
os.makedirs(settings.RECORDINGS_DIR, exist_ok=True)
uploads_dir = Path(settings.BACKEND_DIR) / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# Mount Domain Routers (Both /api prefix and root for flexibility)
app.include_router(interview_router, prefix="/api", tags=["Interview"])
app.include_router(reports_router, prefix="/api", tags=["Reports"])
app.include_router(proctoring_router, prefix="/api", tags=["Proctoring"])

# Root routes for direct access without /api prefix
app.include_router(interview_router, tags=["Interview Root"])
app.include_router(reports_router, tags=["Reports Root"])
app.include_router(proctoring_router, tags=["Proctoring Root"])

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "ai-interviewer-backend", "project": settings.PROJECT_NAME}
