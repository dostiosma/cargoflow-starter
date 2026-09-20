'use strict';

// Notification Service — reenvia por WebSocket lo que llega por Redis Pub/Sub.
// Unico canal: shipment.status.changed (ver seccion 8 del master spec).
// Sin logica de negocio: solo relay. FastAPI y Node.js/n8n nunca escriben
// directamente en la base de datos (seccion 4 del master spec).

const { WebSocketServer, WebSocket } = require('ws');
const { createClient } = require('redis');

const PORT = 4000;
const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const REDIS_CHANNEL = 'shipment.status.changed';

const wss = new WebSocketServer({ port: PORT });

function broadcast(message) {
  for (const client of wss.clients) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(message);
    }
  }
}

async function main() {
  const subscriber = createClient({ url: REDIS_URL });

  subscriber.on('error', (err) => {
    console.error('notification-service: error de Redis:', err);
  });

  await subscriber.connect();

  await subscriber.subscribe(REDIS_CHANNEL, (message) => {
    broadcast(message);
  });

  console.log(`notification-service: WebSocket escuchando en ws://localhost:${PORT}`);
  console.log(`notification-service: suscrito a "${REDIS_CHANNEL}" en ${REDIS_URL}`);
}

main().catch((err) => {
  console.error('notification-service: fallo al iniciar:', err);
  process.exit(1);
});
