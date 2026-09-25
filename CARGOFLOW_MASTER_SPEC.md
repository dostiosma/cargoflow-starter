# CargoFlow — Documento Maestro y Arquitectura

**Versión:** 0.3 · **Estado:** Sprint 0, arquitectura revisada · **Propósito:** proyecto de portafolio para aplicar a una vacante de desarrollador en XCargo (última milla, Colombia)

Este documento es la única fuente de verdad del proyecto. Cualquier cambio de arquitectura, modelo de datos o contrato de API se actualiza aquí primero, antes que en el código.

---

## 1. Visión

CargoFlow es una plataforma de gestión logística: pedidos, envíos, vehículos, conductores y estados de entrega, con asignación automática y alertas de retraso.

No es un ejercicio abstracto — XCargo opera exactamente este tipo de sistema todos los días: reparto de última milla para e-commerce en Colombia, con flota propia y conductores en ruta. El objetivo de CargoFlow es demostrar que puedes construir y explicar, de punta a punta, la misma clase de sistema que ellos operan.

---

## 2. Alcance

La vacante pide: Frontend, Backend, SQL/NoSQL, GitHub, Docker, Python, Node.js, Flutter. CargoFlow los toca todos — pero no todos al mismo nivel de profundidad. Esa es una decisión deliberada, no un recorte.

### 2.1 Núcleo — dominio profundo, debes poder explicar cada línea sin el documento delante
- Backend: FastAPI + PostgreSQL + SQLAlchemy + JWT
- Frontend: React + TypeScript (dashboard administrativo)
- Docker + Docker Compose
- Git/GitHub (branching, PRs, commits convencionales)

### 2.2 Alcance reducido pero real — funcional, deliberadamente más pequeño que "producción"
- **Flutter**: app de conductor con 4 pantallas (login, ruta del día, detalle de envío, confirmar entrega). Sin evidencia fotográfica ni GPS en el MVP.
- **n8n**: 3 workflows concretos (sección 9), no un "centro de automatización" completo.
- **Node.js**: un único servicio WebSocket para actualizar el dashboard en tiempo real. Nada más vive ahí.
- **Redis (NoSQL)**: cachea y publica el estado en vivo de los envíos. No es una segunda base de datos "porque la vacante lo pide" — tiene un trabajo concreto (sección 8).

### 2.3 Fuera de alcance del MVP — roadmap, no recorte
- Score de retraso con aprendizaje automático real (el MVP usa una fórmula simple basada en reglas — sección 6)
- Evidencia fotográfica y GPS en la app del conductor
- Tracking público para el cliente final
- Multi-tenant (varias empresas en la misma instancia)
- Integración real con Google Maps (coordenadas fijas/simuladas en el MVP)

Saber explicar *por qué* algo quedó fuera es tan valioso en la entrevista como lo que sí se construyó.

---

## 3. Usuarios y casos de uso

**Admin/operador** (React): crea pedidos, ve el estado de la flota, consulta reportes.
**Conductor** (Flutter): ve su ruta del día, actualiza el estado de una entrega.

Casos de uso principales:
1. Crear un pedido.
2. n8n asigna automáticamente vehículo y conductor disponibles.
3. El conductor ve su ruta y marca una entrega como completada.
4. El dashboard se actualiza en tiempo real (Node.js/WebSocket) cuando cambia un estado.
5. n8n detecta riesgo de retraso y genera una alerta.
6. El admin consulta el reporte de operación del día.

---

## 4. Arquitectura

```
┌─────────────┐     ┌──────────────┐
│  React Web  │     │   Flutter    │
│  (Admin)    │     │  (Conductor) │
└──────┬──────┘     └──────┬───────┘
       │                   │
       └─────────┬─────────┘
                  │ REST + JWT
                  ▼
           ┌─────────────┐
           │   FastAPI   │
           │  Core API   │
           └──────┬──────┘
                   │
     ┌─────────────┼─────────────┬─────────────┐
     ▼             ▼             ▼             ▼
┌──────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐
│PostgreSQL│  │  Redis  │  │ Node.js  │  │   n8n    │
│  datos   │  │ estado  │  │WebSocket │  │automa-   │
│          │  │en vivo  │  │ server   │  │tización  │
└──────────┘  └─────────┘  └──────────┘  └──────────┘
```

