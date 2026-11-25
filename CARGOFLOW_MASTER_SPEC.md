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
- **n8n**: WF1 y WF2 en el MVP; WF3 está definido pero permanece inactivo y fuera del MVP (sección 9). No es un "centro de automatización" completo.
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
| created_at | timestamp | No nulo en la base de datos (NOT NULL). Lo asigna FastAPI al crear el pedido, dentro del punto de serialización de la cola y con el reloj de PostgreSQL en UTC; el cliente no lo envía y ningún valor puede fijarse antes de ese punto (sección 6, «Cola de pendientes y garantía FIFO»). El orden de `GET /api/shipments` depende de este campo (sección 7) |

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
- `pending → assigned`: únicamente mediante `POST /api/shipments/{id}/assign` (sección 7), y solo para el siguiente de la cola de pendientes (ver «Cola de pendientes y garantía FIFO», más abajo).
- `assigned → in_transit → delivered`: mediante `PATCH /api/shipments/{id}/status` (Flutter).
- `pending / assigned / in_transit → cancelled`: mediante `PATCH /api/orders/{id}/status` (cancelación administrativa). La cancelación se propaga al Shipment y libera los recursos asignados, dentro de la misma transacción.
- `delivered` y `cancelled` son estados terminales.

Al asignar (`POST /api/shipments/{id}/assign`, idempotente — si el Shipment ya no está `pending`, no modifica nada; si está `pending` y no es el siguiente de la cola, responde 409 sin modificar nada; si está `pending` con `vehicle_id`, `driver_id`, `assigned_at` o `estimated_delivery` ya fijados, responde 500 sin modificar nada (ver «Cola de pendientes y garantía FIFO», más abajo); respuestas en la sección 7):
- `Shipment.status = assigned`, junto con `vehicle_id`, `driver_id` y `assigned_at`, se fijan atómicamente.
- `Vehicle.status = in_use`, `Driver.status = busy`.
- Un driver no puede tener más de un shipment activo simultáneamente.

Al llegar a un estado terminal (`delivered` o `cancelled`):
- `Vehicle.status = available`, `Driver.status = available`.
- `actual_delivery` se fija.
- `delay_risk_score` vuelve a `null`.

### Cola de pendientes y garantía FIFO

**Cola y orden.** La cola de pendientes es el conjunto de Shipments en `pending`. Su orden es `orders.created_at` ascendente y, como desempate, `shipments.id` ascendente; la prioridad (`priority`) no altera el orden. El siguiente es el primero de la cola.

**Garantía.** Ninguna asignación adelanta a un Shipment anterior que siga `pending`, sea cual sea el cliente que la solicite: WF1 desde el Webhook o desde el Cron, un admin u otro cliente autorizado. Solo FastAPI impone la garantía; ningún cliente puede saltarse la cola y n8n no la reimplementa. Con FIFO estricto solo un Shipment es elegible a la vez, así que las asignaciones son secuenciales por definición.

**Operaciones sobre la cola.**

| Operación | Efecto sobre la cola | Punto de serialización |
|---|---|---|
| Crear pedido y Shipment (`POST /api/orders`) | Añade un Shipment al final | Sí: se toma antes de generar `created_at` y se mantiene hasta el commit |
| Asignar (`POST /api/shipments/{id}/assign`) | Retira un Shipment (`pending → assigned`) | Sí: se toma antes de cualquier bloqueo de fila y se mantiene hasta el commit |
| Cancelar un pedido cuyo Shipment está `pending` (`PATCH /api/orders/{id}/status`) | Retira un Shipment (`pending → cancelled`) | No |
| Resto de transiciones (`assigned → in_transit → delivered`, cancelación de Shipments que no están `pending`, riesgo) | Ninguno: no afectan a `pending` | No |

No existe otra operación que añada Shipments a `pending` ni que los retire de él: `pending` solo se abandona por asignación o por cancelación, y `PATCH /api/shipments/{id}/status` no admite `pending` como estado de origen. Cancelar no toma el punto de serialización porque solo retira Shipments y retirar nunca adelanta a nadie: la comprobación del siguiente lee estado confirmado, de modo que una cancelación sin confirmar deja a los posteriores en espera (409) y una confirmada los hace elegibles.

**Punto de serialización.** Es una única exclusión mutua de PostgreSQL, de ámbito de transacción, con una clave fija reservada para la cola de pendientes. Crear pedido y asignar la toman antes de cualquier bloqueo de fila y la mantienen hasta confirmar o revertir la transacción; la liberación es automática. Se implementa con un bloqueo consultivo de transacción de PostgreSQL (`pg_advisory_xact_lock`), con estas condiciones:
- Se adquiere en la misma sesión y transacción de PostgreSQL (la misma conexión) en la que se ejecutan después todas las lecturas y escrituras de la operación, hasta su commit o rollback. No se usa el bloqueo consultivo de sesión.
- La clave es una constante de la aplicación, no se deriva de datos del cliente y ningún otro código la usa.
- Ninguna lectura que decida la operación (existencia, estado del Shipment, posición en la cola, disponibilidad de recursos) se hace antes de adquirirlo ni se reutiliza de un objeto cargado antes: cada una se ejecuta en una sentencia posterior a la adquisición.
- No existe otra vía que cree Shipments `pending` ni que los saque de `pending` (tabla anterior). Los scripts o datos de prueba que insertan pedidos directamente en PostgreSQL no pasan por el mecanismo y quedan fuera de la garantía.

**Límites de espera y de duración.** Una transacción detenida mientras mantiene el punto bloquearía toda creación de pedidos y toda asignación, así que están acotados tanto la espera por el punto como el tiempo que se lo retiene. Son límites distintos y ninguno sustituye al otro:
- **Espera por un bloqueo.** `lock_timeout` de PostgreSQL limita cada intento de adquirir un bloqueo (el punto de serialización o la fila de un Shipment). No limita la duración total de la petición, no se acumula entre adquisiciones consecutivas y no limita el tiempo durante el cual una transacción retiene un bloqueo ya adquirido.
- **Duración mientras se retiene el punto.** La acotan `statement_timeout` (cada sentencia, incluidas las esperas de bloqueo dentro de ella) e `idle_in_transaction_session_timeout` (el tiempo entre sentencias con la transacción abierta, por ejemplo un cliente detenido), ambos distintos de cero y fijados para la transacción que toma el punto (por ejemplo con `SET LOCAL`) o para el rol. Ninguno acota por sí solo una cadena de sentencias, pero la asignación y la creación de pedido ejecutan, desde que adquieren el punto hasta el commit, como máximo un número fijo N de sentencias que no depende de los datos, sin bucles ni reintentos dentro de la transacción: la retención total queda acotada por N × (`statement_timeout` + `idle_in_transaction_session_timeout`). Si la versión de PostgreSQL incluye `transaction_timeout` (PostgreSQL 17 o posterior), además se fija ese límite para la duración total de la transacción. Si es menor o igual que `statement_timeout` o que `idle_in_transaction_session_timeout`, PostgreSQL deja sin efecto el más largo de ellos (documentación de PostgreSQL 17) y la duración total queda acotada por `transaction_timeout`, sin depender de N. El proyecto declara PostgreSQL 16 (`postgres:16` en `docker-compose.yml`), que no lo incluye, por lo que este contrato no depende de él; la versión real se comprueba (`SHOW server_version`) y se registra en el README.
- **Alcance de la cota.** La cota protege la duración de la transacción y la retención de bloqueos en PostgreSQL, bajo las condiciones anteriores (N fijo y ambos límites distintos de cero, o `transaction_timeout`). No garantiza por sí sola la duración total de la petición HTTP de FastAPI ni que n8n reciba una respuesta antes de agotar su propio timeout: PostgreSQL puede terminar una sesión y liberar sus bloqueos mientras FastAPI todavía ejecuta código Python o espera otra operación, y puede confirmar una transacción cuya respuesta HTTP se pierda después. Por eso un timeout o un error de comunicación en n8n es un resultado incierto: no se interpreta como que la operación falló ni como que se ejecutó, WF1 no lo reintenta y el siguiente ciclo del Cron consulta de nuevo el estado real de los pendientes (sección 9).
- **Valores.** Este documento no fija valores numéricos: los elige el operador y se escriben en el README. Las pruebas de la sección 14 usan los mismos parámetros que la aplicación, con valores reducidos solo en la prueba. Se recomienda que la cota N × (`statement_timeout` + `idle_in_transaction_session_timeout`) sea menor que el timeout con que WF1 espera la respuesta de la asignación, porque así es menos probable que n8n abandone la espera antes de que la operación termine; es una recomendación de configuración, no una garantía («Alcance de la cota»).
- **Si se agota un límite.** Con `lock_timeout`, la operación no ha escrito nada (la espera ocurre antes de escribir). Con `statement_timeout` o `idle_in_transaction_session_timeout`, la transacción se revierte antes del commit. En ambos casos no se publica ningún evento (los eventos y el aviso a n8n se emiten después del commit), `POST /api/orders` no crea el pedido ni programa el aviso, y, si FastAPI llega a responder, la respuesta es 500, que n8n clasifica como fallo (sección 9). Un fallo durante el propio commit es un resultado incierto, como un error de comunicación: no se supone el estado. No se usa 503: está reservado a la identidad de servicio deshabilitada (sección 10.4). El punto se libera al terminar la transacción (commit, rollback o sesión terminada) y la publicación de eventos y el aviso a n8n ocurren después, sin prolongarlo.

