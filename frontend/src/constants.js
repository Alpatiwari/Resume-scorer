// Hiring pipeline stages — must match STAGES in backend/app/routers/scoring.py
export const STAGES = [
    { value: 'new', label: 'New' },
    { value: 'shortlisted', label: 'Shortlisted' },
    { value: 'interview', label: 'Interview' },
    { value: 'offer', label: 'Offer' },
    { value: 'rejected', label: 'Rejected' },
  ]
  
  export const STAGE_STYLES = {
    new: 'bg-paper text-ink-soft',
    shortlisted: 'bg-gold-soft text-ink',
    interview: 'bg-blue-50 text-blue-700',
    offer: 'bg-green-50 text-green-700',
    rejected: 'bg-red-50 text-red-700',
  }