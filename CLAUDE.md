# CargoFlow — Instrucciones para Claude Code

Este archivo se carga automáticamente al inicio de cada sesión de Claude Code en este repo. Va en la raíz.

## Fuente de verdad
`CARGOFLOW_MASTER_SPEC.md` define arquitectura, modelo de datos, contrato de API y alcance. Ningún endpoint, campo o regla de negocio se implementa sin que exista primero ahí.

## Convenciones
- snake_case en backend, base de datos y payloads de API (sección 6 del spec)
- FastAPI es el único dueño de la lógica de negocio; Node.js y n8n orquestan, nunca deciden (sección 4)
- Commits convencionales: `feat:`, `fix:`, `docs:`, `chore:`

## Cómo trabajar aquí
- Backend, frontend, Flutter y n8n son alcances separados — no mezclar cambios de varios en un mismo commit/PR
- Antes de tocar un endpoint, revisar la sección 7 del master spec
- Al final de cada sesión, verificar contra el Definition of Done (sección 14)

## Lecciones y correcciones
<!-- Cada vez que corrijas algo, añade la regla aquí en una línea para que no se repita. -->
- No usar `passlib` para hashear contraseñas: es una librería sin mantenimiento y su chequeo interno rompe con `bcrypt>=4.1` (`AttributeError: __about__`, luego `ValueError: password cannot be longer than 72 bytes` en su propio self-test, no en el password real). Usar `bcrypt.hashpw` / `bcrypt.checkpw` directamente.
- `EmailStr` de Pydantic (vía `email-validator`) rechaza TLDs reservados como `.test`. Usar `@example.com` en fixtures y datos de prueba, nunca `algo.test`.
- `Settings` de `pydantic-settings` usa `model_config = SettingsConfigDict(...)`, no `class Config:` (deprecado desde Pydantic v2).
- SQLite en memoria (`sqlite:///:memory:`) crea una base nueva por cada conexión. Los tests necesitan `poolclass=StaticPool` en el engine de pruebas, si no las tablas creadas en `create_all()` no existen para la petición real ("no such table").
- Starlette (base de FastAPI) usa `httpx2`, no `httpx`, para `TestClient` desde que el desarrollo de `httpx` original se estancó. Poner `httpx2` directo en requirements.txt, no depender de que llegue como dependencia transitiva.
- `JWT_SECRET` debe tener al menos 32 bytes o PyJWT lanza `InsecureKeyLengthWarning` en cada firma HS256. El valor por defecto en `.env.example` y en `config.py` ya cumple esto — no lo acortes.
