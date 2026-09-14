/**
 * Layout de las páginas protegidas: Nav + el contenido de la ruta
 * activa (Outlet). Se monta una sola vez en App.tsx como elemento de
 * una ruta padre sin path (ver App.tsx) — Dashboard, OrdersList,
 * OrderDetail y Fleet son rutas hijas y comparten este layout.
 */

import { Outlet } from 'react-router-dom'
import { Nav } from '@/components/Nav'

export function Layout() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
      <Nav />
      <main>
        <Outlet />
      </main>
    </div>
  )
}
