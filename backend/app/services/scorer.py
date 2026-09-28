"""
Combines the three scoring legs (see docs section 3 — "hybrid scoring"):

  - skill_overlap: % of the job's required skills the candidate's
    extracted profile actually shows.
  - embedding: semantic similarity between resume and JD text.
  - llm: an LLM's holistic, context-aware judgment.

into one weighted 0-100 final score, plus an explanation a recruiter can
read in a few seconds: matched skills, missing skills, red flags.

A leg that can't be computed is None, never a made-up number. It is left out
of the weighted total (the remaining weights are renormalised) and a warning
is attached to the result so the recruiter can see the score is degraded.
If NO leg can be computed, ScoringError is raised.

Weights live in config.SCORE_WEIGHTS so they're easy to tune without
touching this logic.
"""
from dataclasses import dataclass, field

from app.config import SCORE_WEIGHTS
from app.services.embeddings import semantic_similarity_score
from app.services.llm_scorer import llm_judgment_score
from app.services.nlp_extractor import JobRequirements, ResumeProfile, extract_resume_profile


class ScoringError(Exception):
    """This resume could not be scored at all (no usable scoring leg)."""


@dataclass
class ScoreResult:
    resume_id: str
    final_score: float
    skill_overlap_score: float | None
    embedding_score: float | None
    llm_score: float | None
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    reasoning: str = ""
    # Human-readable notes on anything that degraded this score.
    warnings: list[str] = field(default_factory=list)
    llm_unavailable: bool = False
    llm_error: str | None = None


def _short(text: str | None, limit: int = 220) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _skill_overlap_score(
    resume_skills: list[str], required_skills: list[str]
) -> tuple[float | None, list[str], list[str]]:
    if not required_skills:
        # Nothing to overlap with. That's "not applicable", not "0% match".
        return None, [], []

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
    if not resume_text or not resume_text.strip():
        raise ScoringError("Resume has no extracted text to score.")

    warnings: list[str] = []

    profile = resume_profile or extract_resume_profile(resume_text)
    if profile.llm_error:
        warnings.append(
            "Skills were found by keyword matching only — AI profile extraction failed "
            f"({_short(profile.llm_error)})."
        )
    if job_requirements.llm_error:
        warnings.append(
            "The job's required skills came from keyword matching only — AI extraction failed "
            f"({_short(job_requirements.llm_error)})."
        )

    skill_score, matched_from_dict, missing_from_dict = _skill_overlap_score(
        profile.skills, job_requirements.required_skills
    )
    embed_score = semantic_similarity_score(resume_text, job_text)
    llm_result = llm_judgment_score(resume_text, job_text)
    llm_score = llm_result["score"]

    if skill_score is None:
        warnings.append("No required skills were detected in the job description, so skill overlap was not counted.")
    if embed_score is None:
        warnings.append("Semantic similarity was unavailable (embedding model failed), so it was not counted.")
    if llm_score is None:
        warnings.append(
            f"AI judgment was unavailable ({_short(llm_result['error'])}), so it was not counted. "
            "This score is based on the remaining methods only."
        )

    legs = {"skill_overlap": skill_score, "embedding": embed_score, "llm": llm_score}
    available = {name: value for name, value in legs.items() if value is not None}
    if not available:
        raise ScoringError("No scoring method produced a result. " + " ".join(warnings))

    # Weighted average over the legs we actually have.
    total_weight = sum(SCORE_WEIGHTS[name] for name in available)
    final = sum(value * SCORE_WEIGHTS[name] for name, value in available.items()) / total_weight
    final = max(0.0, min(100.0, final))

    # Prefer the LLM's matched/missing lists when available (it reasons
    # about demonstrated experience, not just word presence) and fall back
    # to the dictionary-based overlap otherwise.
    matched = llm_result["matched_skills"] or matched_from_dict
    missing = llm_result["missing_skills"] or missing_from_dict

    def _r(v: float | None) -> float | None:
        return None if v is None else round(v, 1)

    return ScoreResult(
        resume_id=resume_id,
        final_score=round(final, 1),
        skill_overlap_score=_r(skill_score),
        embedding_score=_r(embed_score),
        llm_score=_r(llm_score),
        matched_skills=matched,
        missing_skills=missing,
        red_flags=profile.red_flags,
        reasoning=llm_result["reasoning"],
        warnings=warnings,
        llm_unavailable=llm_score is None,
        llm_error=llm_result["error"],
    )
