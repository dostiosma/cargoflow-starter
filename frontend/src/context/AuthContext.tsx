/**
 * AuthContext: estado de autenticación global vía Context API +
 * useReducer (sin Redux/Zustand/TanStack Query, según lo aprobado).
 *
 * RESTORE_SESSION se resuelve de forma síncrona, ANTES del primer
 * render, leyendo localStorage en el inicializador diferido de
 * useReducer — no hay estado "restaurando" ni parpadeo: el primer
 * render ya sabe si hay sesión válida o no. Si el `expiresAt`
 * guardado ya venció, se descarta y se limpia localStorage (no hay
 * refresh token: una sesión vencida siempre vuelve a /login).
 */

import { createContext, useCallback, useMemo, useReducer, type ReactNode } from 'react'
import type { AuthAction, AuthState, StoredSession } from '@/types/auth'
import {
  clearStoredSession,
  getStoredSession,
  login as apiLogin,
  setStoredSession,
} from '@/services/api'

const UNAUTHENTICATED_STATE: AuthState = { token: null, email: null, status: 'unauthenticated' }

function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case 'LOGIN':
      return { token: action.payload.token, email: action.payload.email, status: 'authenticated' }
    case 'LOGOUT':
      return UNAUTHENTICATED_STATE
    case 'RESTORE_SESSION':
      return action.payload
        ? { token: action.payload.token, email: action.payload.email, status: 'authenticated' }
        : UNAUTHENTICATED_STATE
    default:
      return state
  }
}

// Lee localStorage y descarta la sesión si ya venció (comparando
// contra el `expiresAt` calculado en el login, no contra el JWT:
// no hace falta decodificarlo de nuevo).
function readValidSession(): StoredSession | null {
  const session = getStoredSession()
  if (!session) return null
  if (session.expiresAt <= Date.now()) {
    clearStoredSession()
    return null
  }
  return session
}

function init(): AuthState {
  return authReducer(UNAUTHENTICATED_STATE, {
    type: 'RESTORE_SESSION',
    payload: readValidSession(),
  })
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

// Context y Provider viven juntos a propósito (useAuth.ts va a
// necesitar el Context) — esto solo le quita Fast Refresh a este
// export puntual, no afecta a AuthProvider ni al resto del archivo.
// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, undefined, init)

  const login = useCallback(async (email: string, password: string) => {
    const response = await apiLogin(email, password)
    const session: StoredSession = {
      token: response.access_token,
      email,
      expiresAt: Date.now() + response.expires_in * 1000,
    }
    setStoredSession(session)
    dispatch({ type: 'LOGIN', payload: session })
  }, [])

  const logout = useCallback(() => {
    clearStoredSession()
    dispatch({ type: 'LOGOUT' })
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, login, logout }),
    [state, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
