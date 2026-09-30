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
import logging
import re
from dataclasses import dataclass, field

from app.services.gemini_client import GeminiUnavailableError, chat_json
from app.services.skill_dictionary import (
    CASE_SENSITIVE_ALIASES,
    CONTEXT_PATTERNS,
    SKILL_ALIASES,
    normalize_skills,
)

logger = logging.getLogger(__name__)


@dataclass
class ResumeProfile:
    skills: list[str] = field(default_factory=list)
    experience_years: float | None = None
    education: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    # Set when the AI extraction pass failed and only regex results were used.
    llm_error: str | None = None


@dataclass
class JobRequirements:
    required_skills: list[str] = field(default_factory=list)
    nice_to_have_skills: list[str] = field(default_factory=list)
    min_experience_years: float | None = None
    key_responsibilities: list[str] = field(default_factory=list)
    llm_error: str | None = None


# ---------------------------------------------------------------------------
# Pass 1: regex + skill dictionary
# ---------------------------------------------------------------------------

_BOUNDARY_BEFORE = r"(?<![a-zA-Z0-9])"
_BOUNDARY_AFTER = r"(?![a-zA-Z0-9])"


def _find_skills_regex(text: str) -> list[str]:
    text_lower = text.lower()
    found: list[str] = []
    for canonical, aliases in SKILL_ALIASES.items():
        candidates = [a.lower() for a in aliases]
        # "Go" and "Excel" are ordinary words, so their bare name is NOT
        # matched here — only through CONTEXT_PATTERNS below.
        if canonical not in CONTEXT_PATTERNS:
            candidates.append(canonical.lower())
        for candidate in candidates:
            pattern = _BOUNDARY_BEFORE + re.escape(candidate) + _BOUNDARY_AFTER
            if re.search(pattern, text_lower):
                found.append(canonical)
                break

    # Case-sensitive aliases: "JS", "ML" only count when written that way.
    for canonical, aliases in CASE_SENSITIVE_ALIASES.items():
        if canonical in found:
            continue
        for alias in aliases:
            if re.search(_BOUNDARY_BEFORE + re.escape(alias) + _BOUNDARY_AFTER, text):
                found.append(canonical)
                break

    # Everyday-word skills ("Go", "Excel"): matched by context patterns only.
    for canonical, patterns in CONTEXT_PATTERNS.items():
        if canonical in found:
            continue
        if any(re.search(p, text, flags=re.MULTILINE) for p in patterns):
            found.append(canonical)

    return found


# --- years of experience -------------------------------------------------

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20,
}
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(_NUMBER_WORDS) + r")"
_UNIT = r"\s*\+?\s*(?:years?|yrs?)"

# "5 years of experience", "3-5 yrs experience", "five years of professional experience"
_YEARS_BEFORE = re.compile(
    _NUM + r"(?:\s*(?:-|\u2013|to)\s*" + _NUM + r")?" + _UNIT
    + r"(?:\s+of)?(?:\s+[\w/+.#&-]+){0,4}?\s+experience",
    re.IGNORECASE,
)
# "experience: 5 years", "experience of 3+ years"
_YEARS_AFTER = re.compile(
    r"experience\s*(?:of|:|-)?\s*(?:at least\s*|minimum\s*(?:of\s*)?)?" + _NUM + _UNIT,
    re.IGNORECASE,
)
# "at least 3 years", "minimum 5 years"
_YEARS_MIN = re.compile(
    r"(?:at least|minimum(?:\s+of)?|min\.?)\s*" + _NUM + _UNIT, re.IGNORECASE
)


def _to_number(token: str) -> float:
    token = token.lower()
    return float(_NUMBER_WORDS[token]) if token in _NUMBER_WORDS else float(token)


def _find_experience_years_regex(text: str) -> float | None:
    """Largest stated years-of-experience figure. For a range ("3-5 years") the
    lower bound is used. Date ranges ("2019-2024") are left to the AI pass."""
    values: list[float] = []
    for m in _YEARS_BEFORE.finditer(text):
        values.append(_to_number(m.group(1)))  # group 1 = lower bound of a range
    for pattern in (_YEARS_AFTER, _YEARS_MIN):
        for m in pattern.finditer(text):
            values.append(_to_number(m.group(1)))
    return max(values) if values else None


# --- required vs nice-to-have split of a job description ------------------

