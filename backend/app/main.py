from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import search

app = FastAPI(title="Lead Project API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)


@app.get("/api/ping")
def ping():
    return {"status": "ok", "message": "Backend is alive"}