FastAPI es el único dueño de la lógica de negocio y de PostgreSQL. Node.js y n8n nunca escriben directamente en la base de datos — hablan con FastAPI por su API REST, igual que React y Flutter. Eso evita que dos sistemas distintos dejen los datos inconsistentes.

---

## 5. Stack y justificación

| Tecnología | Por qué |
|---|---|
| FastAPI | Tipado con Pydantic, documentación OpenAPI automática, async nativo |
| PostgreSQL | El dominio es fuertemente relacional (pedido → envío → vehículo/conductor); necesita joins y transacciones reales |
| React + TypeScript | Tipado en frontend, ecosistema maduro para dashboards |
| Redis | NoSQL con un trabajo concreto: cache y pub/sub del estado en vivo de los envíos |
| Node.js | Un único propósito (WebSocket), separado del core para no mezclar responsabilidades |
| Flutter | Una sola base de código para la app del conductor |
| n8n | Automatización visual — demuestra entender procesos de negocio, no solo escribir código |
| Docker Compose | Entorno reproducible con un comando |
| GitHub Actions | CI simple: tests + build en cada push |

### Decisiones descartadas (para la entrevista)
- **¿Django/Flask en vez de FastAPI?** Más boilerplate para el mismo resultado; FastAPI da documentación automática gratis.
- **¿MongoDB como base principal?** El dominio necesita relaciones e integridad referencial fuerte; NoSQL puro complicaría los reportes.
- **¿Microservicios completos?** Complejidad operativa injustificada para un MVP de portafolio. Node.js se separa solo donde aporta valor real.

---

## 6. Modelo de datos

**users**

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID | PK |
| email | string | único |
| password_hash | string | bcrypt |
| role | enum | admin / driver |
| created_at | timestamp | |

**drivers**

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users |
| name | string | |
| phone | string | |
| vehicle_id | UUID | FK → vehicles, nullable |
| status | enum | available / busy / offline |

**vehicles**

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID | PK |
| plate | string | |
| type | enum | motocarro / van / bicicleta |
| capacity_kg | int | |
| status | enum | available / in_use / maintenance |

**orders**

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID | PK |
| customer_name | string | |
| origin_address | string | |
| destination_address | string | |
| priority | enum | normal / high / critical |
| status | enum | pending / assigned / in_transit / delivered / cancelled |
| created_at | timestamp | |

**shipments**

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID | PK |
| order_id | UUID | FK → orders, único (1 Order → 1 Shipment) |
| vehicle_id | UUID | FK → vehicles, nullable hasta asignar |
| driver_id | UUID | FK → drivers, nullable hasta asignar |
| assigned_at | timestamp | nullable hasta asignar; se fija atómicamente junto con vehicle_id/driver_id |
| estimated_delivery | timestamp | nullable hasta asignar; ver "ETA operacional" más abajo |
| actual_delivery | timestamp | nullable; se fija al llegar a un estado terminal |
| status | enum | igual que orders.status; Shipment es la fuente de verdad operacional — ver "Máquina de estados operacional" más abajo |
| delay_risk_score | float | 0–1, calculado por n8n y persistido por FastAPI (sección 9); vuelve a `null` al salir de `in_transit` |

### Máquina de estados operacional

`Shipment` es la fuente de verdad del progreso operacional. Los cambios operacionales del Shipment se reflejan en `Order.status`; los cambios manuales de `Order` no controlan el progreso operacional del Shipment.

Transiciones válidas:
- `pending → assigned`: únicamente mediante `POST /api/shipments/{id}/assign` (sección 7).
- `assigned → in_transit → delivered`: mediante `PATCH /api/shipments/{id}/status` (Flutter).
- `pending / assigned / in_transit → cancelled`: mediante `PATCH /api/orders/{id}/status` (cancelación administrativa). La cancelación se propaga al Shipment y libera los recursos asignados, dentro de la misma transacción.
- `delivered` y `cancelled` son estados terminales.

Al asignar (`POST /api/shipments/{id}/assign`, idempotente — no reasigna un shipment que ya tiene vehicle_id/driver_id):
- `Shipment.status = assigned`, junto con `vehicle_id`, `driver_id` y `assigned_at`, se fijan atómicamente.
- `Vehicle.status = in_use`, `Driver.status = busy`.
- Un driver no puede tener más de un shipment activo simultáneamente.

Al llegar a un estado terminal (`delivered` o `cancelled`):
- `Vehicle.status = available`, `Driver.status = available`.
- `actual_delivery` se fija.
- `delay_risk_score` vuelve a `null`.

### ETA operacional (`estimated_delivery`)

`estimated_delivery` se fija en el momento de la asignación, no al crear el pedido: `estimated_delivery = assigned_at + 4 horas`, igual para las tres prioridades — `priority` no modifica `estimated_delivery`.

Las 4 horas son una decisión de diseño del MVP, no una estimación logística real (sin distancia, tráfico ni ruta real — ver sección 2.3).

**Fórmula del MVP para `delay_risk_score`** (regla simple, no ML — y así se presenta en la entrevista). Calculada por n8n (WF2, sección 9), persistida por FastAPI vía `PATCH /api/shipments/{id}/risk`:

```
risk_crudo = (tiempo_transcurrido / tiempo_estimado) * 0.8
           + (1 si priority == "critical" sino 0) * 0.2

delay_risk_score = min(1.0, risk_crudo)
```

`tiempo_transcurrido` y `tiempo_estimado` se miden desde `assigned_at` (ver "ETA operacional"). El componente temporal domina la fórmula; `priority == "critical"` adelanta la alerta, no la reemplaza. Alerta cuando `delay_risk_score > 0.7` (sección 9).

### Convención de nombres
Backend, base de datos y el contrato de API JSON: **snake_case**, siempre. El frontend en React/TypeScript puede usar camelCase en su propio código interno, pero al hablar con la API respeta snake_case tal como está definido en la sección 7 — no hay traducción de campos entre capas. Esto evita el problema de `user_id` / `userId` / `idUser` conviviendo en el mismo sistema.

---

## 7. Contrato de API

| Método | Ruta | Descripción | Usado por |
|---|---|---|---|
| POST | /api/auth/login | Login, devuelve JWT | React, Flutter |
| GET | /api/orders | Listar pedidos | React |
| POST | /api/orders | Crear pedido (crea también su Shipment asociado, misma transacción) | React |
| GET | /api/orders/{id} | Detalle de pedido | React |
| PATCH | /api/orders/{id}/status | Cancelación administrativa (ver "Máquina de estados operacional", sección 6) | React, n8n |
| GET | /api/shipments | Listar envíos (filtro opcional `?status=`) | React, n8n |
| GET | /api/shipments/{id} | Detalle de envío | React, Flutter |
| POST | /api/shipments/{id}/assign | Asigna vehículo y conductor disponibles (idempotente; FastAPI decide la selección, n8n no la duplica) | n8n |
| PATCH | /api/shipments/{id}/status | Actualizar estado (ej. "entregado") | Flutter |
| PATCH | /api/shipments/{id}/risk | Persiste `delay_risk_score` calculado por n8n (sección 6 y 9) | n8n |
| GET | /api/vehicles | Listar vehículos | React, n8n |
| PATCH | /api/vehicles/{id}/status | Cambiar disponibilidad manualmente (ej. `maintenance`) — WF1 no lo usa para asignar ni liberar recursos: eso es responsabilidad transaccional de FastAPI (sección 6, "Máquina de estados operacional") | n8n |
| GET | /api/drivers | Listar conductores | React, n8n |
| GET | /api/drivers/{id}/shipments | Ruta del día del conductor | Flutter |
| GET | /api/reports/daily | Métricas del día | React, n8n |
| POST | /api/webhooks/order-created | Dispara automatización interna | n8n (consume) |

Ningún chat/agente inventa un endpoint o campo que no esté en esta tabla. Si hace falta uno nuevo, se agrega aquí primero.

---

## 8. Eventos en tiempo real

Un solo canal: `shipment.status.changed`. Transporta dos tipos de evento, distinguidos por el campo `type`.

