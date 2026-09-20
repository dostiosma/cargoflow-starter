# Notification Service — Node.js

Reenvia por WebSocket los eventos que FastAPI publica en Redis Pub/Sub. Un solo canal: `shipment.status.changed`. Ver seccion 8 del master spec.

No implementa autenticacion, rooms, filtros ni logica de negocio: es un relay puro Redis → WebSocket, broadcast a todos los clientes conectados.

## Como correrlo

```bash
cd notification-service
npm install
REDIS_URL=redis://localhost:6379 npm start
```

`REDIS_URL` es opcional — si no se define, usa `redis://localhost:6379` por defecto (mismo valor que `.env.example` en la raiz del proyecto).

El servidor WebSocket queda escuchando en `ws://localhost:4000`.

## Payload

Reenvia exactamente el mismo JSON que FastAPI publica en Redis, sin transformarlo:

```json
{
  "shipment_id": "<uuid>",
  "status": "pending | assigned | in_transit | delivered | cancelled"
}
```