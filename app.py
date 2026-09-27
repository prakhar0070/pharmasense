"""
Stage 7: Demo UI.

A minimal FastAPI backend exposing the router as a single /ask endpoint,
serving a simple static chat page. Run with:
    python -m uvicorn app:app --reload

Then open http://127.0.0.1:8000 in your browser.
"""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uuid

from router import route

app = FastAPI(title="PharmaSense AI")

app.mount("/static", StaticFiles(directory="static"), name="static")


class Question(BaseModel):
    question: str


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.post("/ask")
def ask(payload: Question):
    session_id = str(uuid.uuid4())[:8]
    response = route(payload.question, session_id=session_id)

    # Normalize whatever the router returns into a plain string for the UI
    result = response.get("result")
    if isinstance(result, str):
        answer_text = result
    else:
        answer_text = str(result)

    return {
        "agent": response.get("agent"),
        "tool_used": response.get("tool_used"),
        "answer": answer_text,
        "session_id": session_id,
    }


@app.get("/health")
def health():
    return {"status": "ok"}
