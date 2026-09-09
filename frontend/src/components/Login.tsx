import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'
import type { ApiErrorResponse } from '@/types/auth'

const DEFAULT_ERROR = 'No se pudo iniciar sesión. Intentá de nuevo.'

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isSubmitting) return

    setError(null)
    setIsSubmitting(true)
    try {
      await login(email, password)
      navigate('/dashboard')
    } catch (err) {
      // Solo el 401 de login tiene `detail` como string simple y
      // verificado (Fase A). Otros errores (422 de validación, red,
      // 500) no tienen esa forma garantizada, así que van con un
      // mensaje genérico en vez de mostrar lo que venga en `detail`.
      if (axios.isAxiosError<ApiErrorResponse>(err) && err.response?.status === 401) {
        setError(err.response.data.detail)
      } else {
        setError(DEFAULT_ERROR)
      }
      setIsSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto flex w-full max-w-sm flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          disabled={isSubmitting}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="password">Contraseña</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          disabled={isSubmitting}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Ingresando…' : 'Ingresar'}
      </Button>
    </form>
  )
}
