import { useRef, useState } from 'react'
import { uploadResumes, getResume } from '../api/apiClient.js'

const ACCEPTED = ['.pdf', '.docx']
const POLL_INTERVAL_MS = 1500
const MAX_POLL_ATTEMPTS = 40 // ~60s per resume before giving up

export default function UploadResumes({ disabled, onUploaded }) {
  const [isDragging, setIsDragging] = useState(false)
  const [pendingFiles, setPendingFiles] = useState([])
  const [uploadedFiles, setUploadedFiles] = useState([]) // [{id, filename, status, message}]
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

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

  // Polls a single resume's status until it's parsed/failed (or we give up),
  // then updates its row in the list and reports the final status upward
  // so Dashboard's parsedCount stays accurate.
  async function pollResumeStatus(resumeId, filename) {
    for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
      try {
        const record = await getResume(resumeId)
        if (record.status === 'parsed' || record.status === 'failed') {
          setUploadedFiles((prev) =>
            prev.map((f) =>
              f.id === resumeId
                ? { ...f, status: record.status, message: record.error || 'Parsed successfully.' }
                : f
            )
          )
          onUploaded?.([{ id: resumeId, filename, status: record.status }])
          return
        }
      } catch {
        // transient fetch error — just retry on the next tick
      }
    }
  }

  async function handleUpload() {
    if (pendingFiles.length === 0) return
    setIsUploading(true)
    setError(null)
    try {
      const results = await uploadResumes(pendingFiles)
      setUploadedFiles((prev) => [...results, ...prev])
      setPendingFiles([])
      onUploaded?.(results)

      results.forEach((r) => {
        if (r.status === 'uploaded' && r.id) {
          pollResumeStatus(r.id, r.filename)
        }
      })
    } catch (err) {
      setError(err.message || 'Upload failed. Is the backend running on port 8000?')
    } finally {
      setIsUploading(false)
    }
  }

  function statusStyle(status) {
    if (status === 'parsed') return 'bg-gold-soft text-ink'
    if (status === 'failed') return 'bg-red-50 text-red-700'
    return 'bg-blue-50 text-blue-700' // 'uploaded' = still processing
  }

  function statusLabel(status) {
    if (status === 'parsed') return 'Parsed'
    if (status === 'failed') return 'Failed'
    return 'Processing…'
  }

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

      {uploadedFiles.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs font-medium text-ink-soft">Recently uploaded</p>
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-white">
            {uploadedFiles.map((f, i) => (
              <li
                key={f.id || `${f.filename}-${i}`}
                className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
              >
                <span className="truncate text-ink">{f.filename}</span>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${statusStyle(f.status)}`}
                >
                  {statusLabel(f.status)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}