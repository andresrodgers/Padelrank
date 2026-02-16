# PadelRank — Estructura del proyecto (v0.1.0)

Esta versión organiza el backend por **módulos** (auth, matches, rankings, etc.) para que sea más fácil mantener, crecer y no romper cosas cuando agreguemos nuevas funciones.


## 1) Raíz del proyecto (carpeta principal)

- `.env`  
  Variables locales (credenciales, modo dev, etc.). No se sube con datos reales.

- `.env.example`  
  Plantilla de variables para que cualquiera pueda configurar el proyecto.

- `docker-compose.yml`  
  Arranca todo lo necesario para correr el proyecto (API + Base de datos).

- `README.md`  
  Instrucciones generales del proyecto (lo iremos enriqueciendo con el tiempo).

- `.github/workflows/ci.yml`  
  Automatización (CI): pruebas/build cuando subimos cambios al repo.

- `docs/`  
  Documentación interna del proyecto (este archivo vive aquí).

- `frontend/`  
  Espacio reservado para el frontend (por ahora puede estar vacío).

- `scripts/`  
  Scripts de pruebas rápidas (smoke tests) para validar que todo funcione.


## 2) `scripts/` (pruebas y validación)

- `padel_lib.ps1`  
  “Caja de herramientas” con funciones para llamar la API:
  - crear usuarios de prueba
  - crear partidos
  - confirmar partidos
  - consultar detalles
  - buscar usuarios por alias

- `padel.ps1`  
  Prueba completa automatizada (harness / smoke test):
  - reinicia contenedores (db + api)
  - corre migraciones
  - crea 4 usuarios
  - crea un partido
  - confirma con 2 votos (1 por equipo)
  - verifica que el partido queda **verified** y que se aplicó ranking
  - valida resultados directo en la base de datos

> Nota: estos scripts son para **testear**, no son parte del funcionamiento normal del sistema en producción.


## 3) `backend/` (motor del sistema)

Aquí está el backend (la “lógica” del producto).

### 3.1 Archivos principales

- `Dockerfile`  
  Cómo se construye la imagen del backend.

- `requirements.txt`  
  Lista de librerías necesarias.

- `alembic.ini`  
  Configuración de migraciones (cambios de base de datos).


## 4) `backend/alembic/` (cambios en la base de datos)

- `env.py` y `script.py.mako`  
  Archivos internos para ejecutar migraciones.

- `versions/`  
  Historial de cambios de la base de datos (cada archivo es un paso):
  - `0001_init_p0.py` → crea la estructura inicial (tablas base)
  - `0002_categories_real_and_mx_map.py` → categorías y mapeos iniciales
  - `0003_unique_alias_lower.py` → alias único en minúsculas (para usuarios)
  - `0004_match_score_proposal.py` → ajustes recientes relacionados con score/partidos


## 5) `backend/app/` (código principal de la API)

### 5.1 Arranque de la app

- `main.py`  
  Punto de entrada del backend (donde se “enciende” la API).


## 6) `backend/app/api/` (conexión de rutas)

- `router.py`  
  Aquí se registran las rutas principales (auth, matches, etc.) y sus prefijos.

- `deps.py`  
  Cosas comunes que necesitan varias rutas (por ejemplo: usuario actual, conexión a DB).

- `routes/`  
  Rutas “clásicas” del proyecto. En esta versión se pueden usar como **puente/compatibilidad**:
  - `auth.py`, `matches.py`, `rankings.py`, etc.

> Importante: aunque ahora existe la carpeta `modules/`, `routes/` ayuda a mantener orden y compatibilidad. Más adelante podemos simplificar si lo vemos necesario.


## 7) `backend/app/modules/` (módulos por dominio)

Esta es la mejora grande de v0.1.0: cada parte del producto vive en un módulo.

Cada módulo normalmente tiene:
- `api.py` → endpoints (las “pantallas”/acciones disponibles desde el app)
- `__init__.py` → archivo de soporte para importar el módulo

Módulos actuales:

- `auth/`  
  Inicio de sesión (OTP), tokens y acceso.

- `me/`  
  Todo lo del usuario autenticado (mi perfil, mi estado, mis datos).

- `users/`  
  Acciones sobre usuarios (ej: búsqueda por alias, lookups).

- `matches/`  
  Partidos:
  - creación de partido con 4 jugadores
  - confirmación del resultado
  - validación: se verifica con **2 confirmaciones**, una por equipo
  - expiración por tiempo si no confirman

- `rankings/`  
  Ranking y puntos:
  - aplica cálculo cuando un partido queda **verified**
  - registra eventos de rating

- `config/`  
  Datos de configuración/parametría que usa el sistema.


## 8) `backend/app/schemas/` (formatos de entrada y salida)

Aquí van los “formatos” de datos que la API recibe y devuelve.

Ejemplos:
- `auth.py` → formatos de login/OTP
- `match.py` → formatos de crear partido, score, responses
- `users.py` → formatos de búsqueda/lookup de usuarios
- `ranking.py` → formatos de respuestas del ranking
- `me.py`, `config.py` → formatos del perfil/configuración


## 9) `backend/app/models/` (lo que se guarda en base de datos)

Representa las entidades principales del sistema:
- `user.py` y `profile.py` → usuario y perfil
- `match.py` → partido, participantes, confirmaciones
- `rating_event.py` → historial de cambios de puntos/rating
- `category.py`, `ladder.py` → categorías y tipo de ladder (HM/WM/MX)
- `audit_log.py` → registro de acciones importantes
  

## 10) `backend/app/services/` (reglas internas del negocio)

Funciones internas que soportan la lógica:
- `elo.py` → cálculo de cambios de rating
- `score_features.py` → utilidades para manejar score/sets
- `audit.py` → registro de acciones (auditoría)


## 11) Resumen funcional (en lenguaje simple)

- Un partido se crea **con 4 jugadores** (no existe partido “vacío”).
- Al crearlo, el creador queda confirmado automáticamente (según el flujo actual).
- Para que un partido sea válido (**verified**) se necesitan:
  - mínimo **2 confirmaciones**
  - y deben venir de **equipos diferentes** (1 por equipo)
- Si se pasa la ventana de confirmación, el partido queda **expired** y no suma.
- Cuando queda **verified**, se aplica el ranking y se guardan eventos de rating.