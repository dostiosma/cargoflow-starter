/**
 * ShipmentEventsContext: distribuye el evento shipment.status.changed
 * que llega por WebSocket desde el Notification Service Node.js
 * (VITE_WS_URL, ver sección 8 del master spec).
 *
 * Único propósito: conectar, recibir, parsear el JSON y exponer el
 * último evento recibido tal cual. No interpreta el evento ni conoce
 * el dominio de shipments — esa reconciliación vive en quien lo
 * consume (Dashboard). Mismo patrón de archivo que AuthContext
 * (Context y Provider colocados), pero con useState en vez de
 * useReducer: acá no hay una máquina de estados real (sin restore
 * desde storage, sin múltiples transiciones) que justifique un
 * reducer.
 *
 * Sin reconexión automática, sin heartbeat, sin autenticación: si el
 * servidor cierra la conexión, se deja de recibir eventos hasta que
 * el usuario recargue la página.
 */

import { createContext, useEffect, useMemo, useState, type ReactNode } from 'react'

interface ShipmentStatusChangedEvent {
  shipment_id: string
  status: string
}

interface ShipmentEventsContextValue {
  lastEvent: ShipmentStatusChangedEvent | null
}

const WS_URL = import.meta.env.VITE_WS_URL

// Context y Provider viven juntos a propósito (useShipmentEvents.ts va
// a necesitar el Context) — esto solo le quita Fast Refresh a este
// export puntual, no afecta a ShipmentEventsProvider ni al resto del
// archivo.
// eslint-disable-next-line react-refresh/only-export-components
export const ShipmentEventsContext = createContext<ShipmentEventsContextValue | undefined>(
  undefined,
)

export function ShipmentEventsProvider({ children }: { children: ReactNode }) {
  const [lastEvent, setLastEvent] = useState<ShipmentStatusChangedEvent | null>(null)

  useEffect(() => {
    const socket = new WebSocket(WS_URL)

    socket.onmessage = (event) => {
      try {
        setLastEvent(JSON.parse(event.data))
      } catch (err) {
        console.error('ShipmentEventsProvider: mensaje inválido', err)
      }
    }

    socket.onerror = (err) => {
      console.error('ShipmentEventsProvider: error de WebSocket', err)
    }

    socket.onclose = () => {
      console.log('ShipmentEventsProvider: conexión WebSocket cerrada')
    }

    return () => socket.close()
  }, [])

  const value = useMemo<ShipmentEventsContextValue>(() => ({ lastEvent }), [lastEvent])

  return (
    <ShipmentEventsContext.Provider value={value}>{children}</ShipmentEventsContext.Provider>
  )
}
