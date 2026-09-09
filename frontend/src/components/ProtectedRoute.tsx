/**
 * Guarda de ruta: si no hay sesión, redirige a /login. No hay un
 * estado de carga que chequear acá — el estado de AuthContext ya se
 * resuelve de forma síncrona antes del primer render (ver
 * AuthContext.tsx), así que el primer render de este componente ya
 * sabe si hay sesión válida o no.
 */

import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { status } = useAuth()

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />
  }

  return children
}
