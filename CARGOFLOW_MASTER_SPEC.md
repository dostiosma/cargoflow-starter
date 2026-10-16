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
| user_id | UUID | FK → users, único (1 User → 1 Driver) |
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

`delay_risk_score` solo se actualiza mientras el Shipment está en `in_transit`: `PATCH /api/shipments/{id}/risk` responde 400 en cualquier otro estado (contrato completo en la sección 7).

### Día operativo

Los timestamps se almacenan en UTC. El **día operativo** es el día calendario de la zona horaria `America/Bogota`: va de las 00:00 (inclusive) a las 00:00 del día siguiente (exclusive) en esa zona, y sus límites se convierten a UTC para compararlos con los timestamps almacenados. El **día operativo en curso** es el que contiene el instante de la consulta.

Es la definición de "día" del spec: cualquier regla que hable "del día" la referencia en lugar de redefinirla.

### Convención de nombres
Backend, base de datos y el contrato de API JSON: **snake_case**, siempre. El frontend en React/TypeScript puede usar camelCase en su propio código interno, pero al hablar con la API respeta snake_case tal como está definido en la sección 7 — no hay traducción de campos entre capas. Esto evita el problema de `user_id` / `userId` / `idUser` conviviendo en el mismo sistema.

---

## 7. Contrato de API

| Método | Ruta | Descripción | Usado por |
|---|---|---|---|
| POST | /api/auth/login | Login, devuelve JWT | React, Flutter |
| GET | /api/auth/me | Contexto del usuario autenticado (contrato abajo) | Flutter |
| GET | /api/orders | Listar pedidos | React |
| POST | /api/orders | Crear pedido (crea también su Shipment asociado, misma transacción; después del commit se programa el aviso a n8n definido en la sección 9) | React |
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

El aviso de pedido creado a n8n no es un endpoint de FastAPI: es una llamada saliente de FastAPI hacia n8n, definida en la sección 9.

Ningún chat/agente inventa un endpoint o campo que no esté en esta tabla. Si hace falta uno nuevo, se agrega aquí primero.

### `PATCH /api/shipments/{id}/risk` — body y respuestas

Body (obligatorio):

```json
{
  "delay_risk_score": "float, 0–1"
}
```

`delay_risk_score` es obligatorio y debe ser un float dentro del rango 0–1, ambos extremos incluidos.

Solo se actualiza con el Shipment en `in_transit`:

| Estado del Shipment | Resultado |
|---|---|
| `in_transit` | Permitido — actualiza `delay_risk_score` |
| `pending` | 400 |
| `assigned` | 400 |
| `delivered` | 400 |
| `cancelled` | 400 |

Respuestas:

| Código | Cuándo |
|---|---|
| 200 | Shipment actualizado (`ShipmentOut`) |
| 400 | El Shipment no está en `in_transit` |
| 401 | Autenticación ausente o inválida |
| 404 | Shipment inexistente |
| 422 | Body inválido o `delay_risk_score` fuera del rango 0–1 |

### `GET /api/auth/me` — respuesta

Devuelve el contexto del usuario autenticado (el del JWT), únicamente con estos campos:

```json
{
  "id": "UUID",
  "email": "string",
  "role": "admin | driver",
  "driver_id": "UUID | null"
}
```

- `id` es el `User.id` del usuario autenticado.
- `driver_id` es el `Driver.id` asociado al usuario (relación 1:1, sección 6), o `null` si el usuario no tiene Driver asociado.

El `{id}` de `GET /api/drivers/{id}/shipments` corresponde a `driver_id` (es decir, a `Driver.id`), no a `User.id`.

Respuestas:

| Código | Cuándo |
|---|---|
| 200 | Contexto del usuario autenticado |
| 401 | Autenticación ausente o inválida |

### `GET /api/drivers/{id}/shipments` — ruta del conductor

`{id}` es el `Driver.id` (UUID), no el `User.id`.

La ruta incluye los Shipments con `driver_id = {id}` que sean:

1. **Activos**: en estado `assigned` o `in_transit`.
2. **Terminales** (`delivered` o `cancelled`) cuya `actual_delivery` cae dentro del día operativo en curso (sección 6).

No se filtra por estado dentro de esos dos grupos: un `cancelled` terminado durante el día permanece visible. No hay parámetro `?date=`.

Orden: `assigned_at` ascendente; desempate por `id` ascendente.

Cada elemento de la lista usa este esquema propio de la ruta (`ShipmentOut` no se reutiliza ni se modifica):

```json
{
  "id": "UUID",
  "status": "assigned | in_transit | delivered | cancelled",
  "assigned_at": "timestamp",
  "estimated_delivery": "timestamp",
  "actual_delivery": "timestamp | null",
  "order": {
    "customer_name": "string",
    "origin_address": "string",
    "destination_address": "string",
    "priority": "normal | high | critical"
  }
}
```

`id`, `status`, `assigned_at`, `estimated_delivery` y `actual_delivery` son los campos homónimos del Shipment (sección 6); `order` es un resumen mínimo del Order del Shipment con campos ya existentes (sección 6). No se incluyen otros campos.

Autorización:

| Usuario | Resultado |
|---|---|
| `admin` | Puede consultar cualquier Driver |
| `driver` | Solo su propio `driver_id` (el de `GET /api/auth/me`); otro `{id}` → 403 |

La propiedad se comprueba antes de consultar si el Driver existe: un `driver` que pida un `{id}` ajeno recibe 403 exista o no ese Driver, por lo que el 404 solo se observa con rol `admin`. Un usuario `driver` sin Driver asociado no puede consultar ninguna ruta.

Respuestas:

| Código | Cuándo |
|---|---|
| 200 | Lista de la ruta; `[]` si el Driver existe y no tiene Shipments en la ruta |
| 401 | Autenticación ausente o inválida |
| 403 | Usuario `driver` consultando un `{id}` que no es el suyo |
| 404 | Driver inexistente |
| 422 | `{id}` no es un UUID válido |

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
El disparador es el aviso de pedido creado que FastAPI envía a n8n (subsección «Aviso de pedido creado (FastAPI → n8n)», más abajo).

**WF2 — Riesgo de retraso**
`Cron cada 15 min → GET /api/shipments?status=in_transit → n8n calcula delay_risk_score → PATCH /api/shipments/{id}/risk → FastAPI persiste, confirma (commit) y publica el evento risk_alert si delay_risk_score > 0.7 (sección 8) — n8n nunca publica el evento directamente`

**WF3 — Reporte diario** *(stretch, no bloquea el MVP)*
`Cron 18:00 → GET /reports/daily → armar resumen → enviar por email`

### Aviso de pedido creado (FastAPI → n8n)

Es una llamada HTTP saliente de FastAPI hacia n8n, no un endpoint de la sección 7. n8n la recibe en el nodo Webhook de WF1 y sigue sin escribir en PostgreSQL (sección 4).

**Cuándo.** `POST /api/orders` crea el Order y su Shipment en una misma transacción (sección 7). Solo después de confirmar el commit, FastAPI programa el envío del aviso con `BackgroundTasks`; nunca antes (misma regla que los eventos de la sección 8). La respuesta `201` no depende de la entrega del aviso: un fallo de comunicación no revierte la transacción ni modifica la respuesta.

**Destino.** `POST {N8N_WEBHOOK_URL}/order-created`. `N8N_WEBHOOK_URL` (variable de entorno existente) es la URL base de los webhooks de n8n. Si no está configurada, no se intenta enviar el aviso y se registra el problema en el log.

**Cuerpo** (JSON, `snake_case`):

```json
{
  "order_id": "UUID",
  "shipment_id": "UUID"
}
```

Contiene exclusivamente esos dos campos: no hay campo `event` ni otros. `shipment_id` es el Shipment creado junto con el Order; WF1 lo usa como `{id}` en `POST /api/shipments/{id}/assign`. Si WF1 necesita más datos, los consulta a la API.

