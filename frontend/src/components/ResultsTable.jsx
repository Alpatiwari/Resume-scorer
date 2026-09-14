import { STAGES, STAGE_STYLES } from '../constants.js'

export default function ResultsTable({ results = [], onSelect, onToggleShortlist, onChangeStage }) {
  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-line bg-white/60 px-6 py-16 text-center">
        <p className="text-sm font-medium text-ink">No candidates scored yet</p>
        <p className="text-sm text-ink-soft">
          Save a role and upload resumes, then click "Score candidates" to see the ranked list here.
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-white">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-normal text-ink-soft">
            <th className="px-4 py-3 font-medium">Shortlist</th>
            <th className="px-4 py-3 font-medium">Rank</th>
            <th className="px-4 py-3 font-medium">Candidate</th>
            <th className="px-4 py-3 font-medium">Score</th>
            <th className="px-4 py-3 font-medium">Stage</th>
            <th className="px-4 py-3 font-medium">Matched skills</th>
            <th className="px-4 py-3 font-medium">Missing skills</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {results.map((r, i) => (
            <tr
              key={r.resume_id}
              onClick={() => onSelect?.(r)}
              className="cursor-pointer hover:bg-paper"
            >
              <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  checked={!!r.shortlisted}
                  onChange={() => onToggleShortlist?.(r)}
                />
              </td>
              <td className="px-4 py-3 text-ink-soft">{i + 1}</td>
              <td className="px-4 py-3 text-ink">{r.filename}</td>
              <td className="px-4 py-3">
                <span className="rounded-full bg-gold-soft px-2.5 py-0.5 text-xs font-medium text-ink">
                  {r.final_score}
                </span>
              </td>
              <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                <select
                  value={r.stage || 'new'}
                  onChange={(e) => onChangeStage?.(r, e.target.value)}
                  aria-label={`Hiring stage for ${r.filename}`}
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