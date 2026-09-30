import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext.jsx'
import { getAuthConfig } from '../api/apiClient.js'

const inputClass =
  'w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-ink placeholder:text-ink-soft/60 focus:border-gold'

export default function Login() {
  const { signIn, signUp } = useAuth()
  const [mode, setMode] = useState('signin') // 'signin' | 'signup'
  const [registrationOpen, setRegistrationOpen] = useState(false)
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  // Only offer "Create account" if the server allows sign-ups.
  useEffect(() => {
    let cancelled = false
    getAuthConfig()
      .then((c) => !cancelled && setRegistrationOpen(Boolean(c.registration_enabled)))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const isSignUp = mode === 'signup'
  const canSubmit = email.trim() && password && !busy

  function switchMode(next) {
    setMode(next)
    setError(null)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      if (isSignUp) await signUp({ email: email.trim(), password, fullName: fullName.trim() })
      else await signIn(email.trim(), password)
      // On success AuthContext sets the user and App swaps this page for the dashboard.
    } catch (err) {
      setError(err.message || 'Could not reach the server. Is the backend running?')
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <p className="font-display text-2xl text-ink">Resume Filter & Scorer</p>
          <p className="mt-1 text-sm text-ink-soft">
            {isSignUp ? 'Create your recruiter account.' : 'Sign in to screen and rank candidates.'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5 rounded-lg border border-line bg-white/60 p-6">
          {isSignUp && (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="full-name" className="text-sm font-medium text-ink">
                Name <span className="font-normal text-ink-soft">(optional)</span>
              </label>
              <input
                id="full-name"
                type="text"
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className={inputClass}
              />
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium text-ink">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className={inputClass}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium text-ink">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete={isSignUp ? 'new-password' : 'current-password'}
              required
              minLength={isSignUp ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
            />
            {isSignUp && <p className="text-xs text-ink-soft">At least 8 characters.</p>}
          </div>

          {error && (
            <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={!canSubmit}
            className="rounded-md bg-ink px-4 py-2.5 text-sm font-medium text-paper transition-colors hover:bg-ink/90 disabled:cursor-not-allowed disabled:bg-ink/30"
          >
            {busy ? (isSignUp ? 'Creating account…' : 'Signing in…') : isSignUp ? 'Create account' : 'Sign in'}
          </button>
        </form>

        {(registrationOpen || isSignUp) && (
          <p className="mt-4 text-center text-sm text-ink-soft">
            {isSignUp ? 'Already have an account?' : 'New here?'}{' '}
            <button
              type="button"
              onClick={() => switchMode(isSignUp ? 'signin' : 'signup')}
              className="text-ink underline hover:text-gold"
            >
              {isSignUp ? 'Sign in' : 'Create an account'}
            </button>
          </p>
        )}
      </div>
    </div>
  )
}
