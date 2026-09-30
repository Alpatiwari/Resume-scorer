import { TOKEN_KEY } from '../constants.js'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

// ---------------------------------------------------------------- token storage

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // storage unavailable (private mode) — the session just won't survive a refresh
  }
}

// AuthContext registers a function here that signs the user out. It is called
// whenever the server answers 401 to a signed-in request (expired/invalid token).
let onUnauthorized = null
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

// ---------------------------------------------------------------- core request

// FastAPI sends `detail` as a string for our errors but as a list of objects for
// validation errors (422). Turn either into a readable message.
function messageFrom(detail, status) {
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => d?.msg || String(d)).join('; ')
  }
  return `Request failed with status ${status}`
}

async function request(path, { method = 'GET', json, body, headers = {}, auth = true } = {}) {
  const finalHeaders = { ...headers }
  const token = getToken()
  if (auth && token) finalHeaders.Authorization = `Bearer ${token}`
  if (json !== undefined) {
    finalHeaders['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  }

  const res = await fetch(`${API_BASE}${path}`, { method, headers: finalHeaders, body })

  if (!res.ok) {
    if (res.status === 401 && auth && token) onUnauthorized?.()
    const data = await res.json().catch(() => ({}))
    throw new Error(messageFrom(data.detail, res.status))
  }
  return res
}

async function requestJson(path, options) {
  const res = await request(path, options)
  return res.json()
}

// ------------------------------------------------------------------------ auth

export function getAuthConfig() {
  return requestJson('/auth/config', { auth: false })
}

export function register({ email, password, fullName }) {
  return requestJson('/auth/register', {
    method: 'POST',
    json: { email, password, full_name: fullName || null },
    auth: false,
  })
}

export function login({ email, password }) {
  // The backend uses the standard OAuth2 password form: `username` carries the email.
  return requestJson('/auth/login', {
    method: 'POST',
    body: new URLSearchParams({ username: email, password }),
    auth: false,
  })
}

export function getMe() {
  return requestJson('/auth/me')
}

// ------------------------------------------------------------------------ jobs

export function createJob({ title, description, experience }) {
  return requestJson('/jobs', { method: 'POST', json: { title, description, experience } })
}

export function getJob(jobId) {
  return requestJson(`/jobs/${jobId}`)
}

// Only the fields you pass are changed. Returns the updated role
// (plus `extraction_warning` if AI skill extraction failed).
export function updateJob(jobId, changes) {
  return requestJson(`/jobs/${jobId}`, { method: 'PATCH', json: changes })
}

export function listJobs() {
  return requestJson('/jobs')
}

// Deletes a role and its scores. Resume files are kept (they may belong to other roles).
// onlyIfEmpty makes the server refuse (409) unless the role has no resumes and no scores.
export function deleteJob(jobId, { onlyIfEmpty = false } = {}) {
  return requestJson(`/jobs/${jobId}${onlyIfEmpty ? '?only_if_empty=true' : ''}`, { method: 'DELETE' })
}

// Resumes in one job's batch, with processing status. Stuck ones come back
// as "failed" (with a reason), so polling this always reaches a final state.
export function listJobResumes(jobId) {
  return requestJson(`/jobs/${jobId}/resumes`)
}

// ---------------------------------------------------------------------- resumes

export function uploadResumes(jobId, files) {
  const formData = new FormData()
  formData.append('job_id', jobId)
  files.forEach((file) => formData.append('files', file))
  // No Content-Type here: the browser must add the multipart boundary itself.
  return requestJson('/resumes/upload', { method: 'POST', body: formData })
}

export function retryResume(resumeId) {
  return requestJson(`/resumes/${resumeId}/retry`, { method: 'POST' })
}

// Permanently deletes a resume (text, scores, links to ALL roles, stored file).
export function deleteResume(resumeId) {
  return requestJson(`/resumes/${resumeId}`, { method: 'DELETE' })
}

export function listResumes() {
  return requestJson('/resumes')
}

export function getResume(resumeId) {
  return requestJson(`/resumes/${resumeId}`)
}

// ---------------------------------------------------------------------- scoring

export function startScoring(jobId) {
  // Just queues the job now — returns immediately, doesn't wait for
  // scoring to finish. Poll getScoringStatus() for progress.
  return requestJson(`/score/${jobId}`, { method: 'POST' })
}

export function getScoringStatus(jobId) {
  return requestJson(`/score/${jobId}/status`)
}

export function getScores(jobId) {
  return requestJson(`/score/${jobId}`)
}

export function setShortlist(scoreId, shortlisted) {
  return requestJson(`/score/item/${scoreId}/shortlist`, { method: 'PATCH', json: { shortlisted } })
}

export function setStage(scoreId, stage) {
  return requestJson(`/score/item/${scoreId}/stage`, { method: 'PATCH', json: { stage } })
}

// kind: 'interview' | 'rejection' | 'offer'. Returns { to, subject, body, mailto, candidate_name }.
export function getEmailDraft(scoreId, kind) {
  return requestJson(`/score/item/${scoreId}/email-draft`, { method: 'POST', json: { kind } })
}

export function setCandidateNotes(scoreId, notes) {
  return requestJson(`/score/item/${scoreId}/notes`, { method: 'PATCH', json: { notes } })
}

// ------------------------------------------------------------ authenticated files
// <a href>, window.open and <iframe src> can't send an Authorization header, so
// files are fetched with fetch() and handed to the browser as a blob instead.

function exportQuery({ shortlistedOnly = false, minScore = 0, stage = '' } = {}) {
  const params = new URLSearchParams({
    shortlisted_only: String(shortlistedOnly),
    min_score: String(minScore),
  })
  if (stage) params.set('stage', stage)
  return params.toString()
}

function filenameFrom(res, fallback) {
  const header = res.headers.get('Content-Disposition') || ''
  const match = /filename="?([^";]+)"?/i.exec(header)
  return match ? match[1] : fallback
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

// format: 'csv' | 'pdf'. Throws with the server's message (e.g. "Nothing to export ...").
export async function downloadExport(jobId, format, opts) {
  const path = format === 'pdf' ? 'export.pdf' : 'export'
  const res = await request(`/score/${jobId}/${path}?${exportQuery(opts)}`)
  saveBlob(await res.blob(), filenameFrom(res, `shortlist.${format}`))
}

export async function fetchResumeFile(resumeId) {
  const res = await request(`/resumes/${resumeId}/file`)
  return res.blob()
}

export async function downloadResumeFile(resumeId, filename) {
  saveBlob(await fetchResumeFile(resumeId), filename || 'resume')
}