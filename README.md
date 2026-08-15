# CargoFlow

Plataforma de gestión logística — proyecto de portafolio para XCargo.

## Documentos
- `CARGOFLOW_MASTER_SPEC.md` — arquitectura, modelo de datos, contrato de API. Fuente de verdad del proyecto.
- `CLAUDE.md` — instrucciones que Claude Code carga automáticamente en cada sesión.

## Quick start
1. `cp .env.example .env`
2. `docker compose up -d postgres redis n8n`
3. `cd backend && pip install -r requirements.txt && pytest` — corre los tests con SQLite en memoria
4. `uvicorn app.main:app --reload` (desde `backend/`) — API en http://localhost:8000
5. `claude` en la raíz del repo para seguir con Claude Code

## Estado
- Sprint 0: arquitectura + infraestructura base — completo
- Sprint 1: backend (FastAPI) — en curso
  - [x] Modelo de datos (users, drivers, vehicles, orders, shipments)
  - [x] POST /api/auth/login (con tests)
  - [ ] CRUD de orders/shipments/vehicles/drivers
