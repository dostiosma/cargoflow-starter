/**
 * ShipmentEventsContext: distribuye los eventos del canal
 * shipment.status.changed que llegan por WebSocket desde el
 * Notification Service Node.js (VITE_WS_URL, ver sección 8 del master
 * spec).
 *
 * Único propósito: conectar, recibir, parsear el JSON, discriminar el
 * `type` y exponer el último status_changed recibido. No conoce el
 * dominio de shipments — esa reconciliación vive en quien lo consume
 * (Dashboard). Mismo patrón de archivo que AuthContext (Context y
 * Provider colocados), pero con useState en vez de useReducer: acá no
 * hay una máquina de estados real (sin restore desde storage, sin
 * múltiples transiciones) que justifique un reducer.
 *
 * La sección 8 define dos tipos de evento en el mismo canal,
 * distinguidos por `type`, y exige que React lo discrimine antes de
 * interpretar el mensaje:
 *   - status_changed: se expone como `lastEvent`.
 *   - risk_alert: se reconoce y se descarta (sin estado ni re-render).
 *     El spec no define ningún efecto en React para este tipo, así que
 *     no se inventa ninguno (ni estado, ni conteo, ni UI).
 *   - sin `type`, `type` desconocido o forma inválida: se ignora
 *     (console.warn). Mensaje que no es JSON: se ignora (console.error).
 *
 * `lastEvent` conserva solo el último status_changed: un risk_alert
 * posterior no lo reemplaza. Limitación conocida, fuera de este bloque:
 * un nuevo status_changed reemplaza al anterior (no hay acumulación ni
 * historial de eventos).
 *
 * Sin reconexión automática, sin heartbeat, sin autenticación: si el
 * servidor cierra la conexión, se deja de recibir eventos hasta que
 * el usuario recargue la página.
 */

import { createContext, useEffect, useMemo, useState, type ReactNode } from 'react'

interface ShipmentStatusChangedEvent {
  type: 'status_changed'
  shipment_id: string
  status: string
}

interface ShipmentRiskAlertEvent {
  type: 'risk_alert'
  shipment_id: string
  delay_risk_score: number
}

type ShipmentEvent = ShipmentStatusChangedEvent | ShipmentRiskAlertEvent

interface ShipmentEventsContextValue {
  lastEvent: ShipmentStatusChangedEvent | null
}

// Discrimina por `type` (sección 8) y comprueba solo la forma del payload
// (que los campos existan con el tipo correcto), no el valor de `status`.
// Devuelve null si el mensaje no es un evento reconocido: sin `type`,
// `type` desconocido o campos con tipo incorrecto.
function parseShipmentEvent(raw: unknown): ShipmentEvent | null {
  if (typeof raw !== 'object' || raw === null) return null
  const { type, shipment_id, status, delay_risk_score } = raw as Record<string, unknown>
  if (typeof shipment_id !== 'string') return null
  if (type === 'status_changed' && typeof status === 'string') {
    return { type, shipment_id, status }
  }
  if (type === 'risk_alert' && typeof delay_risk_score === 'number') {
    return { type, shipment_id, delay_risk_score }
  }
  return null
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
      let raw: unknown
      try {
        raw = JSON.parse(event.data)
      } catch (err) {
        console.error('ShipmentEventsProvider: mensaje inválido', err)
        return
      }

      const parsed = parseShipmentEvent(raw)
      if (parsed === null) {
        console.warn('ShipmentEventsProvider: evento ignorado (sin type, type desconocido o forma inválida)', raw)
        return
      }

      // risk_alert: reconocido, sin efecto (ver comentario de cabecera).
      if (parsed.type === 'status_changed') {
        setLastEvent(parsed)
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
