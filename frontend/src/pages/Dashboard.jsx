import { useRef, useState } from 'react'
import JobDescriptionForm from '../components/JobDescriptionForm.jsx'
import UploadResumes from '../components/UploadResumes.jsx'
import ResultsTable from '../components/ResultsTable.jsx'
import ScoreBreakdown from '../components/ScoreBreakdown.jsx'
import {
  startScoring,
  getScoringStatus,
  getScores,
  setShortlist,
  setStage,
  exportUrl,
  exportPdfUrl,
} from '../api/apiClient.js'
import { STAGES } from '../constants.js'

const POLL_INTERVAL_MS = 1500

export default function Dashboard() {
  const [job, setJob] = useState(null)
  const [results, setResults] = useState([])
  const [parsedCount, setParsedCount] = useState(0)
  const [isScoring, setIsScoring] = useState(false)
  const [progress, setProgress] = useState(null) // { done, total }
  const [scoreError, setScoreError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [stageFilter, setStageFilter] = useState('')
  const [minScore, setMinScore] = useState(0)
  const [shortlistOnly, setShortlistOnly] = useState(false)
  const pollRef = useRef(null)

  function handleUploaded(uploadResults) {
    const parsed = uploadResults.filter((r) => r.status === 'parsed').length
    setParsedCount((prev) => prev + parsed)
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  async function handleScore() {
    if (!job) return
    setIsScoring(true)
    setScoreError(null)
    setProgress(null)
    stopPolling()

    try {
      await startScoring(job.id)
    } catch (err) {
      setIsScoring(false)
      setScoreError(err.message || 'Could not start scoring. Is the backend running?')
      return
    }

    pollRef.current = setInterval(async () => {
      try {
        const status = await getScoringStatus(job.id)
        setProgress({ done: status.done, total: status.total })

        if (status.status === 'done') {
          stopPolling()
          const scored = await getScores(job.id)
          setResults(scored)
          setIsScoring(false)
        } else if (status.status === 'failed') {
          stopPolling()
          setScoreError(status.error || 'Scoring failed.')
          setIsScoring(false)
        }
      } catch (err) {
        stopPolling()
        setScoreError(err.message || 'Lost connection while checking scoring progress.')
        setIsScoring(false)
      }
    }, POLL_INTERVAL_MS)
  }

  async function handleToggleShortlist(row) {
    const next = !row.shortlisted
    setResults((prev) => prev.map((r) => (r.id === row.id ? { ...r, shortlisted: next } : r)))
    try {
      // The server keeps `stage` in sync with the shortlist flag, so take
      // its answer rather than guessing the new stage client-side.
      const updated = await setShortlist(row.id, next)
      setResults((prev) =>
        prev.map((r) => (r.id === row.id ? { ...r, shortlisted: updated.shortlisted, stage: updated.stage } : r))
      )
    } catch (err) {
      setResults((prev) => prev.map((r) => (r.id === row.id ? { ...r, shortlisted: !next } : r)))
      setScoreError(err.message || 'Could not update shortlist.')
    }
  }

  async function handleChangeStage(row, stage) {
    const previous = { stage: row.stage, shortlisted: row.shortlisted }
    setResults((prev) => prev.map((r) => (r.id === row.id ? { ...r, stage } : r)))
    try {
      const updated = await setStage(row.id, stage)
      setResults((prev) =>
        prev.map((r) => (r.id === row.id ? { ...r, stage: updated.stage, shortlisted: updated.shortlisted } : r))
      )
    } catch (err) {
      setResults((prev) => prev.map((r) => (r.id === row.id ? { ...r, ...previous } : r)))
      setScoreError(err.message || 'Could not update stage.')
    }
  }

  function handleExport(format) {
    const opts = { shortlistedOnly: shortlistOnly, minScore, stage: stageFilter }
    window.open(format === 'pdf' ? exportPdfUrl(job.id, opts) : exportUrl(job.id, opts), '_blank')
  }

  const visibleResults = results.filter(
    (r) =>
      r.final_score >= minScore &&
      (!shortlistOnly || r.shortlisted) &&
      (!stageFilter || r.stage === stageFilter)
  )

  // Derived from `results` (not stored) so the open modal always reflects
  // stage changes made from either the table or the modal.
  const selectedCandidate = results.find((r) => r.id === selectedId) || null

  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-line px-8 py-6">
        <p className="font-display text-2xl text-ink">Resume Filter & Scorer</p>
        <p className="text-sm text-ink-soft">
          Screen and rank candidates against a role, in minutes instead of hours.
        </p>
      </header>

      <main className="mx-auto grid max-w-6xl grid-cols-1 gap-8 px-8 py-10 lg:grid-cols-[minmax(0,340px)_1fr]">
        <section className="rounded-lg border border-line bg-white/60 p-6">
          <JobDescriptionForm onSubmit={setJob} />
          {job && (
            <p className="mt-4 rounded-md bg-gold-soft/50 px-3 py-2 text-xs text-ink-soft">
              Role saved — resumes will be scored against "{job.title}".
            </p>
          )}
        </section>

        <section className="flex flex-col gap-8">
          <UploadResumes disabled={!job} onUploaded={handleUploaded} />

          <div>
            <div className="mb-3 flex items-center justify-between gap-4">
              <h2 className="font-display text-xl text-ink">Ranked candidates</h2>
              <button
                type="button"
                onClick={handleScore}
                disabled={!job || parsedCount === 0 || isScoring}
                className="shrink-0 rounded-md bg-ink px-4 py-2 text-sm font-medium text-paper transition-colors hover:bg-ink/90 disabled:cursor-not-allowed disabled:bg-ink/30"
              >
                {isScoring
                  ? progress && progress.total
                    ? `Scoring… ${progress.done}/${progress.total}`
                    : 'Scoring…'
                  : 'Score candidates'}
              </button>
            </div>

            {parsedCount > 0 && results.length === 0 && !isScoring && (
              <p className="mb-3 text-sm text-ink-soft">
                {parsedCount} resume{parsedCount > 1 ? 's' : ''} parsed — click "Score
                candidates" to rank them against the saved role.
              </p>
            )}

            {scoreError && (
              <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
                {scoreError}
              </p>
            )}

            {results.length > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-4 text-sm text-ink-soft">
                <label className="flex items-center gap-2">
                  Min score: {minScore}
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={minScore}
                    onChange={(e) => setMinScore(Number(e.target.value))}
                  />
                </label>

                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={shortlistOnly}
                    onChange={(e) => setShortlistOnly(e.target.checked)}
                  />
                  Shortlisted only
                </label>

                <label className="flex items-center gap-2">
                  Stage
                  <select
                    value={stageFilter}
                    onChange={(e) => setStageFilter(e.target.value)}
                    className="rounded-md border border-line bg-white px-2 py-1 text-ink"
                  >
                    <option value="">All</option>
                    {STAGES.map((st) => (
                      <option key={st.value} value={st.value}>
                        {st.label}
                      </option>
                    ))}
                  </select>
                </label>

                <button
                  type="button"
                  onClick={() => handleExport('csv')}
                  className="rounded-md border border-line px-3 py-1.5 text-ink hover:bg-paper"
                >
                  Export CSV
                </button>
                <button
                  type="button"
                  onClick={() => handleExport('pdf')}
                  className="rounded-md border border-line px-3 py-1.5 text-ink hover:bg-paper"
                >
                  Export PDF
                </button>

                <span>
                  Showing {visibleResults.length} of {results.length}
                </span>
              </div>
            )}

            <ResultsTable
              results={visibleResults}
              onSelect={(row) => setSelectedId(row.id)}
              onToggleShortlist={handleToggleShortlist}
              onChangeStage={handleChangeStage}
            />
          </div>
        </section>
      </main>

      <ScoreBreakdown
        candidate={selectedCandidate}
        onClose={() => setSelectedId(null)}
        onChangeStage={handleChangeStage}
      />
    </div>
  )
}