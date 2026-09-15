/**
 * Página para crear un pedido. Block 3B.1: formulario que envía
 * POST /api/orders con los campos del contrato (OrderCreate) y
 * maneja estados de loading, error y éxito.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { createOrder } from '@/services/orders'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { OrderCreate, OrderPriority } from '@/types/orders'

const PRIORITY_OPTIONS: OrderPriority[] = ['normal', 'high', 'critical']

export function CreateOrder() {
  const navigate = useNavigate()

  const [formData, setFormData] = useState<OrderCreate>({
    customer_name: '',
    origin_address: '',
    destination_address: '',
    priority: 'normal',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    if (!success) return
    const timer = setTimeout(() => navigate('/orders'), 1500)
    return () => clearTimeout(timer)
  }, [success, navigate])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      // Validar campos requeridos
      if (!formData.customer_name.trim()) {
        setError('El nombre del cliente es requerido.')
        setLoading(false)
        return
      }
      if (!formData.origin_address.trim()) {
        setError('La dirección de origen es requerida.')
        setLoading(false)
        return
      }
      if (!formData.destination_address.trim()) {
        setError('La dirección de destino es requerida.')
        setLoading(false)
        return
      }

      // Armar el payload: si priority es 'normal' (default), se puede omitir o incluir
      // El backend acepta ambos, así que lo incluyo siempre por claridad
      const payload: OrderCreate = {
        customer_name: formData.customer_name.trim(),
        origin_address: formData.origin_address.trim(),
        destination_address: formData.destination_address.trim(),
        priority: formData.priority as OrderPriority,
      }

      await createOrder(payload)
      setSuccess(true)
    } catch (err) {
      console.error(err)
      if (axios.isAxiosError(err)) {
        // El 'detail' de FastAPI es string en errores de negocio, pero
        // en un 422 de validación de Pydantic es un array de objetos
        // ({loc, msg, type}) — renderizarlo directo como children de
        // JSX rompe React ("Objects are not valid as a React child").
        const detail = err.response?.data?.detail
        setError(typeof detail === 'string' ? detail : err.message || 'Error al crear el pedido.')
      } else {
        setError('Error al crear el pedido.')
      }
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="flex flex-col gap-4">
        <p role="status" className="text-sm text-green-600">
          ✓ Pedido creado exitosamente. Redirigiendo...
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 max-w-md">
      <h1 className="text-lg font-medium">Crear pedido</h1>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor="customer_name">Cliente *</Label>
          <Input
            id="customer_name"
            name="customer_name"
            type="text"
            value={formData.customer_name}
            onChange={handleChange}
            disabled={loading}
            required
          />
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="origin_address">Origen *</Label>
          <Input
            id="origin_address"
            name="origin_address"
            type="text"
            value={formData.origin_address}
            onChange={handleChange}
            disabled={loading}
            required
          />
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="destination_address">Destino *</Label>
          <Input
            id="destination_address"
            name="destination_address"
            type="text"
            value={formData.destination_address}
            onChange={handleChange}
            disabled={loading}
            required
          />
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="priority">Prioridad (opcional)</Label>
          <select
            id="priority"
            name="priority"
            value={formData.priority}
            onChange={handleChange}
            disabled={loading}
            className="rounded border border-input bg-background px-3 py-2 text-sm ring-offset-background"
          >
            {PRIORITY_OPTIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        <Button type="submit" disabled={loading}>
          {loading ? 'Creando...' : 'Crear pedido'}
        </Button>
      </form>
    </div>
  )
}
