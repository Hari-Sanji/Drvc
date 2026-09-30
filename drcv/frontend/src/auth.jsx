import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler } from './api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [state, setState] = useState({ loading: true, user: null, permissions: [] })

  const logoutLocal = useCallback(() => {
    setToken(null)
    setState({ loading: false, user: null, permissions: [] })
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(logoutLocal)
    if (!getToken()) { setState((s) => ({ ...s, loading: false })); return }
    api.get('/auth/me')
      .then((d) => setState({ loading: false, user: d.user, permissions: d.permissions }))
      .catch(() => logoutLocal())
  }, [logoutLocal])

  const login = useCallback(async (email, password, remember = false, code = undefined) => {
    const d = await api.post('/auth/login', { email, password, remember, ...(code ? { code } : {}) })
    if (d.requires_2fa) return d // second step: the caller asks for the authenticator code
    setToken(d.token, remember)
    setState({ loading: false, user: d.user, permissions: d.permissions })
    return d
  }, [])

  // after a password change the server issues a fresh token (other sessions are signed out)
  const applySession = useCallback((d) => {
    let remember = false
    try { remember = !!localStorage.getItem('drcv-token') } catch { /* ignore */ }
    setToken(d.token, remember)
    setState({ loading: false, user: d.user, permissions: d.permissions })
  }, [])

  const refreshMe = useCallback(async () => {
    const d = await api.get('/auth/me')
    setState((st) => ({ ...st, user: d.user, permissions: d.permissions }))
  }, [])

  const logout = useCallback(async () => {
    try { await api.post('/auth/logout') } catch { /* ignore */ }
    logoutLocal()
  }, [logoutLocal])

  const value = useMemo(() => ({
    ...state, login, logout, applySession, refreshMe,
    can: (p) => state.permissions.includes(p),
  }), [state, login, logout, applySession, refreshMe])
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)
