from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag.answer import answer_question
from rag.config import COLLECTION_NAME
from rag.filters import interpret_query
from rag.retrieve import retrieve

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = REPO_ROOT / "web"

app = FastAPI(title="RAGnaRock")

if WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    k: int = Field(default=10, ge=3, le=30)
    model: str | None = None


@app.get("/")
def index():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/stats")
def stats():
    count = 0
    try:
        import chromadb

        from rag.config import CHROMA_DIR

        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        col = client.get_collection(name=COLLECTION_NAME)
        count = col.count()
    except Exception:
        count = 0
    return {
        "reviews": count,
        "branches": ["Disneyland_California", "Disneyland_Paris", "Disneyland_HongKong"],
        "local_models": [
            "qwen/qwen3.5-9b",
            "qwen/qwen3.8-27b",
            "qwen/qwen3.6-35b-a3b",
            "meta/muse-glimmer",
        ],
        "default_model": os.environ.get("OPENAI_MODEL", "qwen/qwen3.5-9b"),
        "llm_configured": bool(os.environ.get("OPENAI_API_KEY")),
    }


@app.get("/api/filters")
def preview_filters(q: str):
    f = interpret_query(q)
    return {
        "branch": f.branch,
        "reviewer_location": f.reviewer_location,
        "months": f.months,
        "years": f.years,
    }


@app.post("/api/ask")
def ask(req: AskRequest):
    import time

    t0 = time.perf_counter()
    hits, used = retrieve(req.question, n_results=req.k)
    llm_metrics: dict = {}
    answer = answer_question(req.question, hits, used, model=req.model, metrics=llm_metrics)
    total = round(time.perf_counter() - t0, 1)
    llm_failed = answer.startswith("LLM answer failed") or answer.startswith(
        "Open-ended synthesis needs an LLM"
    )
    cards = []
    for h in hits[:12]:
        m = h.get("metadata") or {}
        doc = h.get("document") or ""
        body = doc.split("\n\n", 1)[1] if "\n\n" in doc else doc
        cards.append(
            {
                "review_id": m.get("review_id"),
                "branch": m.get("branch"),
                "reviewer_location": m.get("reviewer_location"),
                "year_month": m.get("year_month"),
                "rating": m.get("rating"),
                "snippet": body[:1000],
                "distance": h.get("distance"),
            }
        )
    return {
        "answer": answer,
        "llm_failed": llm_failed,
        "metrics": {
            "llm_used": not llm_failed and bool(llm_metrics),
            "model": llm_metrics.get("model"),
            "completion_tokens": llm_metrics.get("completion_tokens", 0),
            "seconds": llm_metrics.get("seconds", 0),
            "tok_per_sec": llm_metrics.get("tok_per_sec", 0),
            "total_seconds": total,
        },
        "filters": {
            "branch": used.branch,
            "reviewer_location": used.reviewer_location,
            "months": used.months,
            "years": used.years,
            "relaxations": used.relaxations,
        },
        "hits": cards,
        "count": len(hits),
    }
