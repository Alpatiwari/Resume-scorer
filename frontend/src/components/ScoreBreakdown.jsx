import { useEffect, useState } from 'react'
import { downloadResumeFile, fetchResumeFile, getEmailDraft, getResume } from '../api/apiClient.js'
import { STAGES } from '../constants.js'
import { candidateLabel } from '../utils.js'

function ResumePreview({ candidate }) {
  const isPdf = candidate.filename?.toLowerCase().endsWith('.pdf')
  const [text, setText] = useState(null)
  const [pdfUrl, setPdfUrl] = useState(null)
  const [error, setError] = useState(null)

  // Browsers can render PDFs natively in an iframe; DOCX can't be, so for
  // those we show the text the parser extracted. An iframe can't send the
  // login token, so the PDF is fetched with it and shown from a blob URL.
  useEffect(() => {
    let cancelled = false
    let objectUrl = null
    setError(null)
    setText(null)
    setPdfUrl(null)

    if (isPdf) {
      fetchResumeFile(candidate.resume_id)
        .then((blob) => {
          if (cancelled) return
          objectUrl = URL.createObjectURL(blob)
          setPdfUrl(objectUrl)
        })
        .catch((e) => !cancelled && setError(e.message || 'Could not load the resume file.'))
    } else {
      getResume(candidate.resume_id)
        .then((r) => !cancelled && setText(r.extracted_text || ''))
        .catch((e) => !cancelled && setError(e.message || 'Could not load resume text.'))
    }

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [candidate.resume_id, isPdf])

  async function handleDownload() {
    try {
      await downloadResumeFile(candidate.resume_id, candidate.filename)
    } catch (e) {
      setError(e.message || 'Could not download the file.')
    }
  }

  return (
    <div className="mt-3">
      {error ? (
        <p className="text-sm text-red-700">{error}</p>
      ) : isPdf ? (
        pdfUrl ? (
          <iframe
            title={`Resume: ${candidate.filename}`}
            src={pdfUrl}
            className="h-[60vh] w-full rounded-md border border-line"
          />
        ) : (
          <p className="text-sm text-ink-soft">Loading…</p>
        )
      ) : text === null ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : (
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md border border-line bg-paper p-3 text-xs text-ink">
          {text}
        </pre>
      )}
      <button
        type="button"
        onClick={handleDownload}
        className="mt-2 inline-block text-xs text-ink-soft underline hover:text-ink"
      >
        Download original file
      </button>
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

const EMAIL_KINDS = [
  { value: 'interview', label: 'Interview invite' },
  { value: 'rejection', label: 'Rejection' },
  { value: 'offer', label: 'Offer' },
]

// Builds an editable draft for the candidate, then hands it to the recruiter's
// Gmail (or their mail app via mailto:). Nothing is sent from this app.
function EmailDraftPanel({ candidate }) {
  const [draft, setDraft] = useState(null) // { kind, to, subject, body }
  const [loadingKind, setLoadingKind] = useState(null)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)

  // A different candidate means a different draft.
  useEffect(() => {
    setDraft(null)
    setError(null)
    setCopied(false)
  }, [candidate.id])

  async function handlePick(kind) {
    setLoadingKind(kind)
    setError(null)
    setCopied(false)
    try {
      const d = await getEmailDraft(candidate.id, kind)
      setDraft({ kind, to: d.to || '', subject: d.subject, body: d.body })
    } catch (e) {
      setError(e.message || 'Could not create the draft.')
    } finally {
      setLoadingKind(null)
    }
  }

  function mailtoHref() {
    return (
      `mailto:${encodeURIComponent(draft.to).replace(/%40/g, '@')}` +
      `?subject=${encodeURIComponent(draft.subject)}&body=${encodeURIComponent(draft.body)}`
    )
  }

  // Gmail's web compose window: works in any browser signed in to Gmail,
  // with no mail app set up. URLSearchParams encodes spaces as '+', which
  // Gmail reads correctly.
  function gmailHref() {
    const params = new URLSearchParams({ view: 'cm', fs: '1', su: draft.subject, body: draft.body })
    if (draft.to) params.set('to', draft.to)
    return `https://mail.google.com/mail/?${params.toString()}`
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`)
      setCopied(true)
    } catch {
      setError('Could not copy — select the text and copy it manually.')
    }
  }

  const field = 'w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-ink'

  return (
    <div className="mb-5">
      <p className="mb-1 text-xs font-medium text-ink-soft">Email draft</p>
      <div className="flex flex-wrap gap-2">
        {EMAIL_KINDS.map((k) => (
          <button
            key={k.value}
            type="button"
            onClick={() => handlePick(k.value)}
            disabled={loadingKind !== null}
            className={`rounded-md border px-3 py-1 text-sm text-ink hover:bg-paper disabled:opacity-40 ${
              draft?.kind === k.value ? 'border-ink' : 'border-line'
            }`}
          >
            {loadingKind === k.value ? 'Drafting…' : k.label}
          </button>
        ))}
      </div>

      {error && <p className="mt-2 text-xs text-red-700">{error}</p>}

      {draft && (
        <div className="mt-3 flex flex-col gap-2">
          <input
            value={draft.to}
            onChange={(e) => setDraft({ ...draft, to: e.target.value })}
            placeholder="Recipient email — none found in the resume, add it here"
            aria-label="Recipient email"
            className={field}
          />
          <input
            value={draft.subject}
            onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
            aria-label="Subject"
            className={field}
          />
          <textarea
            value={draft.body}
            onChange={(e) => setDraft({ ...draft, body: e.target.value })}
            rows={9}
            aria-label="Email body"
            className={`${field} resize-y`}
          />
          <div className="flex items-center gap-3">
            <a
              href={gmailHref()}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md bg-ink px-3 py-1 text-sm text-white"
            >
              Open in Gmail
            </a>
            <a
              href={mailtoHref()}
              className="rounded-md border border-line px-3 py-1 text-sm text-ink hover:bg-paper"
            >
              Mail app
            </a>
            <button
              type="button"
              onClick={handleCopy}
              className="rounded-md border border-line px-3 py-1 text-sm text-ink hover:bg-paper"
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
            <span className="text-xs text-ink-soft">Review before sending.</span>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ScoreBreakdown({ candidate, onClose, onChangeStage, onSaveNotes }) {
  const [showPreview, setShowPreview] = useState(false)

  // Recruiter notes: `notes` is what's typed, `savedNotes` is what the server has.
  const [notes, setNotes] = useState('')
  const [savedNotes, setSavedNotes] = useState('')
  const [savingNotes, setSavingNotes] = useState(false)

  // Collapse the preview when switching to a different candidate.
  useEffect(() => {
    setShowPreview(false)
  }, [candidate?.resume_id])

  // Load the saved note whenever a different candidate is opened.
  useEffect(() => {
    setNotes(candidate?.notes || '')
    setSavedNotes(candidate?.notes || '')
  }, [candidate?.id])

  if (!candidate) return null

  async function handleSaveClick() {
    setSavingNotes(true)
    const ok = await onSaveNotes?.(candidate, notes)
    if (ok) setSavedNotes(notes)
    setSavingNotes(false)
  }

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
            <h3 className="font-display text-lg text-ink">{candidateLabel(candidate)}</h3>
            <p className="text-sm text-ink-soft">
              Score breakdown{candidate.candidate_name ? ` · ${candidate.filename}` : ''}
            </p>
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
                {leg.value != null && (
                  <div
                    className="h-full rounded-full bg-gold"
                    style={{ width: `${Math.max(0, Math.min(100, leg.value))}%` }}
                  />
                )}
              </div>
              <span
                className="w-10 shrink-0 text-right text-xs text-ink"
                title={leg.value == null ? 'Not available — not counted in the score' : undefined}
              >
                {leg.value == null ? 'N/A' : leg.value}
              </span>
            </div>
          ))}
        </div>

        <div className="mb-5">
          <label className="mb-1 block text-xs font-medium text-ink-soft">
            Recruiter notes (private)
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder="e.g. Good communication, call on Monday"
            className="w-full resize-y rounded-md border border-line bg-white px-3 py-2 text-sm text-ink"
          />
          <div className="mt-1 flex items-center gap-3">
            <button
              type="button"
              onClick={handleSaveClick}
              disabled={savingNotes || notes === savedNotes}
              className="rounded-md bg-ink px-3 py-1 text-sm text-white disabled:opacity-40"
            >
              {savingNotes ? 'Saving…' : 'Save note'}
            </button>
            {notes === savedNotes && savedNotes && (
              <span className="text-xs text-ink-soft">Saved</span>
            )}
          </div>
        </div>

        <EmailDraftPanel candidate={candidate} />

        {candidate.score_warnings?.length > 0 && (
          <div className="mb-5 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <p className="mb-1 font-medium">This score is degraded</p>
            <ul className="list-inside list-disc">
              {candidate.score_warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        )}

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