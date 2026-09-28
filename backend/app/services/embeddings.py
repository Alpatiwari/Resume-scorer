import logging
import threading

from app.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_model_lock = threading.Lock()
_model = None


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    return _model


def semantic_similarity_score(resume_text: str, job_text: str) -> float | None:
    """Cosine similarity of resume vs job text, scaled to 0-100.

    Returns None (NOT 0) if the embedding model can't load or run. A 0 here
    would look like "this candidate is semantically unrelated" and silently
    drag their score down; None tells the scorer this leg is unavailable.
    """
    try:
        import numpy as np

        model = _get_model()
        with _model_lock:
            embeddings = model.encode([resume_text[:8000], job_text[:8000]])
        a, b = embeddings[0], embeddings[1]
        cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
    except Exception:
        logger.exception("Embedding similarity failed (model '%s')", EMBEDDING_MODEL)
        return None
    return max(0.0, min(1.0, cosine)) * 100
