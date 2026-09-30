"""
A starter dictionary of common tech/business skills for the fast,
deterministic regex pass. This is intentionally not exhaustive — the LLM
pass in nlp_extractor.py catches skills phrased differently or missing
from this list. Extend this list as you see false negatives in practice.

Keys are the canonical display form; values are alternate spellings /
aliases that should also match (case-insensitively).

Three extra tables handle the tricky cases:

  CASE_SENSITIVE_ALIASES  aliases that are only a skill when written exactly
                          like this ("JS", "ML"), because in lower case they
                          are ordinary words or too ambiguous.
  CONTEXT_PATTERNS        skills whose name is also an everyday English word
                          ("Go", "Excel"). Matched only by a hand-written
                          regex, so "I go beyond expectations" and "I excel
                          at communication" do not count as skills.
  IMPLIES                 a skill that proves another one (PostgreSQL -> SQL).

normalize_skill() maps any spelling ("React.js", "reactjs", "REST API") to
its canonical name, so skill comparison isn't defeated by wording.
"""
import re

SKILL_ALIASES: dict[str, list[str]] = {
    "Python": ["python3"],
    "JavaScript": ["javascript", "es6"],
    "TypeScript": ["typescript"],
    "React": ["react.js", "reactjs"],
    "Node.js": ["nodejs", "node.js"],
    "FastAPI": ["fastapi"],
    "Django": ["django"],
    "Flask": ["flask"],
    "Java": ["java"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp"],
    "Go": ["golang"],
    "SQL": ["sql", "t-sql"],
    "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Docker": ["docker", "containerization"],
    "Kubernetes": ["kubernetes", "k8s"],
    "AWS": ["aws", "amazon web services"],
    "GCP": ["gcp", "google cloud"],
    "Azure": ["azure"],
    "CI/CD": ["ci/cd", "continuous integration", "continuous deployment"],
    "Git": ["git", "github", "gitlab", "version control"],
    "REST APIs": ["rest api", "restful", "rest apis"],
    "GraphQL": ["graphql"],
    "Machine Learning": ["machine learning"],
    "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"],
    "PyTorch": ["pytorch"],
    "TensorFlow": ["tensorflow"],
    "spaCy": ["spacy"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "Celery": ["celery"],
    "Microservices": ["microservices", "microservice architecture"],
    "Agile": ["agile", "scrum", "kanban"],
    "Project Management": ["project management", "pmp"],
    "Excel": ["ms excel", "microsoft excel", "advanced excel"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],
    "Figma": ["figma"],
    "HTML/CSS": ["html", "css", "html5", "css3"],
    "Tailwind CSS": ["tailwind", "tailwindcss"],
    "Next.js": ["next.js", "nextjs"],
    "Vue.js": ["vue", "vue.js", "vuejs"],
}

# Only a skill when written exactly like this.
CASE_SENSITIVE_ALIASES: dict[str, list[str]] = {
    "JavaScript": ["JS"],
    "TypeScript": ["TS"],
    "Machine Learning": ["ML"],
    "Deep Learning": ["DL"],
}

# Skills whose name is a normal English word. Regexes are matched against the
# ORIGINAL-case text.
_B = r"(?<![A-Za-z0-9])"
CONTEXT_PATTERNS: dict[str, list[str]] = {
    "Go": [
        # "Go" as an item in a list or at the end of a line: "Python, Go, SQL"
        _B + r"Go(?![A-Za-z0-9])(?=\s*(?:[,;/|)•·\n]|$))",
        # after a list opener: "Languages: Go and Python"
        r"[:,(/|]\s*Go(?![A-Za-z0-9])(?!\s+(?:to|beyond|above|the|for|through|on|out|back|live)\b)",
        # "Go developer", "Go microservices"
        _B + r"Go\s+(?:developer|programming|language|backend|microservices?|services?)\b",
    ],
    "Excel": [
        # capital-E "Excel" that is not the verb ("Excel at ...")
        _B + r"Excel(?![A-Za-z0-9])(?!\s+at\b)",
    ],
}

# A skill that proves another skill.
IMPLIES: dict[str, list[str]] = {
    "PostgreSQL": ["SQL"],
    "MySQL": ["SQL"],
}


def all_canonical_skills() -> list[str]:
    return list(SKILL_ALIASES.keys())


def skill_key(name: str) -> str:
    """Comparison key: lower case with spaces, dots, dashes, slashes and
    underscores removed. "React.js", "ReactJS", "react js" all become "reactjs"."""
    return re.sub(r"[\s.\-_/]+", "", (name or "").lower())


def _build_alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    # Aliases first, canonical names last, so a canonical name always wins a
    # clash (e.g. "postgresql").
    for canonical, aliases in SKILL_ALIASES.items():
        for a in aliases:
            mapping.setdefault(skill_key(a), canonical)
    for canonical, aliases in CASE_SENSITIVE_ALIASES.items():
        for a in aliases:
            mapping.setdefault(skill_key(a), canonical)
    for canonical in SKILL_ALIASES:
        mapping[skill_key(canonical)] = canonical
    return mapping


_ALIAS_TO_CANONICAL = _build_alias_map()


def normalize_skill(name: str) -> str:
    """Canonical spelling for a skill if we know it, else the trimmed input."""
    cleaned = " ".join((name or "").split())
    return _ALIAS_TO_CANONICAL.get(skill_key(cleaned), cleaned)


def normalize_skills(names) -> list[str]:
    """Normalises and de-duplicates (case-insensitively), keeping first-seen order."""
    seen: dict[str, str] = {}
    for n in names:
        norm = normalize_skill(n)
        if norm:
            seen.setdefault(skill_key(norm), norm)
    return list(seen.values())


def with_implied(skills) -> set[str]:
    """Skill keys for `skills`, plus the keys of anything they imply."""
    keys: set[str] = set()
    for s in skills:
        canonical = normalize_skill(s)
        keys.add(skill_key(canonical))
        for implied in IMPLIES.get(canonical, []):
            keys.add(skill_key(implied))
    return keys