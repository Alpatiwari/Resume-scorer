"""
The contextual-judgment leg of the hybrid score: Gemini (free tier)
reads the resume and job description together and judges fit the way a
human reviewer would — e.g. "this candidate lists Python but their
projects are all data-entry scripts, not backend services" — something
keyword overlap and embedding similarity can't catch on their own.

Free API key, no card required (https://aistudio.google.com/apikey).
Falls back to a neutral score (with an explanatory note) if no key is
configured or the call fails, so the rest of the hybrid score still
works without it.
"""
from app.services.gemini_client import GeminiUnavailableError, chat_json

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


def llm_judgment_score(resume_text: str, job_text: str) -> dict:
    """Returns {"score": float, "matched_skills": [...], "missing_skills": [...], "reasoning": str}."""
    try:
        data = chat_json(
            _SCORING_PROMPT.format(job_text=job_text[:8000], resume_text=resume_text[:8000])
        )
        return {
            "score": float(data.get("score", 50.0)),
            "matched_skills": data.get("matched_skills", []),
            "missing_skills": data.get("missing_skills", []),
            "reasoning": data.get("reasoning", ""),
        }
    except GeminiUnavailableError as e:
        return {
            "score": 50.0,
            "matched_skills": [],
            "missing_skills": [],
            "reasoning": f"LLM scoring skipped — {e}. This is a neutral placeholder score, not a real judgment.",
        }
