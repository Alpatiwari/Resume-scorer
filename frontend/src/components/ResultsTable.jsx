import { STAGES, STAGE_STYLES } from '../constants.js'
import { candidateLabel } from '../utils.js'

function SortHeader({ label, sortKey, activeKey, dir, onSort }) {
  const active = activeKey === sortKey
  return (
    <th
      className="px-4 py-3 font-medium"
      aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <button
        type="button"
        onClick={() => onSort?.(sortKey)}
        className={`inline-flex items-center gap-1 uppercase tracking-normal hover:text-ink ${active ? 'text-ink' : ''}`}
      >
        {label}
        <span aria-hidden="true" className="text-[10px]">
          {active ? (dir === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      </button>
    </th>
  )
}

export default function ResultsTable({
  results = [],
  onSelect,
  onToggleShortlist,
  onChangeStage,
  selectedIds = new Set(),
  onToggleSelect,
  onToggleSelectAll,
  allSelected,
  rankById = {},
  sortKey = 'score',
  sortDir = 'desc',
  onSort,
  noMatches = false,
}) {
  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-line bg-white/60 px-6 py-16 text-center">
        {noMatches ? (
          <>
            <p className="text-sm font-medium text-ink">No candidates match</p>
            <p className="text-sm text-ink-soft">Try a different search or loosen the filters.</p>
          </>
        ) : (
          <>
            <p className="text-sm font-medium text-ink">No candidates scored yet</p>
            <p className="text-sm text-ink-soft">
              Save a role and upload resumes, then click "Score candidates" to see the ranked list here.
            </p>
          </>
        )}
      </div>
    )
  }

  const everySelected = allSelected ?? results.every((r) => selectedIds.has(r.id))
  const sortProps = { activeKey: sortKey, dir: sortDir, onSort }

  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-white">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-normal text-ink-soft">
            <th className="px-4 py-3 font-medium">
              <input
                type="checkbox"
                aria-label="Select all"
                checked={everySelected}
                onChange={() => onToggleSelectAll?.()}
              />
            </th>
            <th className="px-4 py-3 font-medium">Shortlist</th>
            <th className="px-4 py-3 font-medium">Rank</th>
            <SortHeader label="Candidate" sortKey="name" {...sortProps} />
            <SortHeader label="Score" sortKey="score" {...sortProps} />
            <SortHeader label="Stage" sortKey="stage" {...sortProps} />
            <th className="px-4 py-3 font-medium">Matched skills</th>
            <th className="px-4 py-3 font-medium">Missing skills</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {results.map((r) => (
            <tr key={r.resume_id} onClick={() => onSelect?.(r)} className="cursor-pointer hover:bg-paper">
              <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  aria-label={`Select ${candidateLabel(r)}`}
                  checked={selectedIds.has(r.id)}
                  onChange={() => onToggleSelect?.(r)}
                />
              </td>
              <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                <input type="checkbox" checked={!!r.shortlisted} onChange={() => onToggleShortlist?.(r)} />
              </td>
              <td className="px-4 py-3 text-ink-soft">{rankById[r.id] ?? ''}</td>
              <td className="px-4 py-3">
                <p className="text-ink">{candidateLabel(r)}</p>
                {r.candidate_name && (
                  <p className="max-w-[14rem] truncate text-xs text-ink-soft" title={r.filename}>
                    {r.filename}
                  </p>
                )}
              </td>
              <td className="px-4 py-3">
                <span className="rounded-full bg-gold-soft px-2.5 py-0.5 text-xs font-medium text-ink">
                  {r.final_score}
                </span>
                {r.score_warnings?.length > 0 && (
                  <span
                    className="ml-1.5 cursor-help text-amber-600"
                    title={r.score_warnings.join('\n')}
                    aria-label="Score is degraded — open the breakdown for details"
                  >
                    ⚠
                  </span>
                )}
              </td>
              <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                <select
                  value={r.stage || 'new'}
                  onChange={(e) => onChangeStage?.(r, e.target.value)}
                  aria-label={`Hiring stage for ${candidateLabel(r)}`}
                  className={`rounded-full border-0 px-2 py-0.5 text-xs font-medium ${STAGE_STYLES[r.stage || 'new']}`}
                >
                  {STAGES.map((st) => (
                    <option key={st.value} value={st.value}>
                      {st.label}
                    </option>
                  ))}
                </select>
              </td>
              <td className="px-4 py-3 text-ink-soft">
                {r.matched_skills?.slice(0, 4).join(', ')}
                {r.matched_skills?.length > 4 ? '…' : ''}
              </td>
              <td className="px-4 py-3 text-ink-soft">
                {r.missing_skills?.slice(0, 4).join(', ')}
                {r.missing_skills?.length > 4 ? '…' : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
