/**
 * Hook delgado sobre ShipmentEventsContext. Tira un error explícito
 * si se usa fuera de <ShipmentEventsProvider>, igual que useAuth.
 */

import { useContext } from 'react'
import { ShipmentEventsContext } from '@/context/ShipmentEventsContext'

export function useShipmentEvents() {
  const context = useContext(ShipmentEventsContext)
  if (context === undefined) {
    throw new Error('useShipmentEvents debe usarse dentro de un ShipmentEventsProvider')
  }
  return context
}
