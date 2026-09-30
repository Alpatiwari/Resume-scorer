export function candidateLabel(row) {
  return row?.candidate_name || row?.filename || ''
}