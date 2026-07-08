from app.logging_config import setup_logging

setup_logging()

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import search, business

logger = logging.getLogger(__name__)

app = FastAPI(title="Lead Project API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)
app.include_router(business.router)


@app.on_event("startup")
def on_startup():
    logger.info("Backend starting up — CORS allowed for http://localhost:5173")


@app.get("/api/ping")
def ping():
    logger.info("Ping received")
    return {"status": "ok", "message": "Backend is alive"}