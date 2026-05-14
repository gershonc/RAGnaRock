from __future__ import annotations

from pathlib import Path

from rag.config import EMBEDDING_MODEL, HF_CACHE


def _model_snapshot_dirs(model_id: str) -> list[Path]:
    safe = "models--" + model_id.replace("/", "--")
    return [
        HF_CACHE / "hub" / safe / "snapshots",
        HF_CACHE / safe / "snapshots",
    ]


def model_cached_locally(model_id: str = EMBEDDING_MODEL) -> bool:
    """True if a HF snapshot exists under the repo HF cache (enables offline load)."""
    for snapshots in _model_snapshot_dirs(model_id):
        if snapshots.is_dir():
            try:
                next(snapshots.iterdir())
            except StopIteration:
                continue
            return True
    return False


def chroma_sentence_transformer_ef():
    """Chroma embedding fn; uses local_files_only when the model is already on disk."""
    from chromadb.utils import embedding_functions

    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
        local_files_only=model_cached_locally(),
    )
