import { useState } from 'react'

// "29 Sep, 3:17 AM" — the time is what tells same-day duplicates apart.
function formatCreated(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const sameYear = d.getFullYear() === new Date().getFullYear()
  return d.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    ...(sameYear ? {} : { year: 'numeric' }),
    hour: 'numeric',
    minute: '2-digit',
  })
}

function summary(role) {
  const resumes = `${role.resume_count} resume${role.resume_count === 1 ? '' : 's'}`
  if (role.scored_count > 0) return `${resumes} · ${role.scored_count} scored`
  if (role.resume_count > 0) return `${resumes} · not scored yet`
  return resumes
}

export default function RolesList({ roles, activeId, onSelect, onDelete }) {
  const [confirmId, setConfirmId] = useState(null) // role awaiting delete confirmation
  const [confirmEmpty, setConfirmEmpty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  if (!roles || roles.length === 0) return null

  // Empty = nothing uploaded, nothing scored. The open role is never bulk-removed:
  // it may be one you just created and are about to upload into.
  const emptyRoles = roles.filter(
    (r) => r.resume_count === 0 && r.scored_count === 0 && r.id !== activeId,
  )

  async function deleteOne(role) {
    setBusy(true)
    setError(null)
    try {
      await onDelete(role)
      setConfirmId(null)
    } catch (err) {
      setError(err.message || 'Could not delete the role.')
    } finally {
      setBusy(false)
    }
  }

  async function deleteEmpty() {
    setBusy(true)
    setError(null)
    let skipped = 0
    for (const role of emptyRoles) {
      try {
        await onDelete(role, { onlyIfEmpty: true })
      } catch {
        skipped += 1 // the server says it's no longer empty (or already gone)
      }
    }
    if (skipped) setError(`${skipped} role${skipped === 1 ? ' was' : 's were'} not removed because they are no longer empty.`)
    setConfirmEmpty(false)
    setBusy(false)
  }

  return (
    <div className="mb-6 flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-display text-xl text-ink">Your roles</h2>
        <span className="text-xs text-ink-soft">{roles.length} total</span>
      </div>

      <ul className="flex max-h-[26rem] flex-col divide-y divide-line overflow-y-auto rounded-md border border-line bg-white">
        {roles.map((role) => {
          const active = role.id === activeId

          if (confirmId === role.id) {
            const hasWork = role.resume_count > 0 || role.scored_count > 0
            return (
              <li key={role.id} className="bg-red-50 px-3 py-2 text-sm">
                <p className="font-medium text-ink">Delete “{role.title}”?</p>
                <p className="mt-0.5 text-xs text-ink-soft">
                  {hasWork
                    ? `This removes its ${role.scored_count} score${role.scored_count === 1 ? '' : 's'} and shortlist decisions. The resume files themselves are kept.`
                    : 'This role is empty.'}{' '}
                  This can’t be undone.
                </p>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => deleteOne(role)}
                    className="rounded-md bg-red-700 px-3 py-1 text-xs font-medium text-white hover:bg-red-800 disabled:opacity-50"
                  >
                    {busy ? 'Deleting…' : 'Delete role'}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => setConfirmId(null)}
                    className="rounded-md border border-line bg-white px-3 py-1 text-xs text-ink hover:bg-paper disabled:opacity-50"
                  >
                    Cancel
                  </button>
                </div>
              </li>
            )
          }

          return (
            <li key={role.id} className={`flex items-stretch ${active ? 'bg-gold-soft/60' : ''}`}>
              <button
                type="button"
                onClick={() => onSelect(role)}
                className={`flex min-w-0 flex-1 flex-col gap-0.5 px-3 py-2 text-left text-sm transition-colors ${
                  active ? '' : 'hover:bg-paper'
                }`}
              >
                <span className="truncate font-medium text-ink">{role.title}</span>
                <span className="text-xs text-ink-soft">{summary(role)}</span>
                {role.created_at && (
                  <span className="text-xs text-ink-soft/70">Created {formatCreated(role.created_at)}</span>
                )}
              </button>
              <button
                type="button"
                onClick={() => {
                  setError(null)
                  setConfirmEmpty(false)
                  setConfirmId(role.id)
                }}
                aria-label={`Delete role ${role.title}`}
                className="shrink-0 px-3 text-xs text-ink-soft hover:bg-red-50 hover:text-red-700"
              >
                Delete
              </button>
            </li>
          )
        })}
      </ul>

      {emptyRoles.length > 0 &&
        (confirmEmpty ? (
          <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-ink-soft">
            <p>
              Delete {emptyRoles.length} empty role{emptyRoles.length === 1 ? '' : 's'} (no resumes, no
              scores)? Roles with any resumes are never touched.
            </p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={deleteEmpty}
                className="rounded-md bg-red-700 px-3 py-1 font-medium text-white hover:bg-red-800 disabled:opacity-50"
              >
                {busy ? 'Deleting…' : 'Delete empty roles'}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setConfirmEmpty(false)}
                className="rounded-md border border-line bg-white px-3 py-1 text-ink hover:bg-paper disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => {
              setError(null)
              setConfirmId(null)
              setConfirmEmpty(true)
            }}
            className="self-start text-xs text-ink-soft underline hover:text-ink"
          >
            Clean up {emptyRoles.length} empty role{emptyRoles.length === 1 ? '' : 's'}
          </button>
        ))}

      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
    </div>
  )
}
