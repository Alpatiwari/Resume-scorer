import { AuthProvider, useAuth } from './auth/AuthContext.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Login from './pages/Login.jsx'

function Gate() {
  const { user, checking } = useAuth()

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <p className="text-sm text-ink-soft">Loading…</p>
      </div>
    )
  }
  return user ? <Dashboard /> : <Login />
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  )
}