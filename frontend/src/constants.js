// Hiring pipeline stages — must match STAGES in backend/app/routers/scoring.py
export const STAGES = [
    { value: 'new', label: 'New' },
    { value: 'shortlisted', label: 'Shortlisted' },
    { value: 'interview', label: 'Interview' },
    { value: 'offer', label: 'Offer' },
    { value: 'hired', label: 'Hired' },
    { value: 'rejected', label: 'Rejected' },
  ]
  
  export const STAGE_STYLES = {
    new: 'bg-paper text-ink-soft',
    shortlisted: 'bg-gold-soft text-ink',
    interview: 'bg-blue-50 text-blue-700',
    offer: 'bg-green-50 text-green-700',
    hired: 'bg-emerald-100 text-emerald-800',
    rejected: 'bg-red-50 text-red-700',
  }

// localStorage keys (kept in one place so logout can clear them)
export const TOKEN_KEY = 'resume-scorer:token'
export const LAST_ROLE_KEY = 'resume-scorer:last-role'