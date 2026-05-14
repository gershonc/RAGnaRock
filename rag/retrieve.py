from __future__ import annotations

import json
from copy import deepcopy

import chromadb

from rag.config import CHROMA_DIR, COLLECTION_NAME
from rag.embeddings import chroma_sentence_transformer_ef
from rag.filters import QueryFilters, build_chroma_where, interpret_query


def _collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = chroma_sentence_transformer_ef()
    return client.get_collection(name=COLLECTION_NAME, embedding_function=ef)


def _relax_filters(f: QueryFilters) -> list[QueryFilters]:
    """Ordered relaxations when a strict metadata filter returns nothing."""
    chain: list[QueryFilters] = [deepcopy(f)]
    cur = chain[0]
    if f.reviewer_location:
        nxt = deepcopy(cur)
        nxt.reviewer_location = None
        nxt.relaxations = list(cur.relaxations) + ["Dropped reviewer_location filter (no hits)."]
        chain.append(nxt)
        cur = nxt
    if f.months:
        nxt = deepcopy(cur)
        nxt.months = None
        nxt.relaxations = list(cur.relaxations) + ["Dropped month/season filter (no hits)."]
        chain.append(nxt)
        cur = nxt
    if f.branch:
        nxt = deepcopy(cur)
        nxt.branch = None
        nxt.relaxations = list(cur.relaxations) + ["Dropped branch filter (no hits)."]
        chain.append(nxt)
    return chain


def retrieve(
    question: str,
    *,
    n_results: int = 20,
    filters: QueryFilters | None = None,
) -> tuple[list[dict], QueryFilters]:
    filters = filters or interpret_query(question)
    col = _collection()
    last_hits: list[dict] = []
    used = filters
    seen_where: set[str] = set()
    for candidate in _relax_filters(filters):
        where = build_chroma_where(candidate)
        key = json.dumps(where, sort_keys=True, default=str)
        if key in seen_where:
            continue
        seen_where.add(key)
        res = col.query(query_texts=[question], n_results=n_results, where=where)
        hits = _pack_results(res)
        if hits:
            last_hits = hits
            used = candidate
            break
    return last_hits, used


def _pack_results(res: dict) -> list[dict]:
    ids = res["ids"][0] if res.get("ids") else []
    docs = res["documents"][0] if res.get("documents") else []
    metas = res["metadatas"][0] if res.get("metadatas") else []
    dists = res["distances"][0] if res.get("distances") else [None] * len(ids)
    out: list[dict] = []
    for i, rid in enumerate(ids):
        out.append(
            {
                "id": rid,
                "document": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "distance": dists[i] if i < len(dists) else None,
            }
        )
    return out
