"""
Structures raw resume/job-description text into: skills, experience years,
education, projects, red flags.

Two passes, merged:
  1. Regex + skill dictionary — fast, deterministic, no LLM needed.
     Good recall on common/standard skill names.
  2. LLM extraction (Gemini, free tier) — catches skills phrased
     differently ("built REST services in Python" -> Python, REST APIs),
     and pulls out structured fields regex can't reliably get (experience
     years, education, project relevance, employment gaps).

If GEMINI_API_KEY isn't set (or the call fails), the LLM pass is skipped
and callers fall back to regex-only results — the pipeline still works,
just less richly.
"""
import re
from dataclasses import dataclass, field

from app.services.gemini_client import GeminiUnavailableError, chat_json
from app.services.skill_dictionary import SKILL_ALIASES


@dataclass
class ResumeProfile:
    skills: list[str] = field(default_factory=list)
    experience_years: float | None = None
    education: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)


@dataclass
class JobRequirements:
    required_skills: list[str] = field(default_factory=list)
    nice_to_have_skills: list[str] = field(default_factory=list)
    min_experience_years: float | None = None
    key_responsibilities: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pass 1: regex + skill dictionary
# ---------------------------------------------------------------------------

def _find_skills_regex(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for canonical, aliases in SKILL_ALIASES.items():
        candidates = [canonical.lower(), *[a.lower() for a in aliases]]
        for candidate in candidates:
            # word-boundary match so "go" doesn't match inside "google"
            pattern = r"(?<![a-zA-Z0-9])" + re.escape(candidate) + r"(?![a-zA-Z0-9])"
            if re.search(pattern, text_lower):
                found.append(canonical)
                break
    return found


_YEARS_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\+?\s*(?:years|yrs)\s*(?:of)?\s*experience", re.IGNORECASE
)


def _find_experience_years_regex(text: str) -> float | None:
    matches = _YEARS_PATTERN.findall(text)
    if not matches:
        return None
    return max(float(m) for m in matches)


# ---------------------------------------------------------------------------
# Pass 2: LLM extraction (Gemini, free tier — no card required)
# ---------------------------------------------------------------------------

_RESUME_EXTRACTION_PROMPT = """You are extracting structured data from a resume for a screening tool. \
Read the resume text below and return ONLY a JSON object with this shape:

{{
  "skills": ["skill1", "skill2", ...],
  "experience_years": <number or null>,
  "education": ["degree, institution", ...],
  "projects": ["short description of relevant project", ...],
  "red_flags": ["e.g. unexplained employment gap, no relevant projects, etc."]
}}

Include skills even if phrased informally (e.g. "built APIs with FastAPI" implies "FastAPI", "REST APIs"). \
Estimate experience_years from work history dates if not explicitly stated. Keep lists concise (max ~15 items each).

Resume text:
---
{text}
---"""

_JOB_EXTRACTION_PROMPT = """You are extracting structured requirements from a job description for a screening tool. \
Read the job description below and return ONLY a JSON object with this shape:

{{
  "required_skills": ["skill1", "skill2", ...],
  "nice_to_have_skills": ["skill1", ...],
  "min_experience_years": <number or null>,
  "key_responsibilities": ["short phrase", ...]
}}

Job description:
---
{text}
---"""


def _call_llm_json(prompt: str) -> dict | None:
    """Calls Gemini and returns the parsed JSON response, or None if
    Gemini isn't available — so callers can gracefully fall back to
    regex-only results."""
    try:
        return chat_json(prompt)
    except GeminiUnavailableError:
        # Extraction is an enrichment layer — never let Gemini being
        # unavailable break the pipeline. The regex pass still ran.
        return None


# ---------------------------------------------------------------------------
# Public API — merges both passes
# ---------------------------------------------------------------------------

def extract_resume_profile(text: str) -> ResumeProfile:
    regex_skills = _find_skills_regex(text)
    regex_years = _find_experience_years_regex(text)

    llm_data = _call_llm_json(_RESUME_EXTRACTION_PROMPT.format(text=text[:12000]))

    if llm_data:
        merged_skills = sorted(set(regex_skills) | {s.strip() for s in llm_data.get("skills", []) if s.strip()})
        return ResumeProfile(
            skills=merged_skills,
            experience_years=llm_data.get("experience_years") or regex_years,
            education=llm_data.get("education", []),
            projects=llm_data.get("projects", []),
            red_flags=llm_data.get("red_flags", []),
        )

    return ResumeProfile(skills=sorted(set(regex_skills)), experience_years=regex_years)


def extract_job_requirements(text: str) -> JobRequirements:
    regex_skills = _find_skills_regex(text)
    regex_years = _find_experience_years_regex(text)

    llm_data = _call_llm_json(_JOB_EXTRACTION_PROMPT.format(text=text[:12000]))

    if llm_data:
        merged_required = sorted(
            set(regex_skills) | {s.strip() for s in llm_data.get("required_skills", []) if s.strip()}
        )
        return JobRequirements(
            required_skills=merged_required,
            nice_to_have_skills=llm_data.get("nice_to_have_skills", []),
            min_experience_years=llm_data.get("min_experience_years") or regex_years,
            key_responsibilities=llm_data.get("key_responsibilities", []),
        )

    return JobRequirements(required_skills=sorted(set(regex_skills)), min_experience_years=regex_years)
