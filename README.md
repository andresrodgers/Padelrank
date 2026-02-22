# Rivio Backend API (Padel Ranking MVP)

Backend de Rivio para autenticacion, perfil de jugador, partidos, ranking, historial competitivo y analitica.

Version actual de API/OpenAPI: `0.1.7`

## Estado del proyecto (v0.1.7)

### Implementado
- Auth con `access_token` + `refresh_token` rotativo.
- Registro/verificacion por OTP (entorno dev) + login por password.
- Perfil de jugador completo (alias, genero, categoria, ubicacion, mano, lado, datos personales opcionales).
- Avatar con presets y modo upload controlado por politica.
- Elegibilidad de juego (`/me/play-eligibility`).
- Partidos 4 jugadores, confirmacion por equipos y verificacion.
- Ranking global/pais/ciudad con fuente unica en `user_ladder_state`.
- Historial (timeline) auditable con filtros y paginacion.
- Analitica materializada e incremental al verificar partidos.
- Entitlements (`FREE` / `RIVIO_PLUS`) desacoplados de billing.
- Soporte: `mailto` trazable + tickets in-app con control anti-spam.
- Cuenta: `logout-all`, solicitud/cancelacion de eliminacion con ventana de gracia.
- Billing scaffold (provider-agnostic) con:
- checkout stub/store-managed base,
- webhooks idempotentes,
- validacion server-side App Store/Google Play (base),
- reconciliacion periodica.

### Pendiente (siguiente fase)
- Conectores store al 100% productivo:
- validacion criptografica nativa completa en notificaciones Apple/Google,
- endurecimiento operativo final para produccion mobile.
- Integracion de OTP con proveedor real (Twilio).

---

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
2. Define secretos reales fuera del repositorio.

Minimo recomendado:
- `DATABASE_URL`
- `JWT_SECRET`
- `OTP_PEPPER`

Billing/store (cuando se habilite en entornos reales):
- `BILLING_PROVIDER` (`none|stripe|app_store|google_play|manual`)
- `BILLING_PRODUCT_PLAN_MAP` (ejemplo: `rivio_plus_monthly=RIVIO_PLUS`)
- App Store:
- `APP_STORE_SHARED_SECRET`
- Google Play:
- `GOOGLE_PLAY_PACKAGE_NAME`
- `GOOGLE_PLAY_SERVICE_ACCOUNT_EMAIL`
- `GOOGLE_PLAY_SERVICE_ACCOUNT_PRIVATE_KEY_PEM`
- Seguridad webhooks:
- `BILLING_REQUIRE_WEBHOOK_SIGNATURE`
- `BILLING_WEBHOOK_SECRET`
- `BILLING_WEBHOOK_STRIPE_SECRET`
- `BILLING_WEBHOOK_APP_STORE_SECRET`
- `BILLING_WEBHOOK_GOOGLE_PLAY_SECRET`

`/.env` esta ignorado por git.

