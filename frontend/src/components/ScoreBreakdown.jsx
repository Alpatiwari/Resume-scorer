import { useEffect, useState } from 'react'
import { getResume, resumeFileUrl } from '../api/apiClient.js'
import { STAGES } from '../constants.js'

function ResumePreview({ candidate }) {
  const isPdf = candidate.filename?.toLowerCase().endsWith('.pdf')
  const [text, setText] = useState(null)
  const [error, setError] = useState(null)

  // Browsers can render PDFs natively in an iframe; DOCX can't be, so for
  // those we show the text the parser extracted.
  useEffect(() => {
    if (isPdf) return
    let cancelled = false
    getResume(candidate.resume_id)
      .then((r) => !cancelled && setText(r.extracted_text || ''))
      .catch((e) => !cancelled && setError(e.message || 'Could not load resume text.'))
    return () => {
      cancelled = true
    }
  }, [candidate.resume_id, isPdf])

  return (
    <div className="mt-3">
      {isPdf ? (
        <iframe
          title={`Resume: ${candidate.filename}`}
          src={resumeFileUrl(candidate.resume_id)}
          className="h-[60vh] w-full rounded-md border border-line"
        />
      ) : error ? (
        <p className="text-sm text-red-700">{error}</p>
      ) : text === null ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : (
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md border border-line bg-paper p-3 text-xs text-ink">
          {text}
        </pre>
      )}
      <a
        href={resumeFileUrl(candidate.resume_id)}
        target="_blank"
        rel="noreferrer"
        className="mt-2 inline-block text-xs text-ink-soft underline hover:text-ink"
      >
        Open original file
      </a>
    </div>
  )
}

function Highlights({ candidate }) {
  const hasYears = candidate.experience_years !== null && candidate.experience_years !== undefined
  const hasEducation = candidate.education?.length > 0
  const hasProjects = candidate.projects?.length > 0
  if (!hasYears && !hasEducation && !hasProjects) return null

  return (
    <div className="mt-5 flex flex-col gap-3">
      <p className="text-xs font-medium text-ink-soft">Experience highlights</p>
      {hasYears && (
        <p className="text-sm text-ink">
          <span className="text-ink-soft">Experience: </span>
          {candidate.experience_years} year{candidate.experience_years === 1 ? '' : 's'}
        </p>
      )}
      {hasEducation && (
        <div>
          <p className="mb-1 text-xs text-ink-soft">Education</p>
          <ul className="list-inside list-disc text-sm text-ink">
            {candidate.education.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}
      {hasProjects && (
        <div>
          <p className="mb-1 text-xs text-ink-soft">Relevant projects</p>
          <ul className="list-inside list-disc text-sm text-ink">
            {candidate.projects.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default function ScoreBreakdown({ candidate, onClose, onChangeStage }) {
  const [showPreview, setShowPreview] = useState(false)

  // Collapse the preview when switching to a different candidate.
  useEffect(() => {
    setShowPreview(false)
  }, [candidate?.resume_id])

  if (!candidate) return null

  const legs = [
    { label: 'Skill overlap', value: candidate.skill_overlap_score },
    { label: 'Semantic similarity', value: candidate.embedding_score },
    { label: 'LLM judgment', value: candidate.llm_score },
  ]

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 px-4"
      onClick={onClose}
    >
      <div
        className={`max-h-[90vh] w-full overflow-y-auto rounded-lg border border-line bg-white p-6 ${showPreview ? 'max-w-3xl' : 'max-w-lg'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="font-display text-lg text-ink">{candidate.filename}</h3>
            <p className="text-sm text-ink-soft">Score breakdown</p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-md px-2 py-1 text-sm text-ink-soft hover:bg-paper hover:text-ink"
          >
            Close
          </button>
        </div>

        <div className="mb-5 flex items-center gap-3">
          <span className="rounded-full bg-gold-soft px-3 py-1 text-lg font-medium text-ink">
            {candidate.final_score}
          </span>
          <span className="text-sm text-ink-soft">overall fit score (0–100)</span>
          <label className="ml-auto flex items-center gap-2 text-xs text-ink-soft">
            Stage
            <select
              value={candidate.stage || 'new'}
              onChange={(e) => onChangeStage?.(candidate, e.target.value)}
              className="rounded-md border border-line bg-white px-2 py-1 text-sm text-ink"
            >
              {STAGES.map((st) => (
                <option key={st.value} value={st.value}>
                  {st.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="mb-5 flex flex-col gap-2">
          {legs.map((leg) => (
            <div key={leg.label} className="flex items-center gap-3">
              <span className="w-40 shrink-0 text-xs text-ink-soft">{leg.label}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-paper">
                <div
                  className="h-full rounded-full bg-gold"
                  style={{ width: `${Math.max(0, Math.min(100, leg.value))}%` }}
                />
              </div>
              <span className="w-10 shrink-0 text-right text-xs text-ink">{leg.value}</span>
            </div>
          ))}
        </div>

        {candidate.reasoning && (
          <p className="mb-5 rounded-md bg-paper px-3 py-2 text-sm text-ink-soft">
            {candidate.reasoning}
          </p>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="mb-1.5 text-xs font-medium text-ink-soft">Matched skills</p>
            {candidate.matched_skills?.length ? (
              <ul className="flex flex-wrap gap-1.5">
                {candidate.matched_skills.map((s) => (
                  <li key={s} className="rounded-full bg-gold-soft px-2 py-0.5 text-xs text-ink">
                    {s}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-ink-soft">None</p>
            )}
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-ink-soft">Missing skills</p>
            {candidate.missing_skills?.length ? (
              <ul className="flex flex-wrap gap-1.5">
                {candidate.missing_skills.map((s) => (
                  <li key={s} className="rounded-full bg-red-50 px-2 py-0.5 text-xs text-red-700">
                    {s}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-ink-soft">None</p>
            )}
          </div>
        </div>

        {candidate.red_flags?.length > 0 && (
          <div className="mt-5">
            <p className="mb-1.5 text-xs font-medium text-ink-soft">Red flags</p>
            <ul className="list-inside list-disc text-sm text-ink-soft">
              {candidate.red_flags.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </div>
        )}

        <Highlights candidate={candidate} />

        <div className="mt-6 border-t border-line pt-4">
          <button
            type="button"
            onClick={() => setShowPreview((v) => !v)}
            className="rounded-md border border-line px-3 py-1.5 text-sm text-ink hover:bg-paper"
          >
            {showPreview ? 'Hide resume' : 'View resume'}
          </button>
          {showPreview && <ResumePreview candidate={candidate} />}
        </div>
      </div>
    </div>
  )
}