**Por qué este mecanismo.** FIFO exige que comprobar «soy el siguiente» y asignar ocurran sin que nada pueda cambiar la cola entre ambos pasos, incluidas inserciones que todavía no existen como filas:
- Bloquear solo el Shipment solicitado (lo que hace hoy la asignación) no basta: otra transacción puede asignar o insertar otro Shipment sin tocar esa fila.
- Bloquear la fila del primer pendiente no basta: no cubre las inserciones concurrentes.
- `SKIP LOCKED` sobre la cola está prohibido: saltaría un Shipment anterior bloqueado y dejaría pasar a uno posterior.
- `SERIALIZABLE` exige reintentos por conflictos de serialización y cambia el aislamiento de todo el sistema; no se elige.
- `LOCK TABLE` sobre `shipments` bloquearía también escrituras ajenas a la cola (tránsito, entrega, riesgo).
- Una fila o tabla centinela con `SELECT … FOR UPDATE` equivale al bloqueo consultivo, pero exige esquema y migración sin aportar más garantía.
- El bloqueo consultivo de transacción funciona entre varias instancias de FastAPI (a diferencia de un candado en memoria), se libera siempre al terminar la transacción (a diferencia del bloqueo de sesión, que con un pool de conexiones podría filtrarse) y no requiere cambios de esquema.

**Orden de bloqueos.** Punto de serialización → Shipment → Order, Vehicle y Driver. Crear pedido y asignar toman el punto antes de cualquier bloqueo de fila. Las demás operaciones sobre un Shipment (cancelar, cambiar su estado, actualizar su riesgo) bloquean primero el Shipment y nunca esperan el punto. Por eso ninguna espera del punto puede cerrar un ciclo. Entre filas, todas las operaciones bloquean primero el Shipment, el Order solo se bloquea con su Shipment ya bloqueado y `assign` elige Vehicle y Driver con `SKIP LOCKED`, de modo que no espera por ellos. Mientras se espera la fila de un Shipment con el punto tomado (por ejemplo, una cancelación en curso del mismo Shipment), las demás creaciones y asignaciones esperan: la espera está acotada («Límites de espera y de duración»).

**Comprobación y asignación.** Dentro del punto de serialización y con el Shipment solicitado bloqueado, `POST /api/shipments/{id}/assign` comprueba en este orden: existencia, idempotencia, inconsistencia de datos (más abajo), posición en la cola y disponibilidad de recursos, y asigna en la misma transacción (resultados en la sección 7). La posición se comprueba comparando el Shipment con el primero de la cola de pendientes, leído con una consulta propia ejecutada después de adquirir el punto; la cola incluye todos los Shipments `pending`, también los que tienen una inconsistencia de datos. La garantía requiere que cada consulta que decide la operación se ejecute con una instantánea posterior a la obtención del punto de serialización: es el comportamiento del aislamiento READ COMMITTED, el valor por defecto de PostgreSQL, que el proyecto no cambia; modificarlo exige revisar este contrato.

**Recursos.** `SKIP LOCKED` solo puede usarse para elegir vehículo y conductor, nunca para elegir qué Shipment se asigna. Como las asignaciones pasan una a una por el punto de serialización, ya no se solapan entre sí: `SKIP LOCKED` sobre los recursos queda como protección frente a otras escrituras (cancelar, entregar, cambiar la disponibilidad de un vehículo).

**Shipment `pending` con datos de asignación.** `vehicle_id`, `driver_id` y `assigned_at` se fijan atómicamente junto con `status = assigned`, y `estimated_delivery` se fija en el momento de la asignación (`assigned_at` + 4 horas, «ETA operacional») y es nulo hasta entonces (tabla `shipments`), así que un Shipment `pending` con cualquiera de los cuatro no nulo (basta uno) es una inconsistencia de datos que ninguna operación de este documento produce. El criterio cubre los datos que escribe la asignación; `actual_delivery` y `delay_risk_score` los escriben transiciones posteriores (estado terminal e `in_transit`) y no forman parte de él. No es idempotencia: no hay una asignación completa que devolver y continuar la cola como si la hubiera. `POST /api/shipments/{id}/assign` sobre ese Shipment responde 500 (sección 7), antes de comprobar su posición: no modifica nada, no publica eventos, no responde `assignment_created` y FastAPI registra la inconsistencia en su log con el id del Shipment y los campos no nulos. El Shipment sigue `pending` y por eso permanece en la cola: los posteriores reciben 409 (FIFO no se relaja para saltarse una anomalía) y la cola queda detenida hasta que se corrijan los datos.

**Corrección de un Shipment inconsistente.** Este documento no define ninguna reparación automática y no la propone. Cancelar el pedido no es una reparación segura por sí sola: la cancelación libera los recursos que el Shipment referencia («Máquina de estados operacional») y el vehículo o el conductor referenciados podrían estar referenciados también por otro Shipment activo (`assigned` o `in_transit`), con lo que quedarían marcados como disponibles mientras ese Shipment los usa. Antes de cualquier corrección se verifican las referencias de `vehicle_id` y `driver_id` contra los demás Shipments, y el tratamiento se decide y se documenta aquí antes de aplicarse.

**Generación de `orders.created_at`.** Se fija dentro del punto de serialización, después de adquirirlo y antes del commit. Se toma del reloj de PostgreSQL en el momento de la sentencia (`clock_timestamp()`), no del inicio de la transacción (`now()` o `CURRENT_TIMESTAMP`, anterior a la espera del punto: una transacción que empezó antes pero obtiene el punto después recibiría una fecha menor que la de un pedido ya confirmado), y se expresa en UTC de forma explícita, sin depender de la zona horaria de la sesión. El valor es el mayor entre ese instante y el mayor `orders.created_at` existente más la unidad mínima que representa la columna (un microsegundo con la precisión por defecto de `timestamp`), de modo que es estrictamente mayor que cualquier valor anterior aunque el reloj retroceda. Así el orden por `created_at` coincide con el orden de confirmación de los pedidos. Un valor asignado antes de adquirir el punto de serialización (por ejemplo, el valor por defecto que el ORM calcula al hacer flush antes del commit) no es válido: dos pedidos podrían confirmarse en orden inverso a su `created_at`, y una asignación podría adelantar a un pedido que se confirma después con una fecha anterior. El cliente no puede enviar `created_at`. Los pedidos existentes conservan su `created_at` almacenado; no se reescribe ni se inventa ninguna fecha (sección 7, «Orden de `GET /api/shipments` — requisito de datos»). Un `created_at` futuro ya existente hace que los pedidos nuevos se encadenen detrás de él con fechas posteriores al instante real, y los pedidos creados con el mecanismo anterior pueden conservar inversiones de orden respecto de su confirmación: ninguno se corrige y la cola se ordena siempre por el valor almacenado.

**Consulta informativa.** Ordenar `GET /api/shipments` no garantiza FIFO por sí solo: es informativo. La comprobación que impone la garantía es la de `POST /api/shipments/{id}/assign` dentro del punto de serialización.

**Si el Shipment no es el siguiente.** `POST /api/shipments/{id}/assign` sobre un Shipment `pending` que no es el siguiente responde 409 (sección 7): no modifica Shipment, Order, Vehicle ni Driver, no publica eventos y no genera `assignment_created: true`.

**Limitaciones aceptadas del MVP.** (1) Crear pedido y asignar quedan serializados globalmente: su rendimiento está limitado por una sola cola de espera. (2) Un Shipment en la cabecera de la cola que falla de forma persistente (un 5xx, una inconsistencia de datos o la falta prolongada de recursos) detiene la asignación de todos los posteriores hasta que se corrija: FIFO estricto no los salta, y la corrección de una inconsistencia de datos es manual y no está definida («Corrección de un Shipment inconsistente»). (3) Mientras haya pendientes anteriores, el Shipment recién creado no se asigna desde el aviso (409) y espera al Cron (sección 9), sin SLA. (4) Las inversiones históricas de `created_at` y los valores futuros ya existentes no se corrigen.

**Entorno de pruebas.** SQLite no tiene el bloqueo consultivo ni el reloj de PostgreSQL: allí el bloqueo no se toma y solo se prueba la lógica de posición, de 409 y de inconsistencia. La garantía de concurrencia y la generación de `created_at` se validan únicamente contra PostgreSQL (sección 14); como fuera de PostgreSQL el bloqueo se omite, una prueba que lo elimine debe fallar contra PostgreSQL.

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
| POST | /api/orders | Crear pedido (crea también su Shipment asociado, misma transacción y dentro del punto de serialización de la cola, sección 6; después del commit se programa el aviso a n8n definido en la sección 9) | React |
| GET | /api/orders/{id} | Detalle de pedido | React |
| PATCH | /api/orders/{id}/status | Cancelación administrativa (ver "Máquina de estados operacional", sección 6) | React |
| GET | /api/shipments | Listar envíos (filtro opcional `?status=`), ordenados por antigüedad del pedido: `orders.created_at` ascendente y, como desempate, `shipments.id` ascendente (es el orden de la cola de pendientes de la sección 6; requisito de datos en «Orden de `GET /api/shipments` — requisito de datos», más abajo). Un usuario driver no puede listar envíos globales; la identidad de servicio de n8n solo puede consultar `status=pending` o `status=in_transit` (sección 10.2) | React, n8n |
| GET | /api/shipments/{id} | Detalle de envío; un usuario driver solo accede a sus propios envíos (sección 10.2) | React, Flutter |
| POST | /api/shipments/{id}/assign | Asigna vehículo y conductor disponibles (idempotente; FastAPI decide la selección, n8n no la duplica); solo asigna el siguiente de la cola de pendientes y, si el Shipment no lo es, responde 409 (sección 6); la respuesta incluye `assignment_created` (sección 9); la pueden ejecutar admin y la identidad de servicio de n8n, no un usuario driver (sección 10.2); respuestas y códigos en «`POST /api/shipments/{id}/assign` — autorización y respuestas», más abajo | n8n |
| PATCH | /api/shipments/{id}/status | Actualizar estado (ej. "entregado") | Flutter |
| PATCH | /api/shipments/{id}/risk | Persiste `delay_risk_score` calculado por n8n (sección 6 y 9) | n8n |
| GET | /api/vehicles | Listar vehículos | React |
| PATCH | /api/vehicles/{id}/status | Cambiar disponibilidad manualmente (ej. `maintenance`); solo admin (sección 10.2). La asignación y la liberación de recursos no pasan por aquí: son responsabilidad transaccional de FastAPI (sección 6, "Máquina de estados operacional") | React |
| GET | /api/drivers | Listar conductores | React |
| GET | /api/drivers/{id}/shipments | Ruta del día del conductor | Flutter |
| GET | /api/reports/daily | Métricas del día | React, WF3 (inactivo: la ruta debe implementarse y su autorización definirse; sección 9) |

