import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = REPO_ROOT / "dataset" / "DisneylandReviews.csv"
CHROMA_DIR = REPO_ROOT / ".chroma"
HF_CACHE = REPO_ROOT / ".hf_cache"
HF_CACHE.mkdir(parents=True, exist_ok=True)
for _k in ("HF_HOME", "TRANSFORMERS_CACHE", "HUGGINGFACE_HUB_CACHE"):
    os.environ.setdefault(_k, str(HF_CACHE))

COLLECTION_NAME = "disneyland_reviews"
# Sentence-Transformers model id (downloads on first ingest)
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
