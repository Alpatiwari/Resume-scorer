import json
import os
import time
from functools import lru_cache

from app.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_MS

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # google-genai package not installed yet
    genai = None
    genai_types = None

# Optional backup models, comma separated, e.g. in .env:
# RESUME_SCORER_GEMINI_FALLBACK_MODELS=gemini-3.6-flash
_fallbacks = [m.strip() for m in os.environ.get("RESUME_SCORER_GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()]
MODELS_TO_TRY = [GEMINI_MODEL] + [m for m in _fallbacks if m != GEMINI_MODEL]

RETRIES_PER_MODEL = 5      # attempts per model
BACKOFF_SECONDS = 3        # waits 3s, 6s, 12s, 24s between attempts


class GeminiUnavailableError(Exception):
    """Raised when no API key is configured, the call fails, or the
    response wasn't valid JSON."""


@lru_cache(maxsize=1)
def _get_client():
    return genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=genai_types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
    )


# Errors worth waiting for and trying again. 429 / RESOURCE_EXHAUSTED is the
# free tier's "too many requests per minute" answer: it clears by itself if we
# back off, so it must be retried instead of dropping the AI score.
_TEMPORARY_MARKERS = (
    "503", "UNAVAILABLE", "Timeout", "timed out",
    "429", "RESOURCE_EXHAUSTED", "rate limit", "Too Many Requests",
)


# A 429 that will NOT clear by waiting a few seconds: the daily allowance is used
# up, or this model has no free quota at all ("limit: 0"). Retrying these only
# burns ~45s per resume (over an hour for 100 resumes) and still fails.
_QUOTA_MARKERS = ("perday", "per day", "limit: 0")


def _is_temporary(msg: str) -> bool:
    lowered = msg.lower()
    if any(marker in lowered for marker in _QUOTA_MARKERS):
        return False
    return any(marker.lower() in lowered for marker in _TEMPORARY_MARKERS)


def chat_json(prompt: str) -> dict:
    if genai is None:
        raise GeminiUnavailableError(
            "The 'google-genai' package isn't installed. Run: pip install google-genai"
        )
    if not GEMINI_API_KEY:
        raise GeminiUnavailableError("GEMINI_API_KEY isn't set.")

    last_error = None
    last_model = GEMINI_MODEL
    for model in MODELS_TO_TRY:
        last_model = model
        for attempt in range(RETRIES_PER_MODEL):
            try:
                response = _get_client().models.generate_content(
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                return json.loads(response.text)
            except Exception as e:
                last_error = e
                if _is_temporary(str(e)) and attempt < RETRIES_PER_MODEL - 1:
                    time.sleep(BACKOFF_SECONDS * (2 ** attempt))
                    continue
                break  # permanent error or out of retries: next model

    raise GeminiUnavailableError(
        f"Gemini call failed with model '{last_model}' "
        f"({last_error.__class__.__name__}: {last_error}). Check GEMINI_API_KEY and your network."
    ) from last_error