El aviso de pedido creado a n8n no es un endpoint de FastAPI: es una llamada saliente de FastAPI hacia n8n, definida en la sección 9.

La columna «Usado por» indica el cliente previsto de cada ruta; quién puede ejecutarla lo define la sección 10.2.

Ningún chat/agente inventa un endpoint o campo que no esté en esta tabla. Si hace falta uno nuevo, se agrega aquí primero.

### Orden de `GET /api/shipments` — requisito de datos

El orden por antigüedad presupone que todos los pedidos tienen `orders.created_at`; cómo se genera ese valor y cómo se garantiza el FIFO en las asignaciones está en la sección 6 («Cola de pendientes y garantía FIFO»). Antes de implementarlo se cumplen estos pasos, en este orden:

1. **Verificación de datos.** En cada base de datos (desarrollo, pruebas y la del entorno de entrega) se cuentan los pedidos con `created_at` nulo: `SELECT COUNT(*) FROM orders WHERE created_at IS NULL;`. El resultado esperado es 0 y se registra en el README o en la descripción del cambio. Se registran además el mayor `created_at` existente, el tipo y la precisión reales de la columna y la zona horaria de la base de datos (`SHOW TimeZone`); que el mayor valor sea posterior al instante de la verificación no impide el orden, pero se reporta y no se corrige (sección 6, «Generación de `orders.created_at`»).
2. **Si el recuento es 0**, `orders.created_at` pasa a ser NOT NULL en la base de datos mediante una migración SQL que se detiene sin modificar nada si encuentra filas con valor nulo. La restricción protege la base de datos frente a cualquier escritura; no obliga al cliente a enviar `created_at`.
3. **Si el recuento no es 0**, no se implementa el orden ni se impone la restricción. No se inventan, estiman ni sustituyen fechas (ni la fecha actual, ni la de otra tabla, ni un valor por defecto) y los pedidos afectados no se corrigen automáticamente: se detiene el trabajo, se reportan los pedidos afectados y su tratamiento se decide y se documenta aquí antes de continuar.
4. **Después de la restricción**, un pedido sin `created_at` no puede existir, de modo que este contrato no depende de cómo cada motor de base de datos ordena los valores nulos.

### `POST /api/shipments/{id}/assign` — autorización y respuestas

Sin body: FastAPI selecciona el vehículo y el conductor disponibles (sección 6); el cliente, incluido n8n, no envía ni elige recursos.

Autorización (sección 10.2): admin y la identidad de servicio de n8n. Un usuario driver no puede realizar asignaciones administrativas y recibe 403. La combinación de credenciales y la precedencia de errores están en la sección 10.4.

**Orden de resolución.** Se aplica el primer caso que corresponda:

1. Autenticación y autorización: 401 o 403 (sección 10.4).
2. Shipment inexistente: 404.
3. Idempotencia: si el Shipment ya no está `pending`, 200 con `assignment_created: false`. Esta comprobación va antes que la de posición: un Shipment ya asignado, en tránsito, entregado o cancelado nunca recibe 409.
4. Inconsistencia de datos: si el Shipment está `pending` y tiene `vehicle_id`, `driver_id`, `assigned_at` o `estimated_delivery` no nulos (basta uno), 500 (sección 6, «Shipment `pending` con datos de asignación»). No es idempotencia y se comprueba antes que la posición.
5. Posición en la cola: si el Shipment está `pending`, sin datos de asignación, y no es el siguiente de la cola de pendientes (sección 6), 409.
6. Recursos: si es el siguiente y no hay vehículo disponible o no hay conductor disponible, 400. Un Shipment `pending` que no es el siguiente recibe 409 aunque tampoco haya recursos.
7. Asignación: 200 con `assignment_created: true`.

Los pasos 2 a 7 se ejecutan en una sola transacción, bajo el punto de serialización de la cola y con el Shipment bloqueado (sección 6).

Respuesta 200, con los campos `id`, `order_id`, `vehicle_id`, `driver_id`, `status` y `assignment_created`:

| Situación del Shipment | Resultado |
|---|---|
| `pending`, sin `vehicle_id` ni `driver_id`, es el siguiente de la cola y hay un vehículo y un conductor disponibles | 200 con `assignment_created: true`. Se asigna (sección 6) y FastAPI publica el evento `status_changed` después del commit |
| Ya no está `pending` (`assigned`, `in_transit`, `delivered` o `cancelled`) | 200 con `assignment_created: false`. No se modifica nada y no se publica ningún evento |

Por tanto, `assignment_created: false` nunca va acompañado de `status: pending`: un Shipment `pending` solo produce 200 con `assignment_created: true`, o 400, 409 o 500.

Otras respuestas:

| Código | Cuándo |
|---|---|
| 400 | El Shipment está `pending`, es el siguiente de la cola y no hay vehículo disponible o no hay conductor disponible. No se modifica nada: el Shipment sigue `pending`. Es el único 400 de esta ruta y n8n lo trata como falta de recursos, sin distinguir cuál falta |
| 401 | Autenticación ausente o inválida, o JWT y API key presentados a la vez (sección 10.4) |
| 403 | Identidad válida sin permiso para asignar (por ejemplo, un usuario driver) |
| 404 | Shipment inexistente |
| 409 | El Shipment está `pending`, sin datos de asignación, y no es el siguiente de la cola de pendientes (sección 6). No se modifica Shipment, Order, vehículo ni conductor, no se publica ningún evento y no hay `assignment_created: true` |
| 500 | Falla interna que no responde `assignment_created`: (a) el Shipment está `pending` y tiene `vehicle_id`, `driver_id`, `assigned_at` o `estimated_delivery` no nulos (inconsistencia de datos): no modifica nada ni publica eventos; (b) se agotó un límite de espera o de duración de la transacción (sección 6, «Límites de espera y de duración»): la transacción se revierte antes del commit y no se publica ningún evento; si el fallo ocurre durante el commit, el resultado es incierto, como un error de comunicación. n8n lo trata como fallo y no supone el estado del Shipment (sección 9). No es 503, reservado a la identidad de servicio deshabilitada (sección 10.4) |
| 503 | Se presenta solo `X-N8N-API-Key` y el servidor no tiene `N8N_API_KEY` configurada (sección 10.4) |

La respuesta incluye además `message`, un texto informativo para personas. No forma parte del contrato de decisión: su texto puede cambiar y ningún cliente, incluido n8n, decide a partir de él. n8n decide únicamente con el código HTTP y con `assignment_created`. Lo mismo vale para el texto `detail` de las respuestas de error, incluido el del 409.

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
| 401 | Autenticación ausente o inválida, o JWT y API key presentados a la vez (sección 10.4) |
| 403 | Identidad humana válida: la ruta está reservada a la identidad de servicio de n8n (sección 10.4) |
| 404 | Shipment inexistente |
| 422 | Body inválido o `delay_risk_score` fuera del rango 0–1 |
| 503 | Se presenta solo `X-N8N-API-Key` y el servidor no tiene `N8N_API_KEY` configurada (sección 10.4) |

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
`Webhook (respuesta mediante Respond to Webhook) → validar credencial y payload → Respond to Webhook: 400 si el payload es inválido, 200 si es válido → solo tras el 200: POST /api/shipments/{id}/assign → registrar resultado`
`Cron cada 5 min → GET /api/shipments?status=pending → por cada Shipment: POST /api/shipments/{id}/assign → registrar resultado`
El primer disparador es el aviso de pedido creado que FastAPI envía a n8n (subsección «Aviso de pedido creado (FastAPI → n8n)», más abajo); el segundo es el Cron de la subsección «Recuperación de asignaciones pendientes (Cron de WF1)». Ambos usan la misma asignación y el mismo registro de resultado. Con la garantía FIFO de la sección 6, el Webhook solo consigue asignar de inmediato cuando el Shipment recién creado es el siguiente de la cola; si hay pendientes anteriores recibe 409 y la asignación corresponde al Cron.

