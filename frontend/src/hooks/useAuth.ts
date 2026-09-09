/**
 * Hook delgado sobre AuthContext. Tira un error explícito si se usa
 * fuera de <AuthProvider>, en vez de devolver `undefined` en
 * silencio y romper más adelante con un mensaje confuso.
 */

import { useContext } from 'react'
import { AuthContext } from '@/context/AuthContext'

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth debe usarse dentro de un AuthProvider')
  }
  return context
}
