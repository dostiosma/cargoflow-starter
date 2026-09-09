/**
 * Tipos de autenticación.
 *
 * LoginRequest / TokenResponse reflejan 1:1 el contrato real de
 * POST /api/auth/login, verificado en backend/app/schemas.py y
 * backend/app/routers/auth.py — snake_case tal como lo define el
 * backend (sección 6 del master spec: no hay traducción de campos
 * entre capas al hablar con la API).
 *
 * El JWT (backend/app/auth.py::create_access_token) solo trae `sub`
 * (uuid del user como string) y `exp` — no incluye email ni role.
 * Por eso el email de sesión se guarda aparte, tomado del propio
 * formulario de login, no del token ni de un endpoint /me (no existe).
 */

export interface LoginRequest {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  /** Segundos hasta expirar. 1800 mientras JWT_EXPIRATION_MINUTES=30 en el backend. */
  expires_in: number
}

/** Forma genérica de error de FastAPI (HTTPException) — no es exclusivo de auth. */
export interface ApiErrorResponse {
  detail: string
}

/** Payload real del JWT emitido por el backend. */
export interface JwtPayload {
  sub: string
  exp: number
}

/**
 * Lo que persistimos en localStorage bajo una sola key.
 * expiresAt es epoch ms (derivado de expires_in en el login,
 * o del claim `exp` del JWT al restaurar sesión).
 */
export interface StoredSession {
  token: string
  email: string
  expiresAt: number
}

export type AuthStatus = 'authenticated' | 'unauthenticated'

export interface AuthState {
  token: string | null
  email: string | null
  status: AuthStatus
}

export type AuthAction =
  | { type: 'LOGIN'; payload: StoredSession }
  | { type: 'LOGOUT' }
  | { type: 'RESTORE_SESSION'; payload: StoredSession | null }
