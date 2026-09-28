import { useCallback, useEffect, useRef, useState } from 'react'
import { uploadResumes, listJobResumes, retryResume } from '../api/apiClient.js'

const ACCEPTED = ['.pdf', '.docx']
const POLL_INTERVAL_MS = 1500
const SLOW_HINT_AFTER_MS = 90_000

export default function UploadResumes({ jobId, disabled, onResumesChanged }) {
  const [isDragging, setIsDragging] = useState(false)
  const [pendingFiles, setPendingFiles] = useState([])
  const [batch, setBatch] = useState([]) // this role's resumes, straight from the server
  const [rejected, setRejected] = useState([]) // files refused at upload (wrong type, too big)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  // Keep the latest callback in a ref so polling doesn't restart every render.
  const onChangedRef = useRef(onResumesChanged)
  onChangedRef.current = onResumesChanged

  const refresh = useCallback(async () => {
    if (!jobId) return
    try {
      const list = await listJobResumes(jobId)
      setBatch(list)
      onChangedRef.current?.(list)
    } catch {
      // transient fetch error — the next tick will retry
    }
  }, [jobId])

  // Switching roles: forget the previous role's batch and load the new one's.
  useEffect(() => {
    setBatch([])
    setRejected([])
    setPendingFiles([])
    setError(null)
    if (jobId) refresh()
    else onChangedRef.current?.([])
  }, [jobId, refresh])

  // Poll one endpoint for the whole batch while anything is still working.
  // The server turns stuck resumes into "failed", so this always stops.
  const hasWorking = batch.some((r) => r.status === 'uploaded' || r.status === 'parsing')
  useEffect(() => {
    if (!jobId || !hasWorking) return
    const timer = setInterval(refresh, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [jobId, hasWorking, refresh])

  function addFiles(fileList) {
    const incoming = Array.from(fileList).filter((f) =>
      ACCEPTED.some((ext) => f.name.toLowerCase().endsWith(ext))
    )
    if (incoming.length === 0) return
    setPendingFiles((prev) => [...prev, ...incoming])
  }

  function handleDrop(e) {
    e.preventDefault()
    setIsDragging(false)
    if (disabled) return
    addFiles(e.dataTransfer.files)
  }

  function removePending(name) {
    setPendingFiles((prev) => prev.filter((f) => f.name !== name))
  }

  async function handleUpload() {
    if (pendingFiles.length === 0 || !jobId) return
    setIsUploading(true)
    setError(null)
    try {
      const results = await uploadResumes(jobId, pendingFiles)
      setPendingFiles([])
      setRejected((prev) => [...results.filter((r) => !r.id), ...prev])
      await refresh()
    } catch (err) {
      setError(err.message || 'Upload failed. Is the backend running on port 8000?')
    } finally {
      setIsUploading(false)
    }
  }

  async function handleRetry(resumeId) {
    try {
      await retryResume(resumeId)
      await refresh()
    } catch (err) {
      setError(err.message || 'Could not retry this resume.')
    }
  }

  function statusStyle(status) {
    if (status === 'parsed') return 'bg-gold-soft text-ink'
    if (status === 'failed') return 'bg-red-50 text-red-700'
    return 'bg-blue-50 text-blue-700' // uploaded / parsing = still processing
  }

  function statusLabel(status) {
    if (status === 'parsed') return 'Parsed'
    if (status === 'failed') return 'Failed'
    return 'Processing…'
  }

  const slowHint = batch.some(
    (r) =>
      (r.status === 'uploaded' || r.status === 'parsing') &&
      r.status_changed_at &&
      Date.now() - new Date(r.status_changed_at).getTime() > SLOW_HINT_AFTER_MS
  )

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="font-display text-xl text-ink mb-1">Resumes</h2>
        <p className="text-sm text-ink-soft">
          Upload up to a few hundred at once. PDF and DOCX only.
        </p>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          if (!disabled) setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors ${
          disabled
            ? 'cursor-not-allowed border-line bg-white/40'
            : isDragging
            ? 'cursor-pointer border-gold bg-gold-soft/40'
            : 'cursor-pointer border-line bg-white hover:border-ink-soft'
        }`}
      >
        <p className="text-sm font-medium text-ink">
          {disabled
            ? 'Save a role first to enable uploads'
            : isDragging
            ? 'Drop resumes here'
            : 'Drag and drop resumes, or click to browse'}
        </p>
        {!disabled && (
          <p className="text-xs text-ink-soft">PDF, DOCX — up to 10MB per file</p>
        )}
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED.join(',')}
          disabled={disabled}
          onChange={(e) => e.target.files && addFiles(e.target.files)}
          className="hidden"
        />
      </div>

      {pendingFiles.length > 0 && (
        <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-white">
          {pendingFiles.map((f) => (
            <li
              key={f.name}
              className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
            >
              <span className="truncate text-ink">{f.name}</span>
              <button
                type="button"
                onClick={() => removePending(f.name)}
                className="shrink-0 text-xs text-ink-soft hover:text-ink"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      {pendingFiles.length > 0 && (
        <button
          type="button"
          onClick={handleUpload}
          disabled={isUploading}
          className="self-start rounded-md bg-gold px-4 py-2.5 text-sm font-medium text-ink transition-colors hover:bg-gold/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isUploading
            ? 'Uploading…'
            : `Upload ${pendingFiles.length} resume${pendingFiles.length > 1 ? 's' : ''}`}
        </button>
      )}

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      {slowHint && (
        <p className="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-700">
          Still waiting on some resumes. If nothing moves, check that the Celery worker is
          running — anything stuck will be marked failed automatically, and you can retry it.
        </p>
      )}

      {rejected.length > 0 && (
        <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-white">
          {rejected.map((f, i) => (
            <li key={`${f.filename}-${i}`} className="px-3 py-2 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="truncate text-ink">{f.filename}</span>
                <span className="shrink-0 rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
                  Rejected
                </span>
              </div>
              <p className="mt-0.5 text-xs text-ink-soft">{f.message}</p>
            </li>
          ))}
        </ul>
      )}

      {batch.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs font-medium text-ink-soft">Resumes for this role</p>
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-white">
            {batch.map((f) => (
              <li key={f.id} className="px-3 py-2 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate text-ink">{f.filename}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    {f.status === 'failed' && (
                      <button
                        type="button"
                        onClick={() => handleRetry(f.id)}
                        className="text-xs text-ink-soft underline hover:text-ink"
                      >
                        Retry
                      </button>
                    )}
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusStyle(f.status)}`}
                    >
                      {statusLabel(f.status)}
                    </span>
                  </span>
                </div>
                {f.status === 'failed' && f.error && (
                  <p className="mt-0.5 text-xs text-red-700">{f.error}</p>
                )}
                {f.status === 'parsed' && f.warning && (
                  <p className="mt-0.5 text-xs text-amber-700">
                    Keyword matching only — AI skill extraction failed: {f.warning}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
