import { useState } from 'react'
import { STAGES, STAGE_STYLES } from '../constants.js'
import { candidateLabel } from '../utils.js'

// Kanban view of the hiring pipeline: one column per stage, drag a card to
// another column to change the candidate's stage. Drag-and-drop doesn't work
// on touch screens, so every card also has a small stage dropdown.
export default function PipelineBoard({ results = [], onSelect, onChangeStage }) {
  const [draggingId, setDraggingId] = useState(null)
  const [overStage, setOverStage] = useState(null)

  if (results.length === 0) {
    return (
      <div className="rounded-lg border border-line bg-white/60 px-6 py-16 text-center text-sm text-ink-soft">
        No candidates to show on the board.
      </div>
    )
  }

  function handleDrop(e, stage) {
    e.preventDefault()
    const id = Number(e.dataTransfer.getData('text/plain'))
    setDraggingId(null)
    setOverStage(null)
    const row = results.find((r) => r.id === id)
    if (row && (row.stage || 'new') !== stage) onChangeStage?.(row, stage)
  }

  return (
    <div className="w-full max-w-full overflow-x-auto pb-3">
      <div className="flex min-w-max gap-3">
        {STAGES.map((st) => {
          const cards = results.filter((r) => (r.stage || 'new') === st.value)
          const isOver = overStage === st.value
          return (
            <div
              key={st.value}
              onDragOver={(e) => {
                e.preventDefault()
                if (overStage !== st.value) setOverStage(st.value)
              }}
              onDragLeave={(e) => {
                // ignore leave events fired when moving over a child card
                if (!e.currentTarget.contains(e.relatedTarget)) setOverStage(null)
              }}
              onDrop={(e) => handleDrop(e, st.value)}
              className={`flex w-48 shrink-0 flex-col rounded-lg border p-2 transition-colors ${
                isOver ? 'border-gold bg-gold-soft/60' : 'border-line bg-white/60'
              }`}
            >
              <div className="mb-2 flex items-center justify-between px-1">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STAGE_STYLES[st.value]}`}>
                  {st.label}
                </span>
                <span className="text-xs text-ink-soft">{cards.length}</span>
              </div>

              <div className="flex min-h-[4rem] max-h-[65vh] flex-col gap-2 overflow-y-auto">
                {cards.map((r) => (
                  <div
                    key={r.id}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData('text/plain', String(r.id))
                      e.dataTransfer.effectAllowed = 'move'
                      setDraggingId(r.id)
                    }}
                    onDragEnd={() => {
                      setDraggingId(null)
                      setOverStage(null)
                    }}
                    onClick={() => onSelect?.(r)}
                    className={`cursor-grab rounded-md border border-line bg-white p-2.5 text-left shadow-sm hover:border-gold active:cursor-grabbing ${
                      draggingId === r.id ? 'opacity-40' : ''
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="break-words text-sm text-ink">{candidateLabel(r)}</p>
                        {r.candidate_name && (
                          <p className="truncate text-[11px] text-ink-soft" title={r.filename}>
                            {r.filename}
                          </p>
                        )}
                      </div>
                      <span className="shrink-0 rounded-full bg-gold-soft px-2 py-0.5 text-xs font-medium text-ink">
                        {r.final_score}
                      </span>
                    </div>
                    {r.matched_skills?.length > 0 && (
                      <p className="mt-1 text-xs text-ink-soft">
                        {r.matched_skills.slice(0, 3).join(', ')}
                        {r.matched_skills.length > 3 ? '…' : ''}
                      </p>
                    )}
                    {r.notes && <p className="mt-1 truncate text-xs italic text-ink-soft">“{r.notes}”</p>}
                    <select
                      value={r.stage || 'new'}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => onChangeStage?.(r, e.target.value)}
                      aria-label={`Move ${candidateLabel(r)} to stage`}
                      className="mt-2 w-full rounded border border-line bg-paper px-1 py-0.5 text-xs text-ink"
                    >
                      {STAGES.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
                {cards.length === 0 && (
                  <p className="px-1 py-3 text-center text-xs text-ink-soft/70">Drop here</p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
