/**
 * Cliente HTTP + integración con el backend de auth.
 *
 * `apiClient` es el axios para endpoints PROTEGIDOS: agrega
 * Authorization automáticamente y, si el backend responde 401,
 * interpreta que el token es inválido/venció, limpia la sesión y
 * manda a /login.
 *
 * `login()` a propósito NO usa `apiClient`: llama a POST
 * /api/auth/login con axios "pelado". Un login fallido (contraseña
 * incorrecta) también devuelve 401, pero significa algo distinto a
 * "sesión vencida" — no debe limpiar una sesión existente ni pasar
 * por el interceptor de abajo. Separar los dos casos por
 * construcción, en vez de detectarlos con un `if` dentro de un único
 * interceptor compartido, evita por diseño cualquier loop o efecto
 * cruzado entre ambos.
 */

import axios from 'axios'
import type { AxiosError } from 'axios'
import type { LoginRequest, TokenResponse, StoredSession } from '@/types/auth'

const BASE_URL = import.meta.env.VITE_API_URL
const LOGIN_PATH = '/api/auth/login'
const STORAGE_KEY = 'cargoflow.session'

/* ---------- Persistencia de sesión (localStorage) ---------- */

export function getStoredSession(): StoredSession | null {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as StoredSession
  } catch {
    return null
  }
}

export function setStoredSession(session: StoredSession): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
}

export function clearStoredSession(): void {
  localStorage.removeItem(STORAGE_KEY)
}

/* ---------- Cliente para endpoints protegidos ---------- */

export const apiClient = axios.create({ baseURL: BASE_URL })

apiClient.interceptors.request.use((config) => {
  const session = getStoredSession()
  if (session) {
    config.headers.Authorization = `Bearer ${session.token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      clearStoredSession()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

/* ---------- Login ---------- */

export async function login(email: string, password: string): Promise<TokenResponse> {
  const body: LoginRequest = { email, password }
  const { data } = await axios.post<TokenResponse>(`${BASE_URL}${LOGIN_PATH}`, body)
  return data
}