**Registrar resultado (MVP).** Es lo que en este documento se llama «notificar»: no es una notificación externa. WF1 registra en su propia ejecución de n8n el resultado de cada llamada de asignación: el código HTTP y, en una respuesta 200, `assignment_created`, `id`, `vehicle_id` y `driver_id`. Solo un 200 válido con `assignment_created: true` y los datos de asignación esperados se registra como asignación nueva; los demás resultados (sin asignación nueva, falta de recursos, rechazo por la cola FIFO, anomalía, fallo, resultado incierto, error de contrato y resultado inesperado) se registran según la tabla de la subsección «Recuperación de asignaciones pendientes (Cron de WF1)». El spec no define canal, destinatario ni plantilla de notificación externa, y el Order no guarda datos de contacto del cliente (sección 6); un canal externo es una decisión futura que se documenta aquí antes de implementarse. El registro de n8n es un registro operativo, no una auditoría persistente (subsección «Registro de ejecuciones de n8n y conservación») ni la fuente de verdad: lo es el Shipment en FastAPI. FastAPI sigue siendo responsable de publicar `status_changed` (sección 8) después del commit de la asignación; n8n nunca publica eventos y no existe un endpoint que se lo permita.

**WF2 — Riesgo de retraso**
`Cron cada 15 min → GET /api/shipments?status=in_transit → n8n calcula delay_risk_score → PATCH /api/shipments/{id}/risk → FastAPI persiste, confirma (commit) y publica el evento risk_alert si delay_risk_score > 0.7 (sección 8) — n8n nunca publica el evento directamente`

**WF3 — Reporte diario** *(inactivo y fuera del MVP)*
`Cron 18:00 → GET /api/reports/daily → armar resumen → enviar por email`
WF3 permanece inactivo y fuera del MVP hasta que se cumplan las tres condiciones siguientes: (1) `GET /api/reports/daily` está implementado en FastAPI; (2) se define su autenticación y autorización; y (3) se documenta qué identidad puede utilizarlo (la sección 10.2 no autoriza hoy a la identidad de servicio de n8n a usar esta ruta). Hasta entonces WF3 no se implementa, importa, activa ni ejecuta como workflow operativo, no se exporta («Exportaciones de workflows y configuración inicial de n8n») y no forma parte de la Definition of Done del MVP.

### Aviso de pedido creado (FastAPI → n8n)

Es una llamada HTTP saliente de FastAPI hacia n8n, no un endpoint de la sección 7. n8n la recibe en el nodo Webhook de WF1 y sigue sin escribir en PostgreSQL (sección 4).

**Cuándo.** `POST /api/orders` crea el Order y su Shipment en una misma transacción (sección 7). Solo después de confirmar el commit, FastAPI programa el envío del aviso con `BackgroundTasks`; nunca antes (misma regla que los eventos de la sección 8). La respuesta `201` no depende de la entrega del aviso: un fallo de comunicación no revierte la transacción ni modifica la respuesta.

**Destino.** `POST {N8N_WEBHOOK_URL}/order-created`. `N8N_WEBHOOK_URL` (variable de entorno existente) es la URL base de los webhooks de n8n. Si `N8N_WEBHOOK_URL` o `N8N_WEBHOOK_SECRET` (ver «Autenticación») están ausentes, vacías o contienen únicamente espacios en blanco, no se realiza la petición HTTP y se registra un warning que indica la variable faltante, sin revelar el valor del secreto.

**Cuerpo** (JSON, `snake_case`):

```json
{
  "order_id": "UUID",
  "shipment_id": "UUID"
}
```

Contiene exclusivamente esos dos campos: no hay campo `event` ni otros. `shipment_id` es el Shipment creado junto con el Order; WF1 lo usa como `{id}` en `POST /api/shipments/{id}/assign`. Si WF1 necesita más datos, los consulta a la API.

**Autenticación.** La llamada incluye la cabecera `X-Webhook-Secret` con el valor de la variable de entorno `N8N_WEBHOOK_SECRET`. El nodo Webhook de n8n la valida con una credencial Header Auth. El mismo secreto debe estar configurado en ambos lados (FastAPI y n8n). Esta autenticación protege solo la recepción del aviso; la autenticación de n8n hacia FastAPI es distinta: n8n envía `X-N8N-API-Key` con la credencial de servicio de la sección 10.1, y todas las llamadas de WF1 y WF2 a FastAPI la incluyen. Los dos secretos son independientes (sección 10.3).

**Entrega (MVP).** Best-effort: FastAPI realiza un único intento por cada creación de pedido, sin reintentos automáticos, y no existe Transactional Outbox. El spec no garantiza la entrega del aviso. La implementación de este envío (D9-B) deberá:

- utilizar un timeout HTTP finito (este documento no fija su valor);
- considerar respuesta exitosa cualquier respuesta 2xx de n8n;
- registrar en el log las respuestas no 2xx y los errores de comunicación;
- no alterar el `201` de `POST /api/orders` en ningún caso.

**Respuesta del Webhook.** El nodo Webhook de WF1 responde mediante el nodo Respond to Webhook, de modo que la respuesta se envía después de validar y la asignación continúa después de responder. Antes de responder, WF1 valida la recepción:

1. La credencial Header Auth («Autenticación»). Una credencial ausente o inválida la rechaza n8n con una respuesta no 2xx.
2. El payload: debe ser un objeto JSON con exactamente los campos `order_id` y `shipment_id`, ambos con formato UUID válido. Cualquier campo adicional invalida el payload.

Resultado de la validación del payload:

| Payload | Respuesta de WF1 | Continuación |
|---|---|---|
| Inválido: falta `order_id` o `shipment_id`, el cuerpo está vacío o no es JSON, el objeto contiene campos adicionales, o alguno de los dos valores no es un UUID válido | 400 (Respond to Webhook) | WF1 termina y no llama a FastAPI |
| Válido | 200 (Respond to Webhook) | La ejecución continúa con `POST /api/shipments/{id}/assign` después de responder; WF1 no espera a que termine la asignación para responder |

FastAPI registra las respuestas no 2xx en su log («Entrega (MVP)»); ante un 400, el Shipment, si existe, sigue `pending`. Si la llamada de asignación posterior al 200 no devuelve un 200 válido (por ejemplo 409, 404, 5xx, timeout o error de comunicación), se aplica la clasificación de «Recuperación de asignaciones pendientes (Cron de WF1)»: WF1 no la reintenta ni asume el estado del Shipment, y la recuperación corresponde al Cron, que solo consulta los Shipments que sigan `pending`. Como WF1 rechaza los campos adicionales, cualquier cambio del payload del aviso se documenta primero en «Aviso de pedido creado (FastAPI → n8n)» y se aplica a FastAPI y a WF1 en el mismo cambio.

**Verificación pendiente en n8n.** El comportamiento anterior es el contrato objetivo, no un hecho comprobado: su validación extremo a extremo está pendiente en la versión de n8n instalada. Antes de dar WF1 por cumplido se comprueba en esa versión, y se registran en el README de `automation/` la versión y el resultado, que:

- el nodo Webhook está configurado para responder mediante Respond to Webhook;
- una credencial inválida produce una respuesta no 2xx y no ejecuta el workflow;
- cada payload inválido de la tabla produce 400 y no llama a FastAPI, y se identifica quién responde ante un cuerpo que no es JSON (n8n antes de ejecutar el workflow o el nodo Respond to Webhook);
- un payload válido produce 200 y la asignación continúa después de responder, también cuando la asignación tarda más que el timeout del aviso.

**Recuperación.** Si el aviso no llega, el Shipment permanece en `pending`. WF1 recupera esas asignaciones con el Cron descrito en «Recuperación de asignaciones pendientes (Cron de WF1)», más abajo. Recuperar asignaciones no es lo mismo que garantizar notificaciones.

**Notificaciones duplicadas.** La idempotencia de `POST /api/shipments/{id}/assign` impide asignar dos veces el mismo Shipment, pero por sí sola no evita notificaciones duplicadas. Para distinguir una asignación nueva de una repetida, la respuesta de `POST /api/shipments/{id}/assign` incluye el campo `assignment_created`: `true` cuando esa petición crea una asignación nueva y `false` cuando esa petición no crea una asignación nueva. WF1 registrará una asignación nueva únicamente cuando sea `true`. Ese registro es, como máximo, una vez: si la ejecución que recibe `assignment_created: true` falla antes de registrarlo, o si se pierde su respuesta y la petición se repite (la repetición recibe `false`), el registro no se recupera, porque el Shipment ya no está `pending` y el Cron no lo vuelve a ver. El spec no garantiza la entrega de notificaciones ni la completitud del registro de n8n: el estado de la asignación está en el Shipment y su cambio se publica como `status_changed` (sección 8).

### Recuperación de asignaciones pendientes (Cron de WF1)

Un Shipment sigue en `pending` cuando el aviso no llega, cuando WF1 rechaza el aviso por un payload inválido, cuando `POST /api/shipments/{id}/assign` responde 400 por falta de recursos o cuando responde 409 porque el Shipment no es el siguiente de la cola. Si la llamada de asignación termina en 404, 5xx, timeout o error de comunicación, el spec no da por supuesto que el Shipment siga `pending` (clasificación más abajo). El Cron de WF1 reintenta las asignaciones pendientes y es el único mecanismo de recuperación del MVP; el aviso de pedido creado sigue siendo best-effort.

