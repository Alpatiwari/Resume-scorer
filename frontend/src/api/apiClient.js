const API_BASE = 'http://localhost:8000/api'

async function handleResponse(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed with status ${res.status}`)
  }
  return res.json()
}

export async function createJob({ title, description, experience }) {
  const res = await fetch(`${API_BASE}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, description, experience }),
  })
  return handleResponse(res)
}

export async function listJobs() {
  const res = await fetch(`${API_BASE}/jobs`)
  return handleResponse(res)
}

// Deletes a role and its scores. Resume files are kept (they may belong to other roles).
// onlyIfEmpty makes the server refuse (409) unless the role has no resumes and no scores.
export async function deleteJob(jobId, { onlyIfEmpty = false } = {}) {
  const res = await fetch(`${API_BASE}/jobs/${jobId}${onlyIfEmpty ? '?only_if_empty=true' : ''}`, {
    method: 'DELETE',
  })
  return handleResponse(res)
}

export async function uploadResumes(jobId, files) {
  const formData = new FormData()
  formData.append('job_id', jobId)
  files.forEach((file) => formData.append('files', file))

  const res = await fetch(`${API_BASE}/resumes/upload`, {
    method: 'POST',
    body: formData,
  })
  return handleResponse(res)
}

// Resumes in one job's batch, with processing status. Stuck ones come back
// as "failed" (with a reason), so polling this always reaches a final state.
export async function listJobResumes(jobId) {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/resumes`)
  return handleResponse(res)
}

export async function retryResume(resumeId) {
  const res = await fetch(`${API_BASE}/resumes/${resumeId}/retry`, { method: 'POST' })
  return handleResponse(res)
}

export async function listResumes() {
  const res = await fetch(`${API_BASE}/resumes`)
  return handleResponse(res)
}

export async function startScoring(jobId) {
  // Just queues the job now — returns immediately, doesn't wait for
  // scoring to finish. Poll getScoringStatus() for progress.
  const res = await fetch(`${API_BASE}/score/${jobId}`, { method: 'POST' })
  return handleResponse(res)
}

export async function getScoringStatus(jobId) {
  const res = await fetch(`${API_BASE}/score/${jobId}/status`)
  return handleResponse(res)
}

export async function getScores(jobId) {
  const res = await fetch(`${API_BASE}/score/${jobId}`)
  return handleResponse(res)
}
export async function getResume(resumeId) {
  const res = await fetch(`${API_BASE}/resumes/${resumeId}`)
  return handleResponse(res)
}
export async function setShortlist(scoreId, shortlisted) {
  const res = await fetch(`${API_BASE}/score/item/${scoreId}/shortlist`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ shortlisted }),
  })
  return handleResponse(res)
}

export async function setStage(scoreId, stage) {
  const res = await fetch(`${API_BASE}/score/item/${scoreId}/stage`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stage }),
  })
  return handleResponse(res)
}

function exportQuery({ shortlistedOnly = false, minScore = 0, stage = '' } = {}) {
  const params = new URLSearchParams({
    shortlisted_only: String(shortlistedOnly),
    min_score: String(minScore),
  })
  if (stage) params.set('stage', stage)
  return params.toString()
}

export function exportUrl(jobId, opts) {
  return `${API_BASE}/score/${jobId}/export?${exportQuery(opts)}`
}

export function exportPdfUrl(jobId, opts) {
  return `${API_BASE}/score/${jobId}/export.pdf?${exportQuery(opts)}`
}

export function resumeFileUrl(resumeId) {
  return `${API_BASE}/resumes/${resumeId}/file`
}