**Autenticación.** La llamada incluye la cabecera `X-Webhook-Secret` con el valor de la variable de entorno `N8N_WEBHOOK_SECRET`. El nodo Webhook de n8n la valida con una credencial Header Auth. El mismo secreto debe estar configurado en ambos lados (FastAPI y n8n). Esta autenticación protege solo la recepción del aviso; la autenticación de n8n hacia FastAPI es un tema distinto y sigue pendiente (sección 10).

**Entrega (MVP).** Best-effort: FastAPI realiza un único intento por cada creación de pedido, sin reintentos automáticos, y no existe Transactional Outbox. El spec no garantiza la entrega del aviso. La implementación de este envío (D9-B) deberá:

- utilizar un timeout HTTP finito (este documento no fija su valor);
- considerar respuesta exitosa cualquier respuesta 2xx de n8n;
- registrar en el log las respuestas no 2xx y los errores de comunicación;
- no alterar el `201` de `POST /api/orders` en ningún caso.

**Recuperación.** Si el aviso no llega, el Shipment permanece en `pending`. WF1 tendrá un Cron que recuperará las asignaciones pendientes; su contrato detallado queda por definir y se documentará en esta sección antes de implementarlo. Recuperar asignaciones no es lo mismo que garantizar notificaciones.

**Notificaciones duplicadas.** La idempotencia de `POST /api/shipments/{id}/assign` impide asignar dos veces el mismo Shipment, pero por sí sola no evita notificaciones duplicadas. Para distinguir una asignación nueva de una repetida, la respuesta de `POST /api/shipments/{id}/assign` incluirá el campo `assignment_created` (contrato aprobado, pendiente de implementación en D9-C1): `true` cuando esa petición realizó una asignación nueva y `false` cuando la asignación ya existía. WF1 notificará únicamente cuando sea `true`.

---

## 10. Seguridad (nivel MVP, pero real)
- JWT con expiración corta + refresh token
- Contraseñas con bcrypt, nunca en texto plano
- Variables sensibles en `.env`, nunca commiteadas (`.env.example` sí va en el repo)
- `N8N_WEBHOOK_SECRET` es una variable sensible: se define en `.env` y nunca se escribe su valor en este documento ni en archivos versionados. Protege la recepción del aviso FastAPI → n8n (cabecera `X-Webhook-Secret`, sección 9) y debe coincidir con la credencial Header Auth configurada en n8n. No es la autenticación de n8n hacia FastAPI, que sigue pendiente de una decisión de seguridad separada.
- CORS configurado explícitamente para los orígenes conocidos (no `*`)
- Autorización por rol y propiedad: solo está definida para `GET /api/drivers/{id}/shipments` (sección 7). Para el resto de endpoints queda pendiente de una decisión de seguridad separada.

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

Dentro de `docker compose`, el backend alcanza a n8n por el nombre del servicio: `N8N_WEBHOOK_URL=http://n8n:5678/webhook`. `localhost` dentro del contenedor del backend apunta al propio backend, no a n8n. `http://localhost:5678/webhook` solo es válido cuando el backend se ejecuta directamente en el host, donde n8n publica el puerto 5678.

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
- El aviso de pedido creado (sección 9) debe tener pruebas de: su payload; la cabecera `X-Webhook-Secret`; que se ejecuta después del commit; la ausencia de `N8N_WEBHOOK_URL` (no se intenta enviar); una respuesta HTTP no 2xx; y un timeout o error de comunicación. En los casos de fallo, el `201` de `POST /api/orders` no se ve afectado.
- `docker compose up --build` levanta el sistema completo sin pasos manuales.
- El README explica cómo correrlo y qué decisiones se tomaron, y por qué.
- Puedes explicar cada decisión de este documento sin tenerlo abierto.

---

## 15. Cómo usar este documento con varios chats de IA
- Este documento es la única fuente de verdad. Ningún chat/agente decide un endpoint, campo o workflow por su cuenta.
- Si algo debe cambiar, se actualiza aquí primero, después se propaga al código.
- Idealmente un solo hilo mantiene el contexto completo del proyecto; los demás reciben tareas puntuales citando la sección exacta de este documento (ej. "implementa POST /api/orders tal como está en la sección 7").