- **Frecuencia.** Cada 5 minutos. Es la configuración inicial del MVP, no un SLA: no promete un tiempo máximo entre la creación del pedido y su asignación.
- **Consulta.** `GET /api/shipments?status=pending` con `X-N8N-API-Key`. Es la única consulta del Cron: no lista vehículos ni conductores y no elige recursos (FastAPI decide, sección 7). La respuesta no tiene paginación ni límite: el Cron procesa la lista completa y solo usa `id`. Si la consulta falla (respuesta distinta de 200, timeout o error de comunicación) o el 200 no es una lista JSON de objetos con `id` (UUID válido), la pasada termina (la estructura inválida se registra como error de contrato) y se reintenta en la siguiente ejecución. El spec no define más campos de cada elemento de la lista y el Cron no depende de ellos, incluido `order_id`: si el Cron necesitara contrastarlo, la consulta tendría que garantizarlo y se documentaría antes en la sección 7.
- **Orden.** FastAPI devuelve los pendientes por antigüedad del pedido: `orders.created_at` ascendente y, como desempate, `shipments.id` ascendente (sección 7, sujeto a su requisito de datos). FastAPI impone ese orden en cada asignación (sección 6): el Cron los procesa en ese orden y de forma secuencial, no lo reimplementa y no decide cuál es el siguiente.
- **Asignación.** Por cada Shipment, `POST /api/shipments/{id}/assign` con `X-N8N-API-Key`, y registra el resultado. La lógica del Cron decide únicamente con el código HTTP y con `assignment_created`; nunca con `message`. Con `assignment_created: false` no hace nada más: otro proceso ya lo asignó o el Shipment dejó de estar `pending`.
- **Resultado de cada llamada de asignación.** Cada llamada a `POST /api/shipments/{id}/assign` se clasifica así, y el resultado se registra en la ejecución de n8n (registro operativo, no una notificación externa ni una auditoría persistente):

  | Resultado de la llamada | Registro | Cron |
  |---|---|---|
  | 200 válido con `assignment_created: true` y los datos de asignación esperados | Asignación nueva | Continúa con el siguiente Shipment |
  | 200 válido con `assignment_created: false` | Sin asignación nueva | Continúa con el siguiente Shipment |
  | 200 con estructura inválida, campos obligatorios ausentes o de tipo incorrecto, `id` u `order_id` que no coinciden (según «Respuesta 200 válida»), `assignment_created: true` sin los datos de asignación esperados o `assignment_created: false` con `status: pending` | Error de contrato | Detiene la pasada |
  | 400 | Falta de recursos | Detiene la pasada, porque los Shipments siguientes tampoco podrían asignarse |
  | 401, 403 o 503 | Error de configuración o de autorización (sección 10.4) | Detiene la pasada |
  | 404 | Resultado inexistente (anomalía): el Shipment no existe y no hay asignación posible (la sección 7 no tiene un endpoint para eliminar Shipments) | Continúa con el siguiente Shipment |
  | 409 | Rechazo por la cola FIFO | Detiene la pasada |
  | 5xx distinto de 503 | Fallo: FastAPI respondió con un error y la asignación no se confirma; el spec no define el estado final del Shipment | Continúa con el siguiente Shipment |
  | Timeout o error de comunicación | Resultado incierto: no se sabe si FastAPI llegó a procesar la petición ni si PostgreSQL llegó a confirmarla; pudo asignar o no, aunque la respuesta no llegue | Continúa con el siguiente Shipment |
  | Cualquier otro código HTTP | Resultado inesperado | Detiene la pasada |

  **Respuesta 200 válida.** Es un objeto JSON con `id` y `order_id` (UUID válidos), `vehicle_id` y `driver_id` (UUID válido o `null`), `status` (uno de `pending`, `assigned`, `in_transit`, `delivered`, `cancelled`) y `assignment_created` (booleano), y cumple estas condiciones. (a) `id` es igual al `shipment_id` solicitado. (b) `order_id` solo se contrasta en el flujo que lo conoce: el Webhook recibe `order_id` y `shipment_id` en el aviso y exige que `order_id` sea igual al de la respuesta; el Cron solo usa el `id` de cada elemento de la lista («Consulta») y no conoce `order_id`, así que exige que sea un UUID válido pero no lo contrasta. (c) Los datos de asignación esperados para una asignación nueva son `assignment_created: true`, `status: assigned` y `vehicle_id` y `driver_id` no nulos. (d) `assignment_created: false` exige un `status` distinto de `pending`: un Shipment `pending` nunca produce `false` (sección 7), así que esa combinación es un error de contrato y no se interpreta como idempotencia. `message` no se valida ni se usa. La única condición para registrar una asignación nueva es un 200 válido con `assignment_created: true` y esos datos; ningún otro resultado, código ni cuerpo se interpreta como éxito.

  **409.** El Cron registra el resultado, detiene la pasada, no continúa con la lista anterior y no reintenta de inmediato: la cola puede haber cambiado, y la siguiente ejecución programada la consulta de nuevo con `GET /api/shipments?status=pending`.

  **Resultado inesperado.** Un código no contemplado (por ejemplo 201, 302, 405, 422 o 429) se registra como inesperado, no se interpreta como éxito, detiene la pasada y no se reintenta de inmediato.

  **Fallo, resultado incierto y 404.** En ningún caso se asume que el Shipment siga `pending` ni que haya quedado asignado. Que una respuesta no llegue no significa que la operación no se ejecutó: PostgreSQL pudo confirmar la transacción y perderse después la respuesta HTTP, o FastAPI pudo seguir procesando después de que n8n abandonara la espera; la cota de duración de la sección 6 protege la transacción y los bloqueos, no el tiempo de respuesta. La reconciliación es la siguiente pasada del Cron, y WF1 no reintenta de inmediato. Continuar con el siguiente Shipment no puede romper el FIFO, porque FastAPI lo impone en cada asignación: si el Shipment que falló sigue `pending`, la llamada del siguiente recibe 409 y la pasada se detiene; si ya fue asignado, el siguiente pasa a ser el primero y puede asignarse. La siguiente pasada consulta `GET /api/shipments?status=pending` y reintenta únicamente los Shipments que sigan `pending`: uno que ya no lo está no se reintenta, y una asignación completada durante un fallo o un resultado incierto no se registra como asignación nueva (el registro es, como máximo, una vez). Un 500 por inconsistencia de datos o por agotarse un límite de espera o de duración (sección 7) se registra como fallo, como cualquier otro 5xx: n8n no supone el estado del Shipment y, si este sigue `pending`, los posteriores reciben 409. Un Shipment en la cabecera de la cola que falla de forma persistente, o que tiene una inconsistencia de datos, detiene la asignación de todos los posteriores y n8n no lo resuelve: el fallo y el 409 se repiten en cada pasada hasta que se corrija la causa (limitación aceptada, sección 6).

  **Webhook.** Conserva el `order_id` y el `shipment_id` del aviso (validados antes de responder 200) y los usa para validar la respuesta de asignación. Hay un único intento por aviso. Con cualquiera de estos resultados, incluido el 409, WF1 registra el resultado, no registra asignación nueva salvo en el primer caso de la tabla, no reintenta (tampoco de inmediato) y finaliza el intento; la recuperación corresponde al Cron.
- **Concurrencia.** El Webhook y el Cron, o dos ejecuciones del Cron, pueden coincidir sobre el mismo Shipment. FastAPI serializa cada asignación con el punto de serialización de la cola y el bloqueo del Shipment (sección 6), así que solo una petición recibe `assignment_created: true`. n8n no añade bloqueos ni coordinación propios.
- **Reintentos.** WF1 no reintenta automáticamente la llamada de asignación (tampoco tras un 409 o un resultado inesperado): el reintento es la siguiente pasada del Cron, que no guarda una lista de fallos y consulta únicamente los Shipments que sigan `pending`.

### Prototipo parcial de WF2 existente en la instancia

El workflow que existe hoy en la instancia de n8n es un prototipo parcial. No es el WF2 de esta sección y no se declara, exporta ni versiona como WF2. Se mantiene separado del WF2 final hasta que se audite.

**Auditoría.** Antes de decidir si el prototipo se completa o se reemplaza, se audita contra este documento. El resultado, con el estado de cada criterio (cumple, cumple en parte o no cumple) y las diferencias encontradas, se registra en el README de `automation/`. Criterios:

| Criterio | Fuente |
|---|---|
| Disparo con Cron cada 15 minutos | Sección 9 (WF2) |
| Consulta `GET /api/shipments?status=in_transit` con `X-N8N-API-Key` | Secciones 9 y 10.2 |
| Calcula `delay_risk_score` con la fórmula del MVP | Sección 6 |
| Persiste con `PATCH /api/shipments/{id}/risk` y un body válido | Sección 7 |
| No escribe en PostgreSQL ni publica eventos: `risk_alert` lo publica FastAPI | Secciones 4, 8 y 9 |
| Usa únicamente las rutas autorizadas a la identidad de servicio | Sección 10.2 |
| Las credenciales están en el sistema de credenciales de n8n y no en nodos ni parámetros | Sección 10.3 |

**Resultado.** Tras la auditoría, el prototipo se completa o se reemplaza. La exportación de WF2 se versiona solo cuando el workflow cumple el contrato completo de esta sección y supera la comprobación de credenciales de «Exportaciones de workflows y configuración inicial de n8n». Mientras tanto, el prototipo no cuenta como WF2 en la Definition of Done. Si se conserva una copia del prototipo para la auditoría, se identifica expresamente como prototipo, no ocupa el lugar de la exportación de WF2 y cumple las mismas reglas sobre credenciales.

### Exportaciones de workflows y configuración inicial de n8n

