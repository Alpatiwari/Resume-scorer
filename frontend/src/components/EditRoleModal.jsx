import { useEffect, useState } from 'react'
import { getJob, updateJob } from '../api/apiClient.js'

const splitSkills = (text) =>
  text
    .split(/[,\n]/)
    .map((x) => x.trim())
    .filter(Boolean)

const field = 'w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-ink focus:border-gold'

// Edit a saved role. Only what you change is sent. Changing the description
// without touching the skill lists makes the server re-read the skills from it.
export default function EditRoleModal({ jobId, onClose, onSaved }) {
  const [original, setOriginal] = useState(null)
  const [title, setTitle] = useState('')
  const [experience, setExperience] = useState('')
  const [description, setDescription] = useState('')
  const [required, setRequired] = useState('')
  const [nice, setNice] = useState('')
  const [minYears, setMinYears] = useState('')
  const [loadError, setLoadError] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    getJob(jobId)
      .then((j) => {
        if (cancelled) return
        setOriginal(j)
        setTitle(j.title || '')
        setExperience(j.experience || '')
        setDescription(j.description || '')
        setRequired((j.required_skills || []).join(', '))
        setNice((j.nice_to_have_skills || []).join(', '))
        setMinYears(j.min_experience_years == null ? '' : String(j.min_experience_years))
      })
      .catch((e) => !cancelled && setLoadError(e.message || 'Could not load the role.'))
    return () => {
      cancelled = true
    }
  }, [jobId])

  // Build the PATCH body from what actually changed.
  function changes() {
    if (!original) return {}
    const c = {}
    if (title.trim() !== original.title) c.title = title.trim()
    if ((experience || '') !== (original.experience || '')) c.experience = experience
    if (description.trim() !== original.description) c.description = description.trim()
    if (required.trim() !== (original.required_skills || []).join(', ')) c.required_skills = splitSkills(required)
    if (nice.trim() !== (original.nice_to_have_skills || []).join(', ')) c.nice_to_have_skills = splitSkills(nice)
    const origYears = original.min_experience_years == null ? '' : String(original.min_experience_years)
    if (minYears.trim() !== origYears) c.min_experience_years = minYears.trim() === '' ? null : Number(minYears)
    return c
  }

  const pending = changes()
  const hasChanges = Object.keys(pending).length > 0
  const invalid = !title.trim() || !description.trim() || (minYears.trim() !== '' && Number.isNaN(Number(minYears)))
  const willReextract = 'description' in pending && !('required_skills' in pending)

  async function handleSave() {
    setSaving(true)
    setSaveError(null)
    try {
      const updated = await updateJob(jobId, pending)
      onSaved?.(updated, Object.keys(pending))
    } catch (e) {
      setSaveError(e.message || 'Could not save the role.')
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 px-4" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-lg border border-line bg-white p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h3 className="font-display text-lg text-ink">Edit role</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-sm text-ink-soft hover:bg-paper hover:text-ink"
          >
            Close
          </button>
        </div>

        {loadError && <p className="text-sm text-red-700">{loadError}</p>}
        {!original && !loadError && <p className="text-sm text-ink-soft">Loading…</p>}

        {original && (
          <div className="flex flex-col gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-ink" htmlFor="er-title">Job title</label>
              <input id="er-title" value={title} onChange={(e) => setTitle(e.target.value)} className={field} />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-ink" htmlFor="er-exp">Experience level</label>
              <select id="er-exp" value={experience} onChange={(e) => setExperience(e.target.value)} className={field}>
                <option value="">Select level</option>
                <option value="entry">Entry level (0–2 yrs)</option>
                <option value="mid">Mid level (2–5 yrs)</option>
                <option value="senior">Senior (5–8 yrs)</option>
                <option value="lead">Lead / Staff (8+ yrs)</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-ink" htmlFor="er-desc">Job description</label>
              <textarea
                id="er-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={8}
                className={`${field} resize-y leading-relaxed`}
              />
              {willReextract && (
                <p className="mt-1 text-xs text-ink-soft">
                  The skills below will be re-read from the new description when you save. Edit the skills
                  yourself if you want to keep your own list.
                </p>
              )}
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-ink" htmlFor="er-req">
                Required skills <span className="font-normal text-ink-soft">(comma separated)</span>
              </label>
              <textarea id="er-req" value={required} onChange={(e) => setRequired(e.target.value)} rows={2} className={field} />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-ink" htmlFor="er-nice">
                Nice-to-have skills <span className="font-normal text-ink-soft">(comma separated)</span>
              </label>
              <textarea id="er-nice" value={nice} onChange={(e) => setNice(e.target.value)} rows={2} className={field} />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-ink" htmlFor="er-years">
                Minimum years of experience <span className="font-normal text-ink-soft">(optional)</span>
              </label>
              <input
                id="er-years"
                value={minYears}
                onChange={(e) => setMinYears(e.target.value)}
                inputMode="decimal"
                placeholder="e.g. 2"
                className={`${field} max-w-[8rem]`}
              />
            </div>

            <p className="rounded-md bg-paper px-3 py-2 text-xs text-ink-soft">
              Saving doesn't change existing scores. Click "Score candidates" afterwards to re-score. Stages and
              notes are kept, and you don't need to upload the resumes again.
            </p>

            {saveError && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{saveError}</p>}

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleSave}
                disabled={saving || !hasChanges || invalid}
                className="rounded-md bg-ink px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {saving ? 'Saving…' : 'Save changes'}
              </button>
              <button type="button" onClick={onClose} className="text-sm text-ink-soft underline">
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
