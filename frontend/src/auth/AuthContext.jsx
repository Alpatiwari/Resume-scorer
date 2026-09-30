import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import {
  getMe,
  getToken,
  login as apiLogin,
  register as apiRegister,
  setToken,
  setUnauthorizedHandler,
} from '../api/apiClient.js'
import { LAST_ROLE_KEY, TOKEN_KEY } from '../constants.js'

const AuthContext = createContext(null)

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // True while we check a saved token with the server, so a refresh doesn't flash the login page.
  const [checking, setChecking] = useState(() => Boolean(getToken()))

  const logout = useCallback(() => {
    setToken(null)
    try {
      // The "reopen last role" hint belongs to the person who just left.
      localStorage.removeItem(LAST_ROLE_KEY)
    } catch {
      // storage unavailable — nothing to clear
    }
    setUser(null)
  }, [])

  // Any 401 from the API (expired token, deactivated account) signs the user out.
  useEffect(() => {
    setUnauthorizedHandler(logout)
    return () => setUnauthorizedHandler(null)
  }, [logout])

  // On first load, validate a saved token.
  useEffect(() => {
    if (!getToken()) {
      setChecking(false)
      return undefined
    }
    let cancelled = false
    getMe()
      .then((me) => !cancelled && setUser(me))
      .catch(() => {
        // 401 already triggered logout(). Any other failure (backend down) leaves the
        // saved token alone and shows the login page; signing in again replaces it.
      })
      .finally(() => !cancelled && setChecking(false))
    return () => {
      cancelled = true
    }
  }, [])

  // Signing out (or in) in another tab applies here too.
  useEffect(() => {
    function onStorage(e) {
      if (e.key === TOKEN_KEY && !e.newValue) setUser(null)
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const signIn = useCallback(async (email, password) => {
    const data = await apiLogin({ email, password })
    setToken(data.access_token)
    setUser(data.user)
  }, [])

  const signUp = useCallback(async ({ email, password, fullName }) => {
    const data = await apiRegister({ email, password, fullName })
    setToken(data.access_token)
    setUser(data.user)
  }, [])

  const value = useMemo(
    () => ({ user, checking, signIn, signUp, logout }),
    [user, checking, signIn, signUp, logout]
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
