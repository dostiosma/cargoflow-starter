/**
 * Barra de navegación entre las páginas protegidas. Bloque 3A.2 (actualizado en 3B.1):
 * estructura de navegación + botón de crear pedido. Vive en components/ porque es
 * reutilizable (la monta Layout, no una ruta puntual).
 *
 * El logout que antes vivía en el placeholder de Dashboard
 * (components/Dashboard.tsx) se centraliza acá para no repetirlo en
 * cada página.
 */

import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'

const LINKS = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/orders', label: 'Pedidos' },
  { to: '/fleet', label: 'Flota' },
] as const

export function Nav() {
  const { email, logout } = useAuth()

  return (
    <nav className="flex items-center justify-between border-b pb-4">
      <div className="flex gap-4">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              isActive ? 'text-sm font-medium' : 'text-sm text-muted-foreground'
            }
          >
            {link.label}
          </NavLink>
        ))}
      </div>
      <div className="flex items-center gap-3">
        {email && <span className="text-sm text-muted-foreground">{email}</span>}
        <Link to="/orders/new">
          <Button type="button">Crear pedido</Button>
        </Link>
        <Button type="button" onClick={logout}>
          Cerrar sesión
        </Button>
      </div>
    </nav>
  )
}
