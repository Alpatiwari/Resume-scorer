# Resume Filter & Scorer

An AI-assisted resume screening tool for recruiters. Upload a batch of resumes, paste a job description, and get a ranked, explainable shortlist in minutes, instead of reading every resume by hand.

Unlike a plain keyword filter, it scores each resume with **three methods combined** (skill overlap, semantic similarity and an LLM's judgment), so a good candidate isn't rejected just because they worded a skill differently, and a keyword-stuffed resume doesn't rank high by accident.

## Features

- **Bulk upload** of PDF and DOCX resumes (drag and drop, up to 10 MB each). Processing runs in the background, so the UI never freezes.
- **Hybrid scoring (0-100)** with a written explanation per candidate: matched skills, missing skills, red flags and reasoning.
- **Multiple roles.** Each role has its own resume batch and ranking. Re-scoring keeps your shortlist and notes.
- **Hiring pipeline.** Move candidates through New, Shortlisted, Interview, Offer, Hired and Rejected, in a table or a board view.
- **Recruiter tools.** Notes per candidate, resume preview, filters (search, minimum score, stage), and editable email drafts (interview, rejection, offer) that open in your own mail app. Nothing is sent by the server.
- **Export** the shortlist as CSV or PDF.
- **Login and privacy.** Every recruiter only sees their own roles, resumes and scores.
- **Honest failures.** If an AI step fails, the score is flagged with a warning instead of quietly using a made-up number.
- **Duplicate detection.** The same file uploaded twice is stored and parsed once.
- **Stuck-job protection.** Resumes or scoring runs that never finish are marked as failed, with a Retry option.

## How scoring works

Each resume gets up to four scores, combined into one weighted final score:

| Method | Weight | What it measures |
|---|---|---|
| Skill overlap | 30% | Share of the job's required skills the resume shows (nice-to-have skills count half) |
| Semantic similarity | 15% | Embedding similarity between the resume and the job description |
| AI judgment (Gemini) | 45% | Holistic fit, based on skills actually used in projects and work history |
| Experience | 10% | Years of experience vs the job's stated minimum (only when both are known) |

If a method can't run (for example, Gemini is unavailable), it is **left out and the remaining weights are rescaled**. The candidate's score is flagged with a warning icon. Weights live in `backend/app/config.py` (`SCORE_WEIGHTS`).

## Tech stack

| Layer | Tools |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS |
| API | Python, FastAPI, SQLAlchemy |
| Database | PostgreSQL |
| Background jobs | Celery + Redis |
| Parsing | pdfplumber (PDF), python-docx (DOCX) |
| AI | Google Gemini (judgment and profile extraction), sentence-transformers `all-MiniLM-L6-v2` (similarity) |
| Auth | JWT (PyJWT), scrypt password hashing |
| Export | reportlab (PDF), csv |

## Project structure

```
resume-scorer/
├── frontend/                 React dashboard
│   └── src/
│       ├── pages/            Dashboard.jsx, Login.jsx
│       ├── components/       UploadResumes, JobDescriptionForm, ResultsTable,
│       │                     ScoreBreakdown, PipelineBoard, RolesList, EditRoleModal
│       ├── auth/             AuthContext.jsx
│       └── api/              apiClient.js
└── backend/
    ├── app/
    │   ├── main.py           FastAPI entry point
    │   ├── config.py         settings and scoring weights
    │   ├── routers/          auth, jobs, resumes, scoring
    │   ├── services/         parser, nlp_extractor, embeddings, llm_scorer,
    │   │                     gemini_client, scorer, security, email_draft
    │   ├── models/           database tables
    │   └── workers/          Celery tasks (parse resumes, score jobs)
    ├── tests/
    ├── create_user.py        create a recruiter account from the terminal
    ├── migrate_*.py          one-off scripts for databases created before a feature existed
    └── storage/              uploaded resume files (not committed)
```

## Getting started

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL
- Redis
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

### 1. Clone

```bash
git clone https://github.com/Alpatiwari/Resume-scorer.git
cd Resume-scorer
```

### 2. Database and Redis

```bash
createdb resume_scorer      # PostgreSQL
redis-server                # or start Redis as a service
```

### 3. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then edit .env (see Configuration below)
```

Generate a JWT secret and paste it into `.env` as `JWT_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start the API (tables are created automatically on first start):

```bash
uvicorn app.main:app --reload --port 8000
```

In a **second terminal** (same folder, venv active), start the background worker. Resumes are not parsed or scored without it:

```bash
celery -A app.celery_app.celery_app worker --loglevel=info
```

The first run downloads the embedding model, so it can take a minute.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and create an account on the login page. You can also create one from the terminal (works even when sign-ups are disabled):

```bash
cd backend
python create_user.py you@example.com --name "Your Name"
```

API docs are at http://localhost:8000/docs.

### 5. Check that Gemini works

Sign in, then open `/docs`, click **Authorize**, and run `GET /api/health/llm`. A wrong model name or key shows up there immediately, instead of as unexplained warning icons on scores.

## Configuration

All settings go in `backend/.env`.

**Required**

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | e.g. `postgresql+psycopg2://user:password@localhost:5432/resume_scorer` |
| `REDIS_URL` | e.g. `redis://localhost:6379/0` |
| `JWT_SECRET_KEY` | At least 32 random characters. The API refuses to start without it. |
| `GEMINI_API_KEY` | Your Google AI Studio key |

**Optional**

| Variable | Default | Meaning |
|---|---|---|
| `RESUME_SCORER_GEMINI_MODEL` | see `config.py` | Gemini model to use. Pick one your key has quota for. |
| `RESUME_SCORER_GEMINI_FALLBACK_MODELS` | empty | Comma-separated backup models |
| `RESUME_SCORER_GEMINI_TIMEOUT_MS` | `20000` | Per-call timeout |
| `RESUME_SCORER_SCORING_CONCURRENCY` | `5` | Resumes scored in parallel. Lower it on free-tier keys. |
| `RESUME_SCORER_ALLOW_DEGRADED_SCORING` | `false` | `false`: if Gemini fails for every resume, the run fails and saves nothing. `true`: save keyword/semantic-only scores, flagged with a warning. |
| `RESUME_SCORER_CORS_ORIGINS` | `http://localhost:5173` | Allowed frontend address(es), comma-separated. Set this when you deploy. |
| `RESUME_SCORER_ALLOW_REGISTRATION` | `true` | Set `false` to close public sign-ups. |
| `RESUME_SCORER_ACCESS_TOKEN_MINUTES` | `480` | Login session length |
| `RESUME_SCORER_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model |

More timeouts (`QUEUE_TIMEOUT_MINUTES`, `PARSE_TIMEOUT_MINUTES`, `SCORING_STALE_MINUTES`, login throttling) are listed in `backend/app/config.py`.

The frontend reads `VITE_API_BASE` (default `http://localhost:8000/api`). Set it when the API is not on localhost.

## Usage

1. **Save a role.** Enter a title and the full job description. Required and nice-to-have skills and the minimum years of experience are extracted for you. You can edit them with **Edit role**.
2. **Upload resumes.** Wait until they show **Parsed**. A failed one can be retried or deleted.
3. **Click Score candidates.** Progress is shown live.
4. **Review the ranking.** Click a candidate for the score breakdown, resume preview, notes and email drafts.
5. **Shortlist and move candidates** through the pipeline, then **Export CSV / PDF**.

## Running the tests

The tests use an in-memory SQLite database. They need no Postgres, Redis or Gemini.

```bash
cd backend
pip install pytest httpx
pytest
```

## Privacy and security notes

- **Resumes are personal data.** Use a paid Gemini key for real candidates. Google's free tier may use inputs and outputs to improve its models.
- Never commit `.env` or `backend/storage/`. Both are in `.gitignore`.
- Passwords are hashed with scrypt, and logins are rate-limited per IP and email. The limiter is in memory, so it only works with a single API process.
- Resume text is treated as untrusted. The AI prompt tells the model to ignore instructions hidden in a resume, and exported CSV cells are protected against spreadsheet formula injection.
- Deleting a resume permanently removes its text, scores, notes and stored file.

## Known limitations

- Scanned (image-only) PDFs have no text and fail with a clear message. OCR is not included.
- The embedding model only reads roughly the first 256 tokens of each resume, which is why it has the lowest weight.
- Resume files are stored on local disk. Deploying the API and worker on separate machines needs shared storage such as S3.
- Database changes use the one-off `migrate_*.py` scripts. They are only needed for databases created before a feature existed. A fresh install creates everything automatically.

## Roadmap

- Docker setup (API, worker, Postgres and Redis in one command)
- Cloud file storage
- Alembic migrations
- OCR for scanned resumes
- Chunked embeddings for long resumes
