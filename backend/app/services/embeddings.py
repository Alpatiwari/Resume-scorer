import threading

from app.config import EMBEDDING_MODEL

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


def semantic_similarity_score(resume_text: str, job_text: str) -> float:
    try:
        model = _get_model()
    except Exception:
        return 0.0

    import numpy as np

    with _model_lock:
        embeddings = model.encode([resume_text[:8000], job_text[:8000]])
    a, b = embeddings[0], embeddings[1]
    cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
    return max(0.0, min(1.0, cosine)) * 100