## Arranque
1. Levantar servicios:
```bash
docker compose up -d db
docker compose up --build -d api
```
2. Aplicar migraciones:
```bash
docker compose run --rm api alembic upgrade head
```
3. API y docs:
- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`

## Arranque dev con autoreload
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

---

## Modulos funcionales

### 1) Auth y seguridad
- Identidades soportadas: `email` y/o `phone`.
- OTP para registro y reset de password.
- Login diario por `identifier + password`.
- Refresh token rotativo con hash en DB.
- `POST /auth/logout` y `POST /auth/logout-all`.
- Headers de seguridad y validacion de `Host`.

### 2) Perfil, elegibilidad y cuenta
- `GET /me`, `PATCH /me/profile`, `GET /me/ladder-states`
- `GET /me/play-eligibility`
- Avatar:
- `GET /me/avatar-presets`
- `GET /me/avatar/upload-policy`
- `POST /me/avatar/preset`
- `POST /me/avatar/upload`
- Ciclo de cuenta:
- `POST /me/account/deletion-request`
- `GET /me/account/deletion-status`
- `POST /me/account/deletion-cancel`

### 3) Partidos
- Creacion con 4 participantes y validaciones de composicion por ladder.
- Confirmacion por jugadores.
- Verificacion al confirmar ambos equipos.
- Aplicacion atomica de ranking + analitica al verificar.

### 4) Ranking
- Endpoint unico:
- `GET /rankings/{ladder_code}/{category_id}`
- Scopes:
- Global (sin filtro)
- Pais (`?country=CO`)
- Ciudad (`?country=CO&city=Neiva`)
- Fuente oficial de rating: `user_ladder_state` (sin duplicar ratings por ubicacion).

### 5) History (timeline auditable)
- `GET /history/me`
- `GET /history/users/{user_id}`
- `GET /history/users/{user_id}/matches/{match_id}`
- Filtros por ladder, rango de fechas, estado, club/ciudad.
- Publico solo verificados; privado enmascara perfiles no publicos.

### 6) Analytics (read model materializado)
- `GET /analytics/me`
- `GET /analytics/me/dashboard`
- `GET /analytics/users/{user_id}`
- `GET /analytics/users/{user_id}/dashboard`
- Export premium:
- `GET /analytics/me/export` (solo `RIVIO_PLUS`)

### 7) Entitlements (Rivio / Rivio+)
- `GET /entitlements/me`
- `GET /entitlements/plans`
- `POST /entitlements/me/simulate` (solo dev)

### 8) Soporte
- `GET /support/contact` (mailto trazable)
- `POST /support/tickets`
- `GET /support/tickets/me`

### 9) Billing (store-managed base)
- `GET /billing/me`
- `POST /billing/checkout-session`
- `POST /billing/webhooks/{provider}`
- `POST /billing/store/app-store/validate`
- `POST /billing/store/google-play/validate`
- `POST /billing/simulate/subscription` (solo dev)
- `POST /billing/reconcile` (solo dev)

---

## Scripts operativos
- Rebuild de analitica:
```bash
cd backend && python scripts/rebuild_analytics.py
```
- Limpieza de artefactos auth:
```bash
cd backend && python scripts/cleanup_auth_artifacts.py
```
- Procesar eliminaciones de cuenta programadas:
```bash
cd backend && python scripts/process_account_deletions.py
```
- Reconciliar billing de tiendas:
```bash
cd backend && python scripts/reconcile_billing.py
```

---

## CI y tests

El workflow CI:
1. Levanta Postgres de servicio.
2. Ejecuta `alembic upgrade head`.
3. Levanta API y valida `/health`.
4. Corre tests con integracion habilitada.

Suite actual:
- Carpeta unica: `backend/tests`
- Ejecucion completa:
```bash
cd backend && RUN_API_INTEGRATION=1 pytest -q tests
```

Smokes utiles:
- Core regression:
```bash
cd backend && RUN_API_INTEGRATION=1 pytest -q tests/test_regression_core_modules.py
```
- Billing:
```bash
cd backend && RUN_API_INTEGRATION=1 pytest -q tests/test_billing_api.py
```

---

## Arquitectura de datos (resumen)
- Rating oficial por jugador/ladder/categoria:
- `user_ladder_state`
- Timeline de partidos:
- `matches`, `match_participants`, `match_confirmations`, `match_scores`
- Read model de analitica:
- `user_analytics_state`, `user_analytics_match_applied`, `user_analytics_partner_stats`, `user_analytics_rival_stats`
- Entitlements y planes:
- `user_entitlements`
- Soporte:
- `support_tickets`
- Billing:
- `billing_customers`, `billing_subscriptions`, `billing_webhook_events`, `billing_checkout_sessions`

---

## Seguridad y operacion
- No subir secretos reales al repositorio.
- Rotar secretos si hubo exposicion.
- Definir `ALLOWED_HOSTS` reales en produccion.
- Ejecutar tareas periodicas de mantenimiento:
- cleanup auth,
- reconciliacion billing,
- procesamiento de eliminaciones programadas.

---

## Releases
- Ultimo tag estable publicado: `v0.1.7`
- Rama de referencia actual: `main`
