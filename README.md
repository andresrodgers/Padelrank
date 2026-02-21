# Padel Ranking MVP (Neiva)

Backend API para registro de partidos, confirmaciones y ranking de padel.

## Stack
- FastAPI
- PostgreSQL 16
- SQLAlchemy + Alembic
- Docker Compose

## Requisitos
- Docker
- Docker Compose

## Configuracion
1. Copia `.env.example` a `.env`.
2. Define secretos reales fuera del repositorio:
- `JWT_SECRET`
- `OTP_PEPPER`

`/.env` esta ignorado por git. No guardes secretos reales en commits.

## Runtime tuning (escala backend)
- `API_WORKERS` (default `4`): procesos de Uvicorn para concurrencia.
- `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`: tuning del pool SQLAlchemy por worker.
- `DB_POOL_TIMEOUT_SECONDS` / `DB_POOL_RECYCLE_SECONDS`: estabilidad de conexiones.

## Seguridad backend
- `ALLOWED_HOSTS`: lista separada por comas para validar Host header.
- `SECURITY_HEADERS_ENABLED=true`: activa headers de seguridad HTTP.
- En produccion define `ALLOWED_HOSTS` con tus dominios reales (sin comodines globales).

## Arranque (modo normal)
1. Levantar servicios:
```bash
docker compose up -d db
docker compose up --build -d api
```
2. Ejecutar migraciones:
```bash
docker compose run --rm api alembic upgrade head
```
3. API y docs:
- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`

## Arranque (modo desarrollo con autoreload)
Usa el compose base + override dev:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## Reglas de negocio relevantes
- Un partido se crea con exactamente 4 participantes.
- El creador del partido debe estar entre esos 4 participantes.
- Cada equipo debe tener 2 participantes (`team_no` 1 y 2).
- Ladders permitidos por genero:
- `HM`: 4M
- `WM`: 4F
- `MX`: 2M + 2F
- El creador queda confirmado al crear el partido.
- El partido se verifica cuando hay confirmaciones de ambos equipos.
- Si vence la ventana de confirmacion y sigue pendiente, el partido expira.
- Ningun jugador puede crear/ser invitado si no cumple perfil minimo:
- canal verificado (`phone` o `email`),
- `alias`,
- `gender`,
- `category` en ladder correspondiente (o base).

## Diseno definitivo de auth (acceso app)
- Identidades: `email` y/o `phone`.
- OTP:
- se usa para verificacion de registro y reset de password.
- no se usa para login diario.
- Login diario: `identifier (email|phone) + password`.
- Tokens: `access_token` corto + `refresh_token`.
- Refresh token rotativo:
- cada refresh invalida el anterior.
- en DB se guarda solo hash del refresh (`auth_sessions.refresh_hash`).
- Logout: revoca sesion de refresh actual.
- Password: hash con `bcrypt`.
- Rate limit base:
- OTP con cooldown de 2 minutos por contacto.
- login con contador por `login_key_hash` en ventana de 15 minutos.

## Entidades de auth en DB
- `users`
- `auth_identities`
- `auth_credentials`
- `auth_sessions`

## Cambio de contacto (verificacion obligatoria)
- `POST /me/contact-change/request`
  - genera OTP para nuevo `email` o `telefono`.
  - valida unicidad del contacto en `users` y `auth_identities`.
- `POST /me/contact-change/confirm`
  - requiere OTP valido.
  - solo al confirmar se actualiza `users.email` o `users.phone_e164`.
  - sincroniza y deja verificada la identidad en `auth_identities`.

## Perfil minimo (`/me/play-eligibility`)
- Debe cumplir:
- `alias`
- `gender` (`M|F|U`)
- `category` por ladder correspondiente o base
- `canal_verificado` (`phone_verified` o `email_verified`)
- Si falta cualquiera:
- no puede crear partido,
- no puede ser invitado.

## Perfil completo (enriquecido)
- `country` (default `CO`)
- `city`
- `handedness` (`R|L|U`)
- `preferred_side` (`drive|reves|both|U`)
- `birthdate` (nullable)
- `first_name` y `last_name` (nullable)
- `first_name/last_name` NO bloquean partidos.
- `country/city` NO bloquean partidos (si se usan para ranking/filtros).

## Ranking (global/pais/ciudad)
- Endpoint unico: `GET /rankings/{ladder_code}/{category_id}`
- Global: sin query params.
- Pais: `?country=CO` (ISO-2).
- Ciudad: `?country=CO&city=Neiva`.
- El rating siempre sale de `user_ladder_state` (uno por `user + ladder + categoria`), sin duplicar por ubicacion.

## History (timeline auditable)
- `GET /history/me`: timeline del usuario autenticado.
- `GET /history/users/{user_id}`: timeline publico (solo verificados para terceros).
- `GET /history/users/{user_id}/matches/{match_id}`: detalle auditable del evento.
- Filtros: `ladder`, `date_from`, `date_to`, `state_scope`, `club_id`, `club_city`.

## Analytics (read model materializado)
- `GET /analytics/me`: metricas privadas por ladder.
- `GET /analytics/users/{user_id}`: metricas publicas (si perfil publico).
- Se actualiza incrementalmente cuando un partido pasa a `verified`.
- Es idempotente por `(user_id, match_id)` para evitar dobles conteos.
- Rebuild completo (admin/internal): `cd backend && python scripts/rebuild_analytics.py`.

## CI
El workflow de GitHub Actions ahora:
1. Levanta Postgres de servicio.
2. Ejecuta `alembic upgrade head`.
3. Valida imports.
4. Corre tests con `pytest`.

## Tests (unificados)
- Carpeta unica: `backend/tests`
- Unit tests: `cd backend && pytest -q`
- Integracion API (requiere API arriba): `cd backend && RUN_API_INTEGRATION=1 pytest -q tests/test_api_integration.py`
- Performance smoke (opcional): `cd backend && RUN_API_INTEGRATION=1 RUN_PERF_TESTS=1 pytest -q tests/test_ranking_performance.py`
- History API (integracion): `cd backend && RUN_API_INTEGRATION=1 pytest -q tests/test_history_api.py`
- History performance smoke: `cd backend && RUN_API_INTEGRATION=1 RUN_PERF_TESTS=1 pytest -q tests/test_history_performance.py`
- Analytics API (integracion): `cd backend && RUN_API_INTEGRATION=1 pytest -q tests/test_analytics_api.py`
- Analytics performance smoke: `cd backend && RUN_API_INTEGRATION=1 RUN_PERF_TESTS=1 pytest -q tests/test_analytics_performance.py`

## Nota de seguridad
Si en algun momento un secreto real se subio al repositorio, debes rotarlo inmediatamente.
