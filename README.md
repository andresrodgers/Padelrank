# Padel Ranking MVP (Neiva) — FastAPI + Postgres + Alembic (P0)

## Qué incluye (P0)
- FastAPI con endpoints base: Auth OTP, Perfil, Config, Matches (crear/confirmar), Rankings.
- PostgreSQL con modelo P0 + seed de ladders, categorías (C1..C3) y 3 clubes (placeholders).
- Alembic migration inicial (0001).

## Requisitos
- Docker + Docker Compose

## Arranque
1) Levanta Postgres:
```bash
docker compose up -d db
```

2) Crea el esquema:
```bash
docker compose run --rm api alembic upgrade head
```

3) Corre la API:
```bash
docker compose up --build api
```

API: http://localhost:8000  
Docs: http://localhost:8000/docs

> OTP en DEV: el endpoint `/auth/otp/request` devuelve el `dev_code` (solo si `ENV=dev`).

## Variables de entorno
Están en `docker-compose.yml` (puedes moverlas a un `.env` luego).

## Notas rápidas de MVP
- Match rankeable: 3/4 confirman antes de 48h y sin disputa.
- Disputa: no afecta ranking.
- Provisional: <5 verificados (cap de delta).
- Ladders: HM/WM/MX. En MX exige 2M+2F.
