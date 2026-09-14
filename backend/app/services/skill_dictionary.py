"""
A starter dictionary of common tech/business skills for the fast,
deterministic regex pass. This is intentionally not exhaustive — the LLM
pass in nlp_extractor.py catches skills phrased differently or missing
from this list. Extend this list as you see false negatives in practice.

Keys are the canonical display form; values are alternate spellings /
aliases that should also match.
"""

SKILL_ALIASES: dict[str, list[str]] = {
    "Python": ["python3", "py"],
    "JavaScript": ["js", "javascript", "es6"],
    "TypeScript": ["ts", "typescript"],
    "React": ["react.js", "reactjs"],
    "Node.js": ["node", "nodejs", "node.js"],
    "FastAPI": ["fastapi"],
    "Django": ["django"],
    "Flask": ["flask"],
    "Java": ["java"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp"],
    "Go": ["golang"],
    "SQL": ["sql", "mysql", "postgresql", "postgres", "t-sql"],
    "MongoDB": ["mongodb", "mongo"],
    "PostgreSQL": ["postgresql", "postgres"],
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
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning", "dl"],
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
    "Excel": ["excel", "ms excel"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],
    "Figma": ["figma"],
    "HTML/CSS": ["html", "css", "html5", "css3"],
    "Tailwind CSS": ["tailwind", "tailwindcss"],
    "Next.js": ["next.js", "nextjs"],
    "Vue.js": ["vue", "vue.js", "vuejs"],
}


def all_canonical_skills() -> list[str]:
    return list(SKILL_ALIASES.keys())
