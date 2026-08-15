# Backend — FastAPI

Sprint 1: auth + modelo de datos (secciones 5-7 del master spec).

## Local
```
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload
```

## Tests
```
pytest
```
Los tests usan SQLite en memoria (no necesitan Postgres corriendo).

## Estado
- [x] Modelo de datos (users, drivers, vehicles, orders, shipments)
- [x] POST /api/auth/login
- [ ] CRUD de orders/shipments/vehicles/drivers -- resto del Sprint 1
