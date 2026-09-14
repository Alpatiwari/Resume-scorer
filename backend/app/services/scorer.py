"""
Combines the three scoring legs (see docs section 3 — "hybrid scoring"):

  - skill_overlap: % of the job's required skills the candidate's
    extracted profile actually shows.
  - embedding: semantic similarity between resume and JD text.
  - llm: an LLM's holistic, context-aware judgment.

into one weighted 0-100 final score, plus an explanation a recruiter can
read in a few seconds: matched skills, missing skills, red flags.

Weights live in config.SCORE_WEIGHTS so they're easy to tune without
touching this logic.
"""
from dataclasses import dataclass, field

from app.config import SCORE_WEIGHTS
from app.services.embeddings import semantic_similarity_score
from app.services.llm_scorer import llm_judgment_score
from app.services.nlp_extractor import JobRequirements, ResumeProfile, extract_resume_profile


@dataclass
class ScoreResult:
    resume_id: str
    final_score: float
    skill_overlap_score: float
    embedding_score: float
    llm_score: float
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    reasoning: str = ""


def _skill_overlap_score(resume_skills: list[str], required_skills: list[str]) -> tuple[float, list[str], list[str]]:
    if not required_skills:
        return 0.0, [], []

    # Preserve original casing (e.g. "AWS", "FastAPI") by matching
    # case-insensitively but keeping the required_skills list's own
    # capitalization for display, rather than lower/title-casing it.
    resume_lower = {s.lower() for s in resume_skills}
    required_lower_to_original = {s.lower(): s for s in required_skills}

    matched = sorted(orig for lower, orig in required_lower_to_original.items() if lower in resume_lower)
    missing = sorted(orig for lower, orig in required_lower_to_original.items() if lower not in resume_lower)
    score = (len(matched) / len(required_skills)) * 100
    return score, matched, missing


def score_resume(
    resume_id: str,
    resume_text: str,
    job_text: str,
    job_requirements: JobRequirements,
    resume_profile: ResumeProfile | None = None,
) -> ScoreResult:
    """Scores a single resume against a job. Pass a pre-computed
    resume_profile if you already extracted it (e.g. at upload time) to
    avoid a redundant LLM extraction call."""
    profile = resume_profile or extract_resume_profile(resume_text)

    skill_score, matched_from_dict, missing_from_dict = _skill_overlap_score(
        profile.skills, job_requirements.required_skills
    )
    embed_score = semantic_similarity_score(resume_text, job_text)
    llm_result = llm_judgment_score(resume_text, job_text)

    weights = SCORE_WEIGHTS
    final = (
        skill_score * weights["skill_overlap"]
        + embed_score * weights["embedding"]
        + llm_result["score"] * weights["llm"]
    )

    # Prefer the LLM's matched/missing lists when available (it reasons
    # about demonstrated experience, not just word presence) and fall back
    # to the dictionary-based overlap otherwise.
    matched = llm_result["matched_skills"] or matched_from_dict
    missing = llm_result["missing_skills"] or missing_from_dict

    return ScoreResult(
        resume_id=resume_id,
        final_score=round(final, 1),
        skill_overlap_score=round(skill_score, 1),
        embedding_score=round(embed_score, 1),
        llm_score=round(llm_result["score"], 1),
        matched_skills=matched,
        missing_skills=missing,
        red_flags=profile.red_flags,
        reasoning=llm_result["reasoning"],
    )