Los workflows finales se versionan como exportaciones JSON de n8n en el directorio `automation/` del repositorio, una por workflow (WF1 y WF2). El prototipo parcial de WF2 no se exporta como WF2 («Prototipo parcial de WF2 existente en la instancia») y WF3 no se exporta ni se importa mientras permanezca inactivo («WF3 — Reporte diario»). La exportación es la referencia versionada de cada workflow: todo cambio hecho en n8n se vuelve a exportar y se versiona.

Las exportaciones no contienen secretos ni valores de credenciales. Las credenciales se almacenan en el sistema de credenciales de n8n (sección 10.3) y las exportaciones solo las referencian. Antes de versionar una exportación se comprueba que ningún nodo, cabecera ni parámetro contiene el valor de `N8N_WEBHOOK_SECRET` ni el de `N8N_API_KEY`.

La configuración inicial es manual:

1. Definir `N8N_WEBHOOK_SECRET` y `N8N_API_KEY` en `.env`, con valores distintos entre sí (sección 10.3). Sin `N8N_WEBHOOK_SECRET`, FastAPI no envía el aviso.
2. Definir `N8N_WEBHOOK_URL` según dónde corra FastAPI (tabla siguiente).
3. Crear en n8n una credencial Header Auth para el nodo Webhook de WF1, con la cabecera `X-Webhook-Secret` y el valor de `N8N_WEBHOOK_SECRET`.
4. Crear en n8n una credencial Header Auth para las llamadas a FastAPI, con la cabecera `X-N8N-API-Key` y el valor de `N8N_API_KEY`.
5. Importar las exportaciones finales de WF1 y WF2 y comprobar que cada nodo usa la credencial que le corresponde.
6. Comprobar que la URL base de FastAPI que usan los workflows es la de la sección 11.
7. Configurar y verificar la conservación de ejecuciones («Registro de ejecuciones de n8n y conservación»).
8. Activar WF1 y WF2.
9. Comprobar el Webhook de WF1 extremo a extremo («Verificación pendiente en n8n») y registrar en el README la versión de n8n instalada y el resultado.

| Dónde corre FastAPI | `N8N_WEBHOOK_URL` |
|---|---|
| Dentro de `docker compose` | `http://n8n:5678/webhook` |
| Directamente en el host | `http://localhost:5678/webhook` |

Dentro de `docker compose`, el contenedor del backend debe recibir `N8N_WEBHOOK_URL=http://n8n:5678/webhook` sin depender del valor del `.env` pensado para ejecutar FastAPI en el host: `localhost` dentro del contenedor apunta al propio backend y no alcanza a n8n (sección 11). El mecanismo (por ejemplo, la clave `environment` de `docker-compose.yml`) y el resto de este procedimiento se documentan en el README. Ni este documento ni el repositorio contienen ni generan valores de credenciales.

### Registro de ejecuciones de n8n y conservación

El registro de ejecuciones de n8n es un registro operativo: sirve para diagnosticar y revisar lo que hicieron WF1 y WF2, pero no es una auditoría persistente. n8n conserva las ejecuciones según su configuración y puede eliminarlas por antigüedad o por cantidad, y su contenido no sustituye al estado persistente: este vive en el Shipment en PostgreSQL (`assigned_at` indica cuándo se asignó, no quién ni con qué resultado). El MVP no tiene una auditoría persistente de asignaciones; si se necesita, se define aquí antes de implementarse y no se resuelve ampliando la retención de n8n.

**Conservación de ejecuciones (requisito operativo).** La instancia de n8n se configura de forma explícita para:

- guardar los datos de las ejecuciones de WF1 y WF2, tanto las correctas como las fallidas;
- conservarlas durante un período y hasta una cantidad máxima definidos por el operador y escritos en el README (este documento no fija los valores);
- no depender de los valores por defecto de n8n.

**Verificación.** Al configurar la instancia, y cada vez que cambie su configuración, se comprueba en la propia instancia que: una ejecución de WF1 muestra los datos de entrada y de salida de cada nodo; las ejecuciones fallidas se conservan; y la conservación configurada coincide con la escrita en el README. Si la conservación configurada es menor que la necesaria para la revisión operativa, el requisito no se da por cumplido.

---

## 10. Seguridad (nivel MVP, pero real)

### 10.1 Autenticación
- Los usuarios humanos se autentican mediante JWT firmado con HS256 y expiración corta.
- Las contraseñas se almacenan mediante bcrypt, nunca en texto plano.
- El refresh token queda pendiente de implementación; no se considera una funcionalidad ya disponible.
- n8n se autentica ante FastAPI mediante una API key independiente, enviada en la cabecera `X-N8N-API-Key`.
- La API key se configura mediante `N8N_API_KEY` en `.env`. Su valor nunca se escribe en este documento ni en archivos versionados.
- La identidad de servicio de n8n es independiente de los usuarios humanos. No se utilizará un usuario ficticio ni se aceptará la API key como si fuera un JWT.

### 10.2 Autorización por identidad y operación

**Admin**
- Puede consultar pedidos, envíos, conductores y vehículos.
- Puede crear y cancelar pedidos.
- Puede consultar detalles, asignar envíos y actualizar los estados de los envíos.
- Puede modificar el estado de los vehículos.
- No puede actualizar directamente el riesgo de retraso mediante el endpoint reservado a n8n.

**Driver**
- Solo puede consultar los envíos que le pertenecen.
- Solo puede consultar el detalle de sus propios envíos. El detalle (`GET /api/shipments/{id}`) de un envío ajeno o inexistente responde 403: la propiedad se comprueba antes de la existencia y el 404 solo lo ve un admin, igual que en la ruta del conductor (`GET /api/drivers/{id}/shipments`).
- Puede actualizar el estado de sus propios envíos, respetando las transiciones válidas del ciclo de vida.
- No puede consultar pedidos, consultar envíos globales (`GET /api/shipments`, con o sin `status`, responde 403), asignar envíos (`POST /api/shipments/{id}/assign` responde 403), modificar riesgos ni administrar conductores o vehículos.

**n8n (identidad de servicio)**

La identidad de servicio puede usar exclusivamente estas cuatro operaciones y no amplía permisos sobre ninguna otra ruta:

| Operación | Permiso | Usada por |
|---|---|---|
| `GET /api/shipments?status=pending` | Sí | WF1 (Cron) |
| `GET /api/shipments?status=in_transit` | Sí | WF2 |
| `POST /api/shipments/{id}/assign` | Sí | WF1 |
| `PATCH /api/shipments/{id}/risk` | Sí (reservada a n8n) | WF2 |

- `GET /api/shipments` con la identidad de servicio, sin `status` o con `status=assigned`, `status=delivered` o `status=cancelled`, responde 403. El resultado con un `status` no válido (403 o 422) queda fuera de este contrato.
- En cualquier otra ruta la credencial de servicio no concede acceso: se ignora y la petición se trata como si no la incluyera (sección 10.4).
- No puede cancelar pedidos, modificar estados de envíos, consultar pedidos, conductores ni vehículos, administrar usuarios, conductores o vehículos ni acceder a otras operaciones.

### 10.3 Protección de credenciales y comunicaciones
- Las variables sensibles se almacenan en `.env`, nunca se versionan. `.env.example` sí se incluye en el repositorio, sin secretos reales.
- `N8N_WEBHOOK_SECRET` protege la comunicación FastAPI → n8n mediante `X-Webhook-Secret` (sección 9).
- `N8N_API_KEY` protege la comunicación n8n → FastAPI mediante `X-N8N-API-Key`.
- Ambos secretos son independientes y no deben intercambiarse.
- Las credenciales de n8n se almacenan en su sistema de credenciales, no directamente en el código de los workflows ni en sus exportaciones versionadas (sección 9).
- La API key de servicio debe poder rotarse sin modificar la lógica de negocio.
- Las comparaciones de secretos deben realizarse de forma segura.

### 10.4 Reglas de autorización
- Cada endpoint comprueba explícitamente qué identidades pueden utilizarlo.
- La autenticación y la autorización son responsabilidades separadas.
- Una credencial ausente o inválida produce HTTP 401.
- Una identidad válida sin permiso para la operación produce HTTP 403.
- Las consultas y modificaciones de drivers deben comprobar la propiedad del recurso.
- Los endpoints de n8n solo aceptan la identidad de servicio en las operaciones expresamente autorizadas.
- La autenticación humana no debe otorgar automáticamente permisos de servicio, ni viceversa.

**Doble autenticación y precedencia de errores**

Hay tres clases de ruta: *humanas* (todas salvo las cuatro operaciones de servicio), *dobles* (`POST /api/shipments/{id}/assign` y `GET /api/shipments`: admin o identidad de servicio) y *de servicio* (`PATCH /api/shipments/{id}/risk`: solo la identidad de servicio). Reglas:

- Una petición se evalúa con una sola identidad. En las rutas dobles y de servicio, recibir a la vez la cabecera `Authorization` y la cabecera `X-N8N-API-Key` es una petición ambigua: se rechaza con 401 sin evaluar ninguna de las dos.
- En las rutas humanas la API key se ignora siempre: no se valida y no cambia el resultado.
- Sin ninguna credencial la respuesta es 401, también cuando el servidor no tiene `N8N_API_KEY` configurada: no se revela la configuración a quien no presenta una clave.
- Si en una ruta doble o de servicio llega solo `X-N8N-API-Key` y el servidor no tiene `N8N_API_KEY` configurada (vacía o solo espacios), la identidad de servicio está deshabilitada y la respuesta es 503 (falla cerrada). La falta de configuración no afecta a los usuarios humanos.
- Un JWT válido en la ruta de servicio es una identidad humana sin permiso: 403.

