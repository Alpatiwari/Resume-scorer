"""
Email drafts for a candidate: interview invite, rejection or offer.

Template-based, so it works with no API key. Candidate name and address are
pulled from the parsed resume text (best effort) -- the recruiter can edit
everything before sending, and the mail itself is sent from their own mail app
via a mailto: link, so this service never sends anything.
"""
import re
from urllib.parse import quote

KINDS = ("interview", "rejection", "offer")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_NOT_A_NAME = re.compile(
    r"resume|curriculum|vitae|\bcv\b|@|http|www\.|\d|linkedin|github|phone|email|address",
    re.IGNORECASE,
)


def extract_email(text: str | None) -> str | None:
    """First email address in the resume text, or None."""
    if not text:
        return None
    m = _EMAIL_RE.search(text)
    return m.group(0).lower() if m else None


# Words that appear in headings / job titles / file names but are not part of a
# person's name. A line containing any of them is never taken as the name.
_NOT_NAME_WORDS = {
    "resume", "curriculum", "vitae", "cv", "summary", "objective", "profile", "skills", "education",
    "experience", "projects", "contact", "details", "about", "me", "software", "engineer", "developer",
    "backend", "frontend", "fullstack", "full", "stack", "web", "mobile", "data", "analyst", "scientist",
    "intern", "internship", "fresher", "student", "manager", "designer", "computer", "science", "engineering",
    "technology", "information", "bachelor", "master", "university", "college", "institute", "java",
    "python", "javascript", "react", "node", "new", "final", "latest", "updated", "copy",
}


def _filename_words(filename: str) -> list[str]:
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", filename or "")
    stem = re.sub(r"[_\-\.\d()]+", " ", stem)
    return [w for w in stem.split() if w.isalpha() and len(w) >= 2 and w.lower() not in _NOT_NAME_WORDS]


def _name_from_filename(filename: str) -> str | None:
    words = _filename_words(filename)[:3]
    return " ".join(w.capitalize() for w in words) if words else None


def _looks_like_name(line: str) -> bool:
    if not line or len(line) > 40 or _NOT_A_NAME.search(line):
        return False
    words = line.split()
    if not 2 <= len(words) <= 4:
        return False
    if any(w.lower().strip(".") in _NOT_NAME_WORDS for w in words):
        return False
    return all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words)


def extract_name(text: str | None, filename: str = "") -> str | None:
    """Best-effort candidate name, or None when unsure (callers then show the
    filename / a plain 'Hello,' rather than a wrong name).

    Looks at the first lines of the resume for a short, letters-only line that
    isn't a heading or job title. If several lines qualify, the one that shares
    a word with the filename wins; otherwise the first. Falls back to the
    filename itself."""
    lines = [ln.strip() for ln in (text or "")[:2000].splitlines()[:12]]
    candidates = [ln for ln in lines if _looks_like_name(ln)]
    if candidates:
        file_words = {w.lower() for w in _filename_words(filename)}
        pick = next(
            (c for c in candidates if file_words & {w.lower().strip(".") for w in c.split()}),
            candidates[0],
        )
        return " ".join(w.capitalize() if w.islower() or w.isupper() else w for w in pick.split())
    return _name_from_filename(filename)


def build_draft(
    kind: str,
    *,
    candidate_name: str | None,
    job_title: str,
    recruiter_name: str | None,
    company: str | None = None,
) -> dict:
    """Returns {"subject", "body"}. Raises ValueError for an unknown kind."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of: {', '.join(KINDS)}")

    first = (candidate_name or "").split()[0] if candidate_name else ""
    greeting = f"Hi {first}," if first else "Hello,"
    sign = recruiter_name or "The Hiring Team"
    at_company = f" at {company}" if company else ""

    if kind == "interview":
        subject = f"Interview invitation: {job_title}{at_company}"
        body = (
            f"{greeting}\n\n"
            f"Thank you for applying for the {job_title} role{at_company}. "
            "We were impressed by your background and would like to invite you to an interview.\n\n"
            "Could you share a few times over the next week that suit you? "
            "Please also let me know if you would prefer a phone, video or in-person conversation.\n\n"
            "Looking forward to hearing from you.\n\n"
            f"Best regards,\n{sign}"
        )
    elif kind == "rejection":
        subject = f"Your application for {job_title}{at_company}"
        body = (
            f"{greeting}\n\n"
            f"Thank you for your interest in the {job_title} role{at_company} and for the time you "
            "put into applying.\n\n"
            "After careful consideration, we have decided not to move forward with your application "
            "at this time. This was a competitive process and the decision is no reflection on your "
            "abilities. We will keep your details on file and encourage you to apply for future "
            "openings that match your skills.\n\n"
            f"We wish you every success in your search.\n\nKind regards,\n{sign}"
        )
    else:  # offer
        subject = f"Offer for {job_title}{at_company}"
        body = (
            f"{greeting}\n\n"
            f"We are delighted to offer you the {job_title} position{at_company}. "
            "Everyone you met was impressed, and we think you would be a great fit.\n\n"
            "I will send the formal offer letter with the full details shortly. In the meantime, "
            "please let me know if you have any questions, or a good time for a quick call.\n\n"
            f"Congratulations, and we hope to welcome you to the team.\n\nBest regards,\n{sign}"
        )
    return {"subject": subject, "body": body}


def mailto_link(to: str | None, subject: str, body: str) -> str:
    """mailto: URL. Spaces must be %20 (not '+') or mail apps show literal plus signs."""
    return f"mailto:{quote(to or '', safe='@,')}?subject={quote(subject)}&body={quote(body)}"
