
import json
from functools import lru_cache

from app.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_MS

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # google-genai package not installed yet
    genai = None
    genai_types = None


class GeminiUnavailableError(Exception):
    """Raised when no API key is configured, the call fails, or the
    response wasn't valid JSON. Callers should catch this and fall back
    to a non-LLM result rather than letting the whole request fail."""


@lru_cache(maxsize=1)
def _get_client():
    """Client is expensive-ish to construct and safe to reuse across
    calls/threads, so build it once instead of per-request. Also where
    the per-call timeout is configured, so a single slow/hanging Gemini
    call can never stall an entire scoring batch indefinitely."""
    return genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=genai_types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
    )


def chat_json(prompt: str) -> dict:
    """Sends a single-turn prompt to Gemini and returns the parsed JSON
    response. Raises GeminiUnavailableError on any failure (no key, bad
    network, invalid JSON, timeout, etc.) so callers can decide how to
    degrade gracefully. Bounded by GEMINI_TIMEOUT_MS — never hangs
    forever."""
    if genai is None:
        raise GeminiUnavailableError(
            "The 'google-genai' package isn't installed. Run: pip install google-genai"
        )
    if not GEMINI_API_KEY:
        raise GeminiUnavailableError(
            "GEMINI_API_KEY isn't set. Get a free key at "
            "https://aistudio.google.com/apikey and export it as GEMINI_API_KEY."
        )

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,  # consistent extraction, not creative
            ),
        )
        return json.loads(response.text)
    except GeminiUnavailableError:
        raise
    except Exception as e:
        raise GeminiUnavailableError(
            f"Gemini call failed with model '{GEMINI_MODEL}' "
            f"({e.__class__.__name__}: {e}). Check GEMINI_API_KEY and your network."
        ) from e
