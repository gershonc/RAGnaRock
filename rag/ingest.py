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
    # Fix 2: stream rows (no list(reader)) and isolate per-row failures so
    # one bad Year_Month / Rating can't abort a 42k-row ingest.
    collection = _get_collection(reset=reset)
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    skipped_empty = 0
    skipped_bad = 0

    def flush():
        nonlocal ids, documents, metadatas
        if not ids:
            return
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        ids, documents, metadatas = [], [], []

    try:
        with csv_path.open(newline="", encoding="utf-8", errors="replace") as _f:
            total = max(sum(1 for _ in _f) - 1, 0)
    except OSError:
        total = 0

    with csv_path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(tqdm(reader, desc="Indexing reviews", total=total or None)):
            try:
                rid = str(row.get("Review_ID") or f"row-{idx}").strip() or f"row-{idx}"
                text = (row.get("Review_Text") or "").strip()
                if not text:
                    skipped_empty += 1
                    continue
                branch = (row.get("Branch") or "").strip()
                loc = (row.get("Reviewer_Location") or "").strip()
                try:
                    rating = int(float(str(row.get("Rating") or 0).strip() or 0))
                except (TypeError, ValueError):
                    rating = 0
                ym = (row.get("Year_Month") or "").strip()
                try:
                    year, month = parse_year_month(ym)
                except (ValueError, TypeError, AttributeError):
                    year, month = 0, 0
                # Fix 4: park-local season (HK summer includes Sep).
                season = month_to_season(month, branch or None)
                doc = (
                    f"Branch: {branch}. Reviewer location: {loc}. "
                    f"Visit: {ym}. Rating: {rating}/5. Season (park-local): {season}.\n\n{text}"
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
            except Exception:
                skipped_bad += 1
                continue
            ids.append(f"{rid}-{idx}")
            documents.append(doc)
            metadatas.append(meta)
            if len(ids) >= batch_size:
                flush()
    flush()
    if skipped_empty or skipped_bad:
        print(f"Skipped {skipped_empty} empty + {skipped_bad} malformed rows.")
    return collection.count()