_NICE_MARKER = re.compile(
    r"nice[\s-]*to[\s-]*have|good[\s-]*to[\s-]*have|\b(?:is|are)\s+a\s+(?:plus|bonus)\b"
    r"|\ba\s+plus\b|\bbonus\b|\bpreferred\b|\bdesirable\b",
    re.IGNORECASE,
)
_NICE_HEADING = re.compile(
    r"^[\W_]*(?:nice[\s-]*to[\s-]*have|good[\s-]*to[\s-]*have|preferred(?:\s+(?:qualifications|skills|requirements))?"
    r"|bonus(?:\s+points)?|desirable|optional)\b[^\n]{0,40}$",
    re.IGNORECASE,
)
_REQUIRED_HEADING = re.compile(
    r"^[\W_]*(?:required|requirements|responsibilities|qualifications|must[\s-]*have|key skills"
    r"|what you(?:'ll| will)?|who you are|about|benefits|what we offer|skills)\b[^\n]{0,40}$",
    re.IGNORECASE,
)


def _split_job_sections(text: str) -> tuple[str, str]:
    """Splits a job description into (required_text, nice_to_have_text).

    A heading like "Nice to have:" sends the lines under it to the nice side
    until a required-style heading appears. A single sentence that says "... is
    a plus" / "preferred" / "nice to have: ..." is nice-to-have wherever it is.
    """
    required: list[str] = []
    nice: list[str] = []
    state = "required"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if len(line) < 70 and _NICE_HEADING.match(line):
            state = "nice"
        elif len(line) < 70 and _REQUIRED_HEADING.match(line):
            state = "required"
        # sentence-level marker check ("Docker is a plus." / "Nice to have: X.")
        for sentence in re.split(r"(?<=[.!?;])\s+", line):
            if _NICE_MARKER.search(sentence):
                nice.append(sentence)
            else:
                (nice if state == "nice" else required).append(sentence)
    return "\n".join(required), "\n".join(nice)


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


def _call_llm_json(prompt: str) -> tuple[dict | None, str | None]:
    """Calls Gemini. Returns (data, None) on success or (None, reason) on
    failure, so callers can fall back to regex-only results AND report that
    they did — a failed enrichment pass must be visible, not invisible."""
    try:
        data = chat_json(prompt)
    except GeminiUnavailableError as e:
        logger.warning("AI extraction unavailable, using regex only: %s", e)
        return None, str(e)
    if not isinstance(data, dict):
        return None, "Gemini returned JSON that is not an object."
    return data, None


def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def _num_or_none(value) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 and n == n else None  # rejects negatives and NaN


# ---------------------------------------------------------------------------
# Public API — merges both passes
# ---------------------------------------------------------------------------

def extract_resume_profile(text: str) -> ResumeProfile:
    regex_skills = _find_skills_regex(text)
    regex_years = _find_experience_years_regex(text)

    llm_data, llm_error = _call_llm_json(_RESUME_EXTRACTION_PROMPT.format(text=text[:12000]))

    if llm_data:
        merged_skills = sorted(normalize_skills([*regex_skills, *_str_list(llm_data.get("skills"))]))
        years = _num_or_none(llm_data.get("experience_years"))
        return ResumeProfile(
            skills=merged_skills,
            experience_years=years if years else regex_years,
            education=_str_list(llm_data.get("education")),
            projects=_str_list(llm_data.get("projects")),
            red_flags=_str_list(llm_data.get("red_flags")),
        )

    return ResumeProfile(
        skills=sorted(set(regex_skills)), experience_years=regex_years, llm_error=llm_error
    )


def extract_job_requirements(text: str) -> JobRequirements:
    required_text, nice_text = _split_job_sections(text)
    regex_required = _find_skills_regex(required_text)
    regex_nice = _find_skills_regex(nice_text)
    regex_years = _find_experience_years_regex(text)

    llm_data, llm_error = _call_llm_json(_JOB_EXTRACTION_PROMPT.format(text=text[:12000]))

    if llm_data:
        llm_required = _str_list(llm_data.get("required_skills"))
        nice = normalize_skills([*regex_nice, *_str_list(llm_data.get("nice_to_have_skills"))])
        nice_keys = {n.lower() for n in nice}
        # Skills found in the required part of the text stay required. A skill
        # only the AI called required is dropped if it is listed as nice-to-have.
        required = normalize_skills([
            *regex_required,
            *[s for s in normalize_skills(llm_required) if s.lower() not in nice_keys],
        ])
        years = _num_or_none(llm_data.get("min_experience_years"))
        return JobRequirements(
            required_skills=sorted(required),
            nice_to_have_skills=sorted(nice),
            min_experience_years=years if years else regex_years,
            key_responsibilities=_str_list(llm_data.get("key_responsibilities")),
        )

    return JobRequirements(
        required_skills=sorted(set(regex_required)),
        nice_to_have_skills=sorted(set(regex_nice) - set(regex_required)),
        min_experience_years=regex_years,
        llm_error=llm_error,
    )