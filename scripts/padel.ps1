# scripts/padel.ps1
# Harness / Smoke test completo:
# - docker down -v
# - up db+api
# - esperar db y api
# - alembic upgrade head
# - crear 4 usuarios + onboarding
# - crear match MX
# - test confirmación: 2 votos (1 por equipo) => verified + ranking
# - validaciones en DB
#
# IMPORTANTE:
# - Si quieres que $u1..$u4 y $mid queden disponibles para comandos manuales,
#   ejecuta este archivo con DOT-SOURCE:
#   . .\scripts\padel.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --- CONFIG ---
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

. "$PSScriptRoot\padel_lib.ps1"
Set-Base "http://localhost:8000"

function Write-Section($t) {
  Write-Host ""
  Write-Host "=== $t ==="
}

function Wait-DbReady {
  Write-Section "Esperando DB (pg_isready)..."
  for ($i=0; $i -lt 40; $i++) {
    try {
      docker compose exec -T db pg_isready -U padel -d padel_mvp | Out-Null
      Write-Host "DB OK"
      return
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  throw "DB no respondió a tiempo"
}

function Wait-ApiReady {
  Write-Section "Esperando API (/health)..."
  for ($i=0; $i -lt 60; $i++) {
    try {
      $r = Invoke-WebRequest "$(Get-Base)/health" -UseBasicParsing -TimeoutSec 2
      if ($r.StatusCode -eq 200) { Write-Host "API OK"; return }
    } catch {}
    Start-Sleep -Seconds 1
  }
  throw "API no respondió a tiempo"
}

function Alembic-Upgrade {
  Write-Section "Migraciones Alembic"
  docker compose run --rm api alembic upgrade head
}

function Db-Query([string]$sql) {
  return docker compose exec -T db psql -U padel -d padel_mvp -c $sql
}

# --- RESET STACK ---
Write-Section "RESET: down -v"
docker compose down -v | Out-Null

Write-Section "UP: db + api"
docker compose up -d db api | Out-Null

Wait-DbReady
Wait-ApiReady
Alembic-Upgrade

# --- CREAR 4 USUARIOS ---
Write-Section "Crear 4 usuarios (OTP request+verify)"
$u1 = New-UserAndProfile "+573001111111" "andres_m1" "M" "5ta"
Write-Host "$($u1.phone) => TOKEN OK"; Write-Host "user_id: $($u1.user_id)"

$u2 = New-UserAndProfile "+573002222222" "carlos_m2" "M" "6ta"
Write-Host "$($u2.phone) => TOKEN OK"; Write-Host "user_id: $($u2.user_id)"

$u3 = New-UserAndProfile "+573003333333" "laura_f1" "F" "D"
Write-Host "$($u3.phone) => TOKEN OK"; Write-Host "user_id: $($u3.user_id)"

$u4 = New-UserAndProfile "+573004444444" "sofia_f2" "F" "B"
Write-Host "$($u4.phone) => TOKEN OK"; Write-Host "user_id: $($u4.user_id)"

# --- ONBOARDING CHECK (ladder-states) ---
Write-Section "Onboarding (perfil + categoría principal)"
(Get-MyLadderStates $u1.token) | ConvertTo-Json -Depth 20 | Write-Host
(Get-MyLadderStates $u2.token) | ConvertTo-Json -Depth 20 | Write-Host
(Get-MyLadderStates $u3.token) | ConvertTo-Json -Depth 20 | Write-Host
(Get-MyLadderStates $u4.token) | ConvertTo-Json -Depth 20 | Write-Host

# --- CREAR MATCH MX ---
Write-Section "Crear match MX"
# OJO: aquí usamos un creador externo para simular el caso real (alguien registra el partido).
$creatorToken = Get-Token "+573009990200"

$playedAt = (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("yyyy-MM-ddTHH:mm:ssZ")
$score = @{ sets = @(@{t1=6;t2=4}, @{t1=7;t2=5}) }

$m = New-MatchMX-Creator $creatorToken $u1 $u2 $u3 $u4 $score $playedAt
$mid = $m.id
Write-Host "MATCH ID: $mid | ladder=$($m.ladder_code) | category_id=$($m.category_id) | status=$($m.status)"
if (-not $mid) { throw "No se creó match" }

# --- TEST CONFIRM: 2 votos, uno por equipo => verified ---
Write-Section "Confirmar 2/4 (UNO por cada equipo) => debe pasar a verified y aplicar ranking"
$r1 = Confirm-Match -token $u1.token -matchId $mid -status confirmed -source "ps1"
$r1 | ConvertTo-Json -Depth 10 | Write-Host

$r2 = Confirm-Match -token $u2.token -matchId $mid -status confirmed -source "ps1"
$r2 | ConvertTo-Json -Depth 10 | Write-Host

# --- VALIDAR DB ---
Write-Section "Validación DB: match status, rank_processed_at"
Db-Query "SELECT id, status, confirmed_count, has_dispute, rank_processed_at FROM matches WHERE id='$mid';"

Write-Section "Validación DB: rating_events (4 filas)"
Db-Query "SELECT user_id, old_rating, new_rating, delta, k_factor, weight, created_at FROM rating_events WHERE match_id='$mid' ORDER BY user_id;"

# --- ENDPOINTS ---
Write-Section "Endpoint: GET /matches/{id}/detail"
(Get-MatchDetail -token $u1.token -matchId $mid) | ConvertTo-Json -Depth 20 | Write-Host

Write-Section "Endpoint: GET /matches/{id}/confirmations"
(Get-MatchConfirmations -token $u1.token -matchId $mid) | ConvertTo-Json -Depth 20 | Write-Host

Write-Section "DONE ✅"
Write-Host "Match ID final: $mid"
