"""
The contextual-judgment leg of the hybrid score: Gemini (free tier)
reads the resume and job description together and judges fit the way a
human reviewer would — e.g. "this candidate lists Python but their
projects are all data-entry scripts, not backend services" — something
keyword overlap and embedding similarity can't catch on their own.

Free API key, no card required (https://aistudio.google.com/apikey).
If no key is configured, the model name is wrong, or the call fails, the
result has score=None and an "error" string. It is NOT replaced with a
neutral placeholder: the scorer excludes the leg and flags the result, so a
broken LLM can never quietly turn every candidate into a 50.
"""
import logging
import math

from app.services.gemini_client import GeminiUnavailableError, chat_json

logger = logging.getLogger(__name__)

_SCORING_PROMPT = """You are an experienced technical recruiter judging how well a candidate fits a role. \
Read the resume and job description below, then return ONLY a JSON object:

{{
  "score": <0-100 integer, your holistic judgment of fit>,
  "matched_skills": ["skill the candidate genuinely demonstrates for this role", ...],
  "missing_skills": ["required skill the candidate doesn't show", ...],
  "reasoning": "2-3 sentence explanation a recruiter could read in 5 seconds"
}}

Judge based on demonstrated experience (projects, work history), not just whether a skill word appears on \
the page. A resume that lists "Python" once with no supporting project should score lower on that skill \
than one with multiple Python projects described.

Job description:
---
{job_text}
---

Resume:
---
{resume_text}
---"""


def _clean_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def _unavailable(reason: str) -> dict:
    return {
        "score": None,
        "matched_skills": [],
        "missing_skills": [],
        "reasoning": "",
        "error": reason,
    }


def llm_judgment_score(resume_text: str, job_text: str) -> dict:
    """Returns {"score": float | None, "matched_skills": [...],
    "missing_skills": [...], "reasoning": str, "error": str | None}.
    score is None whenever the LLM judgment could not be obtained."""
    try:
        data = chat_json(
            _SCORING_PROMPT.format(job_text=job_text[:8000], resume_text=resume_text[:8000])
        )
    except GeminiUnavailableError as e:
        logger.warning("LLM scoring unavailable: %s", e)
        return _unavailable(str(e))

    if not isinstance(data, dict):
        return _unavailable("Gemini returned JSON that is not an object.")
    try:
        raw = float(data["score"])
    except (KeyError, TypeError, ValueError):
        return _unavailable("Gemini's response had no numeric 'score'.")
    if math.isnan(raw) or math.isinf(raw):
        return _unavailable("Gemini returned a non-finite score.")

    score = max(0.0, min(100.0, raw))
    if score != raw:
        logger.warning("LLM score %s was outside 0-100; clamped to %s", raw, score)

    return {
        "score": score,
        "matched_skills": _clean_list(data.get("matched_skills")),
        "missing_skills": _clean_list(data.get("missing_skills")),
        "reasoning": str(data.get("reasoning") or ""),
        "error": None,
    }