Payload cuando `type = "status_changed"`:

```json
{
  "type": "status_changed",
  "shipment_id": "UUID",
  "status": "pending | assigned | in_transit | delivered | cancelled"
}
```

Payload cuando `type = "risk_alert"` (se publica solo cuando `delay_risk_score > 0.7`, sección 6):

```json
{
  "type": "risk_alert",
  "shipment_id": "UUID",
  "delay_risk_score": "float, 0–1"
}
```

```
FastAPI persiste el cambio (status o delay_risk_score)
        │
        ▼
Confirma en PostgreSQL (commit) — el evento nunca se publica antes del commit
        │
        ▼
Publica el evento correspondiente en Redis (pub/sub)
        │
        ▼
Node.js está suscrito, lo recibe
        │
        ▼
Node.js lo reenvía por WebSocket tal cual, sin interpretarlo ni modificarlo
        │
        ▼
React discrimina el `type` recibido antes de interpretarlo, y actualiza el dashboard sin recargar
```

---

## 9. Automatización (n8n) — 3 workflows

**WF1 — Asignación automática**
`Webhook (pedido creado) → POST /api/shipments/{id}/assign → notificar`

**WF2 — Riesgo de retraso**
`Cron cada 15 min → GET /api/shipments?status=in_transit → n8n calcula delay_risk_score → PATCH /api/shipments/{id}/risk → FastAPI persiste, confirma (commit) y publica el evento risk_alert si delay_risk_score > 0.7 (sección 8) — n8n nunca publica el evento directamente`

**WF3 — Reporte diario** *(stretch, no bloquea el MVP)*
`Cron 18:00 → GET /reports/daily → armar resumen → enviar por email`

---

## 10. Seguridad (nivel MVP, pero real)
- JWT con expiración corta + refresh token
- Contraseñas con bcrypt, nunca en texto plano
- Variables sensibles en `.env`, nunca commiteadas (`.env.example` sí va en el repo)
- CORS configurado explícitamente para los orígenes conocidos (no `*`)

---

## 11. Docker

```
docker-compose.yml
├── frontend        (React, puerto 3000)
├── backend         (FastAPI, puerto 8000)
├── postgres        (puerto 5432)
├── redis           (puerto 6379)
├── notifications   (Node.js, puerto 4000)
└── n8n             (puerto 5678)
```

Objetivo: `docker compose up --build` levanta todo, sin pasos manuales adicionales.

---

## 12. Estrategia de Git
- Ramas: `main`, `develop`, `feature/<nombre>`
- Commits convencionales: `feat:`, `fix:`, `docs:`, `chore:`
- Pull requests incluso trabajando solo — demuestra proceso, no solo código.

---

## 13. Plan de sprints

| Sprint | Contenido |
|---|---|
| 0 | Este documento, repo, esqueleto de Docker, esquema de BD |
| 1 | Backend: auth + CRUD de orders/shipments/vehicles/drivers |
| 2 | Frontend: dashboard consumiendo el backend real |
| 3 | Flutter: login + ruta del día + actualizar estado |
| 4 | Node.js (WebSocket) + n8n (WF1 y WF2) |
| 5 | Tests, README, demo de 3 minutos, WF3 si alcanza el tiempo |

La duración de cada sprint depende de las horas por semana disponibles — no hay una fecha fija todavía.

---

## 14. Definition of Done
- Cada endpoint de la sección 7 tiene al menos un test.
- `docker compose up --build` levanta el sistema completo sin pasos manuales.
- El README explica cómo correrlo y qué decisiones se tomaron, y por qué.
- Puedes explicar cada decisión de este documento sin tenerlo abierto.

---

## 15. Cómo usar este documento con varios chats de IA
- Este documento es la única fuente de verdad. Ningún chat/agente decide un endpoint, campo o workflow por su cuenta.
- Si algo debe cambiar, se actualiza aquí primero, después se propaga al código.
- Idealmente un solo hilo mantiene el contexto completo del proyecto; los demás reciben tareas puntuales citando la sección exacta de este documento (ej. "implementa POST /api/orders tal como está en la sección 7").
