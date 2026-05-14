from __future__ import annotations

import csv
from pathlib import Path

from tqdm import tqdm

from rag.config import CHROMA_DIR, COLLECTION_NAME
from rag.embeddings import chroma_sentence_transformer_ef
from rag.metadata import month_to_season, parse_year_month


def _get_collection(reset: bool):
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = chroma_sentence_transformer_ef()
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_csv(csv_path: Path, *, reset: bool = False, batch_size: int = 256) -> int:
    collection = _get_collection(reset=reset)
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    def flush():
        nonlocal ids, documents, metadatas
        if not ids:
            return
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        ids, documents, metadatas = [], [], []

    with csv_path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for idx, row in enumerate(tqdm(rows, desc="Indexing reviews")):
        rid = str(row["Review_ID"]).strip()
        text = (row.get("Review_Text") or "").strip()
        if not text:
            continue
        branch = (row.get("Branch") or "").strip()
        loc = (row.get("Reviewer_Location") or "").strip()
        rating = int(float(row["Rating"]))
        ym = (row.get("Year_Month") or "").strip()
        year, month = parse_year_month(ym)
        season = month_to_season(month)
        doc = (
            f"Branch: {branch}. Reviewer location: {loc}. "
            f"Visit: {ym}. Rating: {rating}/5. Season (NH): {season}.\n\n{text}"
        )
        meta = {
            "review_id": rid,
            "branch": branch,
            "reviewer_location": loc,
            "rating": rating,
            "year": year,
            "month": month,
            "year_month": ym,
            "season": season,
        }
        ids.append(f"{rid}-{idx}")
        documents.append(doc)
        metadatas.append(meta)
        if len(ids) >= batch_size:
            flush()
    flush()
    return collection.count()
