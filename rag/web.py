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


# ---------- Chroma explorer ----------

import time as _time

_STATS_CACHE: dict = {"at": 0.0, "data": None, "name": None}


def _chroma_client():
    import chromadb

    from rag.config import CHROMA_DIR

    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def _chroma_collection(name: str):
    return _chroma_client().get_collection(name=name)


@app.get("/browse")
def browse_page():
    return FileResponse(str(WEB_DIR / "browse.html"))


@app.get("/api/collections")
def collections():
    out = []
    for col in _chroma_client().list_collections():
        try:
            n = col.count()
        except Exception:
            n = 0
        out.append({"name": col.name, "count": n, "metadata": col.metadata})
    return {"collections": out}


@app.get("/api/chroma-stats")
def chroma_stats(collection: str = COLLECTION_NAME):
    from collections import Counter

    now = _time.time()
    if (
        _STATS_CACHE["data"] is not None
        and now - _STATS_CACHE["at"] < 300
        and _STATS_CACHE["name"] == collection
    ):
        return _STATS_CACHE["data"]
    col = _chroma_collection(collection)
    # Full-scan in batches: a single unbounded get() exceeds SQLite's
    # variable limit ("too many SQL variables").
    branches: Counter = Counter()
    ratings: Counter = Counter()
    years: Counter = Counter()
    locs: Counter = Counter()
    total = col.count()
    step = 5000
    for off in range(0, total, step):
        metas = (
            col.get(limit=step, offset=off, include=["metadatas"]).get("metadatas")
            or []
        )
        for m in metas:
            branches[str(m.get("branch"))] += 1
            ratings[str(m.get("rating"))] += 1
            years[str(m.get("year"))] += 1
            locs[str(m.get("reviewer_location"))] += 1
    data = {
        "name": collection,
        "count": total,
        "branches": dict(branches.most_common()),
        "ratings": dict(sorted(ratings.items())),
        "years": dict(sorted(years.items(), key=lambda kv: (kv[0] == "0", kv[0]))),
        "top_locations": dict(locs.most_common(12)),
    }
    _STATS_CACHE.update({"at": now, "data": data, "name": collection})
    return data


@app.get("/api/browse")
def browse(
    collection: str = COLLECTION_NAME,
    limit: int = 20,
    offset: int = 0,
    q: str | None = None,
    branch: str | None = None,
    rating: int | None = None,
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    col = _chroma_collection(collection)
    clauses = []
    if branch:
        clauses.append({"branch": branch})
    if rating is not None:
        clauses.append({"rating": rating})
    where = None
    if clauses:
        where = clauses[0] if len(clauses) == 1 else {"$and": clauses}
    where_doc = {"$contains": q} if q else None
    res = col.get(
        where=where,
        where_document=where_doc,
        limit=limit,
        offset=offset,
        include=["documents", "metadatas"],
    )
    ids = res.get("ids") or []
    docs = res.get("documents") or []
    metas = res.get("metadatas") or []
    items = [
        {"id": i, "snippet": (d or "")[:400], "metadata": m}
        for i, d, m in zip(ids, docs, metas)
    ]
    return {"items": items, "limit": limit, "offset": offset, "total": col.count()}


@app.get("/api/record")
def record(collection: str = COLLECTION_NAME, id: str = "", vectors: bool = False):
    col = _chroma_collection(collection)
    include = (
        ["documents", "metadatas", "embeddings"]
        if vectors
        else ["documents", "metadatas"]
    )
    res = col.get(ids=[id], include=include)
    ids = res.get("ids") or []
    if not ids:
        return {"found": False}
    docs = res.get("documents") or [""]
    metas = res.get("metadatas") or [{}]
    out: dict = {"found": True, "id": ids[0], "document": docs[0], "metadata": metas[0]}
    if vectors:
        import math

        raw = res.get("embeddings")
        vec: list = []
        if raw is not None:
            first = raw[0]  # list or ndarray row
            if first is not None:
                vec = [float(x) for x in list(first)]
        if vec:
            out["embedding"] = vec
            out["dim"] = len(vec)
            out["norm"] = round(math.sqrt(sum(x * x for x in vec)), 4)
    return out


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
