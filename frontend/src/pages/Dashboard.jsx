import { useEffect, useRef, useState } from 'react'
import JobDescriptionForm from '../components/JobDescriptionForm.jsx'
import UploadResumes from '../components/UploadResumes.jsx'
import ResultsTable from '../components/ResultsTable.jsx'
import PipelineBoard from '../components/PipelineBoard.jsx'
import EditRoleModal from '../components/EditRoleModal.jsx'
import ScoreBreakdown from '../components/ScoreBreakdown.jsx'
import RolesList from '../components/RolesList.jsx'
import {
  listJobs,
  deleteJob,
  startScoring,
  getScoringStatus,
  getScores,
  setShortlist,
  setStage,
  setCandidateNotes,
  downloadExport,
} from '../api/apiClient.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { LAST_ROLE_KEY, STAGES } from '../constants.js'
import { candidateLabel } from '../utils.js'

const POLL_INTERVAL_MS = 1500
const PAGE_SIZES = [25, 50, 100]
const STAGE_ORDER = Object.fromEntries(STAGES.map((st, i) => [st.value, i]))

// Default direction when a column is first clicked: names A→Z, stages in
// pipeline order, scores highest first.
const DEFAULT_DIR = { name: 'asc', stage: 'asc', score: 'desc' }

function compareRows(a, b, key) {
  if (key === 'name') {
    return candidateLabel(a).localeCompare(candidateLabel(b), undefined, { sensitivity: 'base' })
  }
  if (key === 'stage') return (STAGE_ORDER[a.stage || 'new'] ?? 0) - (STAGE_ORDER[b.stage || 'new'] ?? 0)
  return a.final_score - b.final_score
}

function matchesSearch(row, q) {
  const hay = [
    candidateLabel(row),
    row.filename,
    row.notes,
    ...(row.matched_skills || []),
    ...(row.missing_skills || []),
  ]
    .join(' ')
    .toLowerCase()
  return q.split(/\s+/).every((word) => hay.includes(word))
}

function rememberRole(id) {
  try {
    if (id) localStorage.setItem(LAST_ROLE_KEY, id)
    else localStorage.removeItem(LAST_ROLE_KEY)
  } catch {
    // storage unavailable (private mode) — remembering the role is optional
  }
}

function recalledRole() {
  try {
    return localStorage.getItem(LAST_ROLE_KEY)
  } catch {
    return null
  }
}