| Petición | Ruta humana | Ruta doble | Ruta de servicio |
|---|---|---|---|
| Sin credenciales | 401 | 401 | 401 |
| Solo JWT válido con permiso | continúa | continúa | — (ningún rol tiene permiso) |
| Solo JWT válido sin permiso (rol o propiedad) | 403 | 403 | 403 |
| Solo JWT inválido o expirado | 401 | 401 | 401 |
| Solo API key válida, operación permitida al servicio | 401 (API key ignorada) | continúa | continúa |
| Solo API key válida, operación no permitida al servicio | 401 (API key ignorada) | 403 | — |
| Solo API key inválida | 401 (API key ignorada) | 401 | 401 |
| Solo API key y servidor sin `N8N_API_KEY` configurada | 401 (API key ignorada) | 503 | 503 |
| JWT y API key a la vez | se evalúa solo el JWT: continúa, 401 o 403 | 401 (ambigua) | 401 (ambigua) |

Orden de precedencia (se aplica el primer caso que corresponda):

1. Credenciales ambiguas (rutas dobles y de servicio): 401.
2. Identidad de servicio deshabilitada (solo API key, sin `N8N_API_KEY` configurada): 503.
3. Credencial ausente o inválida: 401.
4. Identidad válida sin permiso (rol, propiedad del recurso u operación no permitida al servicio): 403.
5. Recurso inexistente: 404. Para un driver, la propiedad se comprueba antes de la existencia (403 exista o no el recurso).
6. Reglas de negocio de la operación: 400 o 409.

El orden de 422 (formato inválido de ruta, query o cuerpo) respecto de 401 y 403 no forma parte de este contrato: FastAPI puede rechazar un cuerpo JSON malformado antes de ejecutar la autenticación. Las pruebas de aceptación no deben depender de ese orden.

### 10.5 CORS y configuración
- CORS se configura explícitamente para los orígenes conocidos; nunca se utiliza `*` en producción.
- Los secretos reales no se almacenan en el repositorio, logs ni respuestas HTTP.

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

Objetivo: `docker compose up --build` levanta los servicios de la lista. No equivale a una automatización completa: la configuración inicial de n8n (credenciales, importación y activación de WF1 y WF2; sección 9) es manual y se documenta en el README.

Dentro de `docker compose`, el backend alcanza a n8n por el nombre del servicio: `N8N_WEBHOOK_URL=http://n8n:5678/webhook`. `localhost` dentro del contenedor del backend apunta al propio backend, no a n8n. `http://localhost:5678/webhook` solo es válido cuando el backend se ejecuta directamente en el host, donde n8n publica el puerto 5678.

En sentido inverso, dentro de `docker compose` n8n alcanza a FastAPI por el nombre del servicio: `http://backend:8000`. `localhost` dentro del contenedor de n8n apunta a n8n, no a FastAPI.

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
| 5 | Tests, README, demo de 3 minutos; WF3 solo si antes se cumplen las condiciones de la sección 9 y alcanza el tiempo |

La duración de cada sprint depende de las horas por semana disponibles — no hay una fecha fija todavía.

---

## 14. Definition of Done
- Cada endpoint de la sección 7 tiene al menos un test.
- El aviso de pedido creado (sección 9) debe tener pruebas de: su payload; la cabecera `X-Webhook-Secret`; que se ejecuta después del commit; la ausencia de `N8N_WEBHOOK_URL` o de `N8N_WEBHOOK_SECRET` (no se intenta enviar), y que un valor compuesto únicamente por espacios en blanco en cualquiera de las dos tampoco provoca el envío; una respuesta HTTP no 2xx; y un timeout o error de comunicación. En los casos de fallo, el `201` de `POST /api/orders` no se ve afectado.
- Las rutas con identidad de servicio (`GET /api/shipments`, `POST /api/shipments/{id}/assign` y `PATCH /api/shipments/{id}/risk`) tienen una prueba por cada fila de la matriz de la sección 10.4 que les corresponde, incluidos credencial ausente, inválida, ambigua (JWT y API key a la vez) y `N8N_API_KEY` sin configurar (503). Una ruta humana representativa prueba que la API key se ignora, con y sin JWT. `GET /api/shipments` con la identidad de servicio, sin `status` o con `assigned`, `delivered` o `cancelled`, responde 403. `POST /api/shipments/{id}/assign` la ejecuta un admin y un usuario driver recibe 403. Ninguna prueba depende del orden de 422 respecto de 401 o 403.
- Un usuario driver solo puede consultar sus propios envíos y no puede listar envíos globales, con pruebas de: `GET /api/shipments`, con y sin `status`, responde 403; `GET /api/shipments/{id}` de un envío propio responde 200, y de un envío de otro conductor o inexistente responde 403; `GET /api/drivers/{id}/shipments` del propio conductor responde 200 solo con sus envíos, y de otro conductor, exista o no, responde 403; un usuario driver sin Driver asociado no puede consultar ningún envío (403); y ninguna respuesta a un driver contiene envíos de otro conductor.
- `GET /api/shipments` tiene pruebas del orden `orders.created_at` ascendente con desempate por `shipments.id` ascendente, con valores de `created_at` explícitos y con y sin filtro `status`. Antes de implementarlo se verificó en cada base de datos que no hay pedidos con `created_at` nulo, con el recuento registrado (sección 7).
- La migración que establece `orders.created_at` como NOT NULL sigue el procedimiento de migraciones SQL manuales que ya existe en el proyecto: un archivo numerado en `backend/migrations/`, con la guarda que aborta la transacción sin modificar datos, aplicado a mano con `psql -v ON_ERROR_STOP=1`. No se introduce Alembic ni otro framework de migraciones. Esa migración real se prueba contra un PostgreSQL desechable (por ejemplo, reutilizando el aislamiento del harness PostgreSQL que ya existe en `backend/tests/pg_concurrency/`), con el archivo SQL aplicado tal cual, y las pruebas verifican: (1) con una tabla `orders` sin filas con `created_at` nulo, la migración se completa, los datos no cambian y la columna queda NOT NULL; (2) con al menos una fila con `created_at` nulo, la migración se detiene con error sin modificar ningún dato: todas las filas, incluidas las nulas, quedan idénticas y la columna sigue admitiendo NULL; (3) una vez aplicada la restricción, un INSERT y un UPDATE con SQL directo que ponen `created_at` en NULL son rechazados por la base de datos con un error de integridad (violación de NOT NULL), sin depender de que el cliente o el ORM proporcione `created_at`. Las pruebas en SQLite pueden usarse como complemento, pero no sustituyen la validación en PostgreSQL.
- La garantía FIFO de extremo a extremo (sección 6) se demuestra contra un PostgreSQL desechable, bajo READ COMMITTED (la prueba comprueba `SHOW transaction_isolation` en la conexión usada), con las pruebas siguientes. Ninguna impone un resultado HTTP que la garantía no exige:
  - Invariante con un Shipment anterior (A) y uno posterior (B) pendientes y dos asignaciones concurrentes: nunca queda B asignado mientras A sigue `pending`. El resultado de B depende de qué petición adquiere primero el punto de serialización y de los recursos disponibles, no del orden en que las peticiones se envían ni llegan al servidor. «Disponible» significa vehículo con `status = available` y conductor con `status = available`, sin bloqueo de fila de otra transacción, y cada escenario fija los recursos de antemano:
    - A adquiere primero el punto y hay al menos dos vehículos y dos conductores disponibles: A recibe 200 con `assignment_created: true` y B, tras esperar el punto, también.
    - A adquiere primero y hay exactamente un vehículo y al menos dos conductores disponibles, o al menos dos vehículos y exactamente un conductor disponible: A recibe 200 con `assignment_created: true`; B recibe 400 y queda `pending` sin vehículo ni conductor reservados.
    - A adquiere primero y no hay vehículos disponibles o no hay conductores disponibles: A recibe 400 y B recibe 409, porque A sigue `pending`.
    - B adquiere primero, con cualquier disponibilidad de recursos: B recibe 409 sin modificar nada; A, que adquiere el punto después, recibe 200 con `assignment_created: true` si hay al menos un vehículo y un conductor disponibles, y 400 si no.
    - En la variante determinista el orden de adquisición se fuerza reteniendo la transacción que adquiere primero el punto. En la variante de carrera no se retiene ninguna petición: la prueba registra cuál adquirió primero el punto, acepta solo los resultados anteriores que corresponden a ese orden de adquisición y a los recursos fijados, y en cada iteración comprueba el estado persistido final: ningún B asignado con A `pending`, como máximo un `assignment_created: true` por Shipment, ningún recurso reservado por una respuesta 400 o 409 y un único evento `status_changed` por asignación efectiva.
  - El posterior no adelanta al anterior aunque el anterior esté bloqueado por otra transacción (por ejemplo, una cancelación sin confirmar) ni aunque haya recursos para ambos: recibe 409. Un 409 no modifica Shipment, Order, vehículo ni conductor, no publica eventos y no devuelve `assignment_created: true`.
  - Una creación de pedido sin confirmar mantiene en espera a las asignaciones y, al confirmarse, su Shipment queda detrás de los pendientes anteriores.
  - Con dos creaciones concurrentes, el orden de `created_at` coincide con el orden de confirmación y cada `created_at` es estrictamente mayor que el mayor anterior, incluso cuando el mayor `created_at` existente es posterior al reloj de la base de datos. Una creación cuya transacción empezó antes que otra, pero que obtiene el punto de serialización después, recibe un `created_at` mayor (la prueba falla si se usa el inicio de la transacción). El valor se almacena en UTC con una sesión cuya zona horaria no es UTC.
  - Una cancelación del primero concurrente con la asignación del segundo da 409 hasta que la cancelación se confirma y después deja al segundo asignable.
  - Cancelación y asignación del mismo Shipment (mutación M3). La cancelación del pedido de A retiene la fila de A sin confirmar y después se lanza la asignación de A, que adquiere el punto de serialización y espera la fila de A. Al confirmarse la cancelación, la asignación responde 200 con `assignment_created: false`, no reserva recursos y no publica ningún evento de asignación, y A termina `cancelled`, nunca `assigned` después de `cancelled`. Esta prueba pasa sin mutación y falla, con un código de detección propio, con la mutación M3, que elimina el `FOR UPDATE` sobre el Shipment en `assign`: sin ese bloqueo la asignación lee A como `pending`, espera al UPDATE y, al confirmarse la cancelación, lo sobrescribe y A termina `assigned`. M3 deja de exigirse como detectable con dos asignaciones del mismo Shipment (T3-C): el punto de serialización ya las serializa y en ese escenario la mutación es equivalente. El bloqueo de fila sigue siendo necesario porque cancelar, cambiar el estado y actualizar el riesgo no toman el punto.
  - Un Shipment `pending` con `vehicle_id`, `driver_id`, `assigned_at` o `estimated_delivery` no nulos recibe 500 al asignarse, nunca 200, aunque sea el siguiente de la cola y haya recursos disponibles, sin modificar nada ni publicar eventos. Se prueba con cada campo por separado (solo `vehicle_id`, solo `driver_id`, solo `assigned_at`, solo `estimated_delivery`) y con los cuatro a la vez, y los Shipments posteriores reciben 409.
  - Límites de espera y de duración (sección 6), con los parámetros de la aplicación y valores reducidos solo para la prueba, contra un PostgreSQL desechable cuya versión se registra (`SHOW server_version`): (i) con el punto retenido por otra transacción, la asignación y la creación de pedido responden 500 al agotarse `lock_timeout`, no modifican nada, no publican eventos y no programan el aviso a n8n, y la transacción que lo retiene sigue reteniéndolo, porque `lock_timeout` no la limita; (ii) dos esperas consecutivas, cada una menor que `lock_timeout` aunque su suma no lo sea, no fallan, porque el límite es por adquisición; (iii) una transacción que retiene el punto con una sentencia más larga que `statement_timeout` es cancelada, se revierte y deja el punto libre; (iv) una transacción que retiene el punto y queda inactiva más allá de `idle_in_transaction_session_timeout` es terminada por el servidor, no deja cambios y deja el punto libre; (v) la asignación y la creación de pedido ejecutan, desde que adquieren el punto hasta el commit, como máximo un número fijo de sentencias que no depende de los datos (la prueba las cuenta), porque la cota N × (`statement_timeout` + `idle_in_transaction_session_timeout`) lo supone; (vi) la cota calculada con los valores configurados se compara con el timeout con que WF1 espera la respuesta de la asignación y el resultado se registra en el README (recomendación de configuración, no garantía de respuesta); además, cuando la respuesta HTTP se retrasa más que ese timeout mientras la transacción se confirma en PostgreSQL, WF1 registra un resultado incierto, no reintenta y no vuelve a asignar en la pasada siguiente un Shipment que ya no esté `pending`; (vii) en PostgreSQL 17 o posterior, una transacción de muchas sentencias cortas que supera `transaction_timeout` es terminada, y con `transaction_timeout` menor o igual que `statement_timeout` o `idle_in_transaction_session_timeout` actúa `transaction_timeout`; en versiones anteriores la prueba de entorno comprueba que `transaction_timeout` no existe y que el contrato no depende de él.
  - Se cumple el orden de resolución de la sección 7 (404, idempotencia con `assignment_created: false`, inconsistencia de datos, 409, 400, 200 con `assignment_created: true`): un Shipment ya asignado, en tránsito, entregado o cancelado nunca recibe 409 y un pendiente que no es el siguiente recibe 409 aunque no haya recursos.
  - Webhook y Cron, o dos Crons, sobre la misma cola nunca asignan fuera de orden.
  - Las pruebas fallan si se elimina el punto de serialización o si `created_at` se genera antes de adquirirlo (mutaciones del harness). Las pruebas de concurrencia PostgreSQL existentes y sus mutaciones que suponen que dos Shipments distintos compiten en paralelo y que el perdedor no espera (T3-D, T3-D-b, T3-E y la mutación M2) se rediseñan para el comportamiento serializado, y cada mutación sigue demostrando que su prueba falla por la razón esperada (M3, con la prueba de cancelación y asignación del mismo Shipment).
  - Las pruebas en SQLite solo complementan la lógica de posición, de 409 y de inconsistencia, no la concurrencia.
