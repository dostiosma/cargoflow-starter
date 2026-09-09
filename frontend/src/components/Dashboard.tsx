/**
 * Placeholder del Dashboard. Todavía no hay orders/vehicles/shipments
 * ni reports (Sprint 3+) — esto solo existe para poder comprobar que
 * la ruta protegida y la sesión funcionan de punta a punta.
 */

import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'

export function Dashboard() {
  const { email, logout } = useAuth()

  return (
    <div className="mx-auto flex w-full max-w-sm flex-col gap-4 pt-8">
      <h1 className="text-lg font-medium">Bienvenido{email ? `, ${email}` : ''}</h1>
      <p className="text-sm text-muted-foreground">
        Sesión activa. Esto confirma que la ruta protegida y el login
        funcionan de punta a punta.
      </p>
      <Button type="button" onClick={logout}>
        Cerrar sesión
      </Button>
    </div>
  )
}