export default function Dashboard() {
  const { user, logout } = useAuth()
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
  const [roles, setRoles] = useState([])
  // Bulk actions: which table rows are ticked, and the stage to move them to.
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [bulkStage, setBulkStage] = useState('')
  const [viewMode, setViewMode] = useState('table') // 'table' | 'board'
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState('score') // 'score' | 'name' | 'stage'
  const [sortDir, setSortDir] = useState('desc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [editingRole, setEditingRole] = useState(false)
  const [roleNotice, setRoleNotice] = useState(null) // { text, warning } after a role edit
  const pollRef = useRef(null)
  const selectTokenRef = useRef(0) // guards against a slow click finishing after a newer one
  const knownResumeCountRef = useRef(null)

  async function loadRoles() {
    try {
      const list = await listJobs()
      setRoles(list)
      return list
    } catch {
      return []
    }
  }

  function resetView() {
    stopPolling()
    setResults([])
    setParsedCount(0)
    setProgress(null)
    setScoreError(null)
    setIsScoring(false)
    setSelectedId(null)
    setMinScore(0)
    setShortlistOnly(false)
    setStageFilter('')
    setSelectedIds(new Set())
    setBulkStage('')
    setSearch('')
    setSortKey('score')
    setSortDir('desc')
    setPage(1)
    setEditingRole(false)
    setRoleNotice(null)
    knownResumeCountRef.current = null
  }

  // Reopens a saved role: shows its saved ranking straight from the
  // database (no re-scoring), and picks up a scoring run still in progress.
  async function handleSelectRole(role) {
    const token = ++selectTokenRef.current
    resetView()
    setJob({ id: role.id, title: role.title })
    rememberRole(role.id)

    try {
      const saved = await getScores(role.id)
      if (token === selectTokenRef.current) setResults(saved)
    } catch {
      // 404 just means "not scored yet" — leave the table empty
    }

    // Ask the server (the roles list can be a few seconds stale) whether a
    // scoring run is still going, and if so keep following it.
    try {
      const status = await getScoringStatus(role.id)
      if (token !== selectTokenRef.current) return
      if (status.status === 'queued' || status.status === 'running') {
        setIsScoring(true)
        setProgress({ done: status.done, total: status.total })
        startPolling(role.id)
      }
    } catch {
      // status unavailable — the saved results above are still shown
    }
  }

  useEffect(() => {
    setPage(1)
  }, [search, minScore, shortlistOnly, stageFilter, sortKey, sortDir, pageSize, job?.id])

  // On first load, reopen whichever role was open before the refresh.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const list = await loadRoles()
      if (cancelled) return
      const last = recalledRole()
      const match = list.find((r) => r.id === last)
      if (match) handleSelectRole(match)
    })()
    return () => {
      cancelled = true
      stopPolling()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Called by UploadResumes with this role's resumes whenever their status
  // changes. The count comes from the server's view of THIS role's batch.
  function handleResumesChanged(list) {
    setParsedCount(list.filter((r) => r.status === 'parsed').length)
    // Keep the "Your roles" counts fresh when the batch grows.
    if (knownResumeCountRef.current !== null && knownResumeCountRef.current !== list.length) {
      loadRoles()
    }
    knownResumeCountRef.current = list.length
  }

  // A resume was deleted: its scores are gone on the server, so drop them from the
  // table and from any selection, and refresh the role counts.
  function handleResumeDeleted(resumeId) {
    const gone = results.find((r) => r.resume_id === resumeId)
    setResults((prev) => prev.filter((r) => r.resume_id !== resumeId))
    if (gone) {
      setSelectedId((id) => (id === gone.id ? null : id))
      setSelectedIds((prev) => {
        const next = new Set(prev)
        next.delete(gone.id)
        return next
      })
    }
    loadRoles()
  }

  function handleJobSaved(newJob) {
    // A new role starts with a clean slate: its own batch, its own results.
    ++selectTokenRef.current
    resetView()
    setJob(newJob)
    rememberRole(newJob.id)
    loadRoles()
  }

  // Deletes a role (and its scores). If it's the one open on screen, clear the
  // view so nothing keeps pointing at a role that no longer exists.
  async function handleDeleteRole(role, opts) {
    await deleteJob(role.id, opts) // throws on failure; RolesList shows the message
    if (role.id === job?.id) {
      ++selectTokenRef.current
      resetView()
      setJob(null)
      rememberRole(null)
    }
    await loadRoles()
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  function startPolling(jobId) {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const status = await getScoringStatus(jobId)
        setProgress({ done: status.done, total: status.total })

        if (status.status === 'done') {
          stopPolling()
          const scored = await getScores(jobId)
          setResults(scored)
          // A finished run can still carry warnings (AI unavailable for some
          // resumes, etc). Show them instead of reporting a clean "done".
          if (status.error) setScoreError(status.error)
          setIsScoring(false)
          loadRoles()
        } else if (status.status === 'failed') {
          stopPolling()
          setScoreError(status.error || 'Scoring failed.')
          setIsScoring(false)
          loadRoles()
        }
      } catch (err) {
        stopPolling()
        setScoreError(err.message || 'Lost connection while checking scoring progress.')
        setIsScoring(false)
      }
    }, POLL_INTERVAL_MS)
  }

  async function handleScore() {
    if (!job) return
    setIsScoring(true)
    setScoreError(null)
    setProgress(null)
    setRoleNotice(null)
    stopPolling()

    try {
      await startScoring(job.id)
    } catch (err) {
      setIsScoring(false)
      setScoreError(err.message || 'Could not start scoring. Is the backend running?')
      return
    }

    startPolling(job.id)
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

  async function handleSaveNotes(row, notes) {
    try {
      const updated = await setCandidateNotes(row.id, notes)
      setResults((prev) => prev.map((r) => (r.id === row.id ? { ...r, notes: updated.notes } : r)))
      return true
    } catch (err) {
      setScoreError(err.message || 'Could not save notes.')
      return false
    }
  }

  // ---- Bulk actions ----
  function toggleSelect(row) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(row.id)) next.delete(row.id)
      else next.add(row.id)
      return next
    })
  }

  function toggleSelectAll() {
    const allSelected = visibleResults.length > 0 && visibleResults.every((r) => selectedIds.has(r.id))
    setSelectedIds(allSelected ? new Set() : new Set(visibleResults.map((r) => r.id)))
  }

  async function handleBulkStage() {
    if (!bulkStage || selectedIds.size === 0) return
    const rows = results.filter((r) => selectedIds.has(r.id))
    await Promise.all(rows.map((r) => handleChangeStage(r, bulkStage)))
    setSelectedIds(new Set())
    setBulkStage('')
  }

  function handleSort(key) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(DEFAULT_DIR[key] || 'desc')
    }
  }

  // After a role edit: keep the role on screen, refresh the list, and tell the
  // recruiter that existing scores still reflect the OLD role until re-scored.
  function handleRoleSaved(updated, changedFields) {
    setEditingRole(false)
    setJob((prev) => ({ ...prev, id: updated.id, title: updated.title }))
    loadRoles()
    const affectsScore = changedFields.some((f) => f !== 'title')
    setRoleNotice({
      text: affectsScore
        ? 'Role updated. Current scores still reflect the old version.'
        : 'Role updated.',
      warning: updated.extraction_warning || null,
      canRescore: affectsScore,
    })
  }

  async function handleExport(format) {
    const opts = { shortlistedOnly: shortlistOnly, minScore, stage: stageFilter }
    try {
      await downloadExport(job.id, format, opts)
    } catch (err) {
      setScoreError(err.message || 'Could not export.')
    }
  }

  // Rank = position by score, whatever the table is currently sorted by.
  const rankById = {}
  ;[...results]
    .sort((a, b) => b.final_score - a.final_score)
    .forEach((r, i) => {
      rankById[r.id] = i + 1
    })

  const query = search.trim().toLowerCase()
  const dir = sortDir === 'asc' ? 1 : -1
  const visibleResults = results
    .filter(
      (r) =>
        r.final_score >= minScore &&
        (!shortlistOnly || r.shortlisted) &&
        (!stageFilter || r.stage === stageFilter) &&
        (!query || matchesSearch(r, query))
    )
    .sort((a, b) => dir * compareRows(a, b, sortKey) || b.final_score - a.final_score || candidateLabel(a).localeCompare(candidateLabel(b)))

  const pageCount = Math.max(1, Math.ceil(visibleResults.length / pageSize))
  const safePage = Math.min(page, pageCount)
  const pagedResults = visibleResults.slice((safePage - 1) * pageSize, safePage * pageSize)
  const allVisibleSelected = visibleResults.length > 0 && visibleResults.every((r) => selectedIds.has(r.id))

  // Derived from `results` (not stored) so the open modal always reflects
  // stage changes made from either the table or the modal.
  const selectedCandidate = results.find((r) => r.id === selectedId) || null

  return (
    <div className="min-h-screen bg-paper">
      <header className="flex items-start justify-between gap-4 border-b border-line px-8 py-6">
        <div>
          <p className="font-display text-2xl text-ink">Resume Filter & Scorer</p>
          <p className="text-sm text-ink-soft">
            Screen and rank candidates against a role, in minutes instead of hours.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-sm text-ink-soft">
          <span className="hidden sm:inline" title={user?.email}>
            {user?.full_name || user?.email}
          </span>
          <button
            type="button"
            onClick={logout}
            className="rounded-md border border-line px-3 py-1.5 text-ink hover:bg-white/60"
          >
            Log out
          </button>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl grid-cols-1 gap-8 px-8 py-10 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <section className="rounded-lg border border-line bg-white/60 p-6">
          <RolesList
            roles={roles}
            activeId={job?.id}
            onSelect={handleSelectRole}
            onDelete={handleDeleteRole}
          />
          <JobDescriptionForm onSubmit={handleJobSaved} />
          {job && (
            <div className="mt-4 flex items-start justify-between gap-3 rounded-md bg-gold-soft/50 px-3 py-2 text-xs text-ink-soft">
              <p>Role saved — resumes will be scored against "{job.title}".</p>
              <button
                type="button"
                onClick={() => setEditingRole(true)}
                disabled={isScoring}
                title={isScoring ? 'Wait for scoring to finish' : undefined}
                className="shrink-0 rounded-md border border-line bg-white px-2 py-1 text-ink hover:bg-paper disabled:opacity-40"
              >
                Edit role
              </button>
            </div>
          )}
        </section>

        <section className="flex min-w-0 flex-col gap-8">
          <UploadResumes
            jobId={job?.id}
            disabled={!job}
            onResumesChanged={handleResumesChanged}
            onResumeDeleted={handleResumeDeleted}
          />

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

            {roleNotice && (
              <div className="mb-3 flex flex-wrap items-center gap-3 rounded-md bg-gold-soft/60 px-3 py-2 text-sm text-ink">
                <span>{roleNotice.text}</span>
                {roleNotice.canRescore && (parsedCount > 0 || results.length > 0) && (
                  <button
                    type="button"
                    onClick={handleScore}
                    disabled={isScoring}
                    className="rounded-md bg-ink px-3 py-1 text-white disabled:opacity-40"
                  >
                    Re-score now
                  </button>
                )}
                <button type="button" onClick={() => setRoleNotice(null)} className="ml-auto text-ink-soft underline">
                  Dismiss
                </button>
                {roleNotice.warning && (
                  <p className="w-full text-xs text-amber-800">
                    AI skill extraction failed, so basic keyword matching was used: {roleNotice.warning}
                  </p>
                )}
              </div>
            )}

            {scoreError && (
              <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
                {scoreError}
              </p>
            )}

            {results.length > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-4 text-sm text-ink-soft">
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search name or skill…"
                  aria-label="Search candidates"
                  className="w-56 rounded-md border border-line bg-white px-3 py-1.5 text-ink placeholder:text-ink-soft/60"
                />
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

                <div className="flex overflow-hidden rounded-md border border-line" role="group" aria-label="View">
                  {[
                    ['table', 'Table'],
                    ['board', 'Board'],
                  ].map(([mode, label]) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setViewMode(mode)}
                      aria-pressed={viewMode === mode}
                      className={`px-3 py-1.5 ${viewMode === mode ? 'bg-ink text-white' : 'bg-white text-ink hover:bg-paper'}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>

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

            {viewMode === 'table' && selectedIds.size > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-line bg-gold-soft px-4 py-2 text-sm text-ink">
                <span className="font-medium">{selectedIds.size} selected</span>
                {visibleResults.length > pageSize && (
                  <span className="text-xs text-ink-soft">(“select all” covers every filtered row, not just this page)</span>
                )}
                <select
                  value={bulkStage}
                  onChange={(e) => setBulkStage(e.target.value)}
                  className="rounded-md border border-line bg-white px-2 py-1"
                >
                  <option value="">Move to stage…</option>
                  {STAGES.map((st) => (
                    <option key={st.value} value={st.value}>
                      {st.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={handleBulkStage}
                  disabled={!bulkStage}
                  className="rounded-md bg-ink px-3 py-1 text-white disabled:opacity-40"
                >
                  Apply
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedIds(new Set())}
                  className="text-ink-soft underline"
                >
                  Clear
                </button>
              </div>
            )}

            {viewMode === 'board' ? (
              <PipelineBoard
                results={visibleResults}
                onSelect={(row) => setSelectedId(row.id)}
                onChangeStage={handleChangeStage}
              />
            ) : (
              <>
                <ResultsTable
                  results={pagedResults}
                  onSelect={(row) => setSelectedId(row.id)}
                  onToggleShortlist={handleToggleShortlist}
                  onChangeStage={handleChangeStage}
                  selectedIds={selectedIds}
                  onToggleSelect={toggleSelect}
                  onToggleSelectAll={toggleSelectAll}
                  allSelected={allVisibleSelected}
                  rankById={rankById}
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={handleSort}
                  noMatches={results.length > 0}
                />
                {visibleResults.length > PAGE_SIZES[0] && (
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-ink-soft">
                    <span>
                      {(safePage - 1) * pageSize + 1}–{Math.min(safePage * pageSize, visibleResults.length)} of{' '}
                      {visibleResults.length}
                    </span>
                    <div className="flex items-center gap-2">
                      <label className="flex items-center gap-1">
                        Per page
                        <select
                          value={pageSize}
                          onChange={(e) => setPageSize(Number(e.target.value))}
                          className="rounded-md border border-line bg-white px-2 py-1 text-ink"
                        >
                          {PAGE_SIZES.map((n) => (
                            <option key={n} value={n}>
                              {n}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        onClick={() => setPage(safePage - 1)}
                        disabled={safePage <= 1}
                        className="rounded-md border border-line px-3 py-1 text-ink hover:bg-paper disabled:opacity-40"
                      >
                        Prev
                      </button>
                      <span>
                        Page {safePage} / {pageCount}
                      </span>
                      <button
                        type="button"
                        onClick={() => setPage(safePage + 1)}
                        disabled={safePage >= pageCount}
                        className="rounded-md border border-line px-3 py-1 text-ink hover:bg-paper disabled:opacity-40"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </section>
      </main>

      {editingRole && job && (
        <EditRoleModal jobId={job.id} onClose={() => setEditingRole(false)} onSaved={handleRoleSaved} />
      )}

      <ScoreBreakdown
        candidate={selectedCandidate}
        onClose={() => setSelectedId(null)}
        onChangeStage={handleChangeStage}
        onSaveNotes={handleSaveNotes}
      />
    </div>
  )
}