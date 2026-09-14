import { useState } from 'react'
import { createJob } from '../api/apiClient.js'

export default function JobDescriptionForm({ onSubmit }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [experience, setExperience] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState(null)

  const canSubmit = title.trim() && description.trim() && !isSaving

  async function handleSubmit(e) {
    e.preventDefault()
    if (!canSubmit) return
    setIsSaving(true)
    setError(null)
    try {
      const job = await createJob({ title, description, experience })
      onSubmit?.(job)
    } catch (err) {
      setError(err.message || 'Could not save the role. Is the backend running?')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <div>
        <h2 className="font-display text-xl text-ink mb-1">Role details</h2>
        <p className="text-sm text-ink-soft">
          The more specific this is, the more accurate the scoring.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="job-title" className="text-sm font-medium text-ink">
          Job title
        </label>
        <input
          id="job-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Senior Backend Engineer"
          className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-ink placeholder:text-ink-soft/60 focus:border-gold"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="experience" className="text-sm font-medium text-ink">
          Experience level
        </label>
        <select
          id="experience"
          value={experience}
          onChange={(e) => setExperience(e.target.value)}
          className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-ink focus:border-gold"
        >
          <option value="">Select level</option>
          <option value="entry">Entry level (0–2 yrs)</option>
          <option value="mid">Mid level (2–5 yrs)</option>
          <option value="senior">Senior (5–8 yrs)</option>
          <option value="lead">Lead / Staff (8+ yrs)</option>
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="job-desc" className="text-sm font-medium text-ink">
          Job description
        </label>
        <textarea
          id="job-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Paste the full job description — responsibilities, required skills, and qualifications."
          rows={12}
          className="w-full resize-y rounded-md border border-line bg-white px-3 py-2 text-sm text-ink leading-relaxed placeholder:text-ink-soft/60 focus:border-gold"
        />
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      <button
        type="submit"
        disabled={!canSubmit}
        className="mt-1 rounded-md bg-ink px-4 py-2.5 text-sm font-medium text-paper transition-colors hover:bg-ink/90 disabled:cursor-not-allowed disabled:bg-ink/30"
      >
        {isSaving ? 'Saving…' : 'Save role'}
      </button>
    </form>
  )
}