- WF1 (sección 9) se demuestra contra FastAPI real, con pruebas de: el Webhook rechaza un aviso sin `X-Webhook-Secret` válido sin llamar a FastAPI; responde 400 mediante Respond to Webhook y no llama a FastAPI ante un payload incompleto (sin `order_id`, sin `shipment_id`, cuerpo vacío o no JSON), ante un payload con campos adicionales (por ejemplo `event` u otro campo desconocido) y ante un `order_id` o `shipment_id` con UUID inválido (texto que no es UUID, longitud incorrecta, caracteres no hexadecimales, `null` o un número); con un payload válido responde 200 y la asignación continúa después de responder, también cuando tarda más que el timeout del aviso; solo llama a `POST /api/shipments/{id}/assign` con el `shipment_id` recibido; registra una asignación nueva solo cuando `assignment_created` es `true`; ante un 400 el Shipment sigue `pending` y el Cron lo recupera; ante un 404, un 5xx distinto de 503 y un timeout o error de comunicación registra respectivamente resultado inexistente, fallo y resultado incierto, no registra asignación nueva, no reintenta y continúa con el siguiente Shipment, y la pasada siguiente consulta solo `status=pending` y no reintenta un Shipment que ya no lo esté (por ejemplo, uno que FastAPI asignó antes de un timeout, o cuya transacción PostgreSQL confirmó y cuya respuesta HTTP no llegó a n8n), y si el Shipment que falló sigue `pending` el siguiente recibe 409; ante un 409 el Webhook no reintenta, no registra asignación nueva y finaliza, y el Cron registra el rechazo por la cola FIFO, detiene la pasada, no continúa con la lista anterior y no reintenta de inmediato, y la ejecución siguiente consulta de nuevo la cola; ante un código HTTP no contemplado (por ejemplo 201, 302, 405, 422 o 429) el Cron registra un resultado inesperado, detiene la pasada, no lo interpreta como éxito y no reintenta de inmediato; ante un 200 con estructura inválida, campos obligatorios ausentes o de tipo incorrecto, un `id` distinto del `shipment_id` solicitado, un `order_id` distinto del recibido en el aviso (solo en el Webhook, que es el flujo que lo conoce; el Cron no lo contrasta), `assignment_created: true` sin `status: assigned` o sin `vehicle_id` y `driver_id` no nulos, o `assignment_created: false` con `status: pending`, registra un error de contrato, no registra una asignación nueva y detiene la pasada (en el Webhook, finaliza); solo un 200 válido con `assignment_created: true` y los datos esperados se registra como asignación nueva; el Cron consulta solo `status=pending`, procesa en el orden definido y termina la pasada al primer 400, 401, 403, 503, 409, resultado inesperado o error de contrato; Webhook y Cron concurrentes sobre el mismo Shipment producen una sola asignación y un solo registro de asignación nueva; la lógica de WF1 se ramifica solo por el código HTTP y `assignment_created`, nunca por `message`; y ninguna llamada usa un JWT ni otra credencial distinta de `X-N8N-API-Key`. La validación extremo a extremo del Webhook (Respond to Webhook) se realiza en la versión de n8n instalada y su resultado queda registrado en el README de `automation/`.
- Las exportaciones finales de WF1 y WF2 están versionadas en `automation/` y no contienen valores de credenciales. El prototipo parcial de WF2 no cuenta como WF2 hasta que su auditoría esté registrada en el README de `automation/` y el workflow cumpla el contrato completo (sección 9). La conservación de ejecuciones de n8n está configurada, documentada en el README y verificada en la instancia (sección 9). WF3 permanece inactivo y no forma parte de esta Definition of Done (sección 9).
- `docker compose up --build` levanta los servicios definidos en `docker-compose.yml`. La configuración inicial manual de n8n (sección 9) está documentada en el README, incluidas las dos formas de `N8N_WEBHOOK_URL`: `http://n8n:5678/webhook` dentro de compose y `http://localhost:5678/webhook` con FastAPI en el host. Mientras requiera pasos manuales, el proyecto no declara automatización completa.
- El README explica cómo correrlo y qué decisiones se tomaron, y por qué.
- Puedes explicar cada decisión de este documento sin tenerlo abierto.

---

## 15. Cómo usar este documento con varios chats de IA
- Este documento es la única fuente de verdad. Ningún chat/agente decide un endpoint, campo o workflow por su cuenta.
- Si algo debe cambiar, se actualiza aquí primero, después se propaga al código.
- Idealmente un solo hilo mantiene el contexto completo del proyecto; los demás reciben tareas puntuales citando la sección exacta de este documento (ej. "implementa POST /api/orders tal como está en la sección 7").
