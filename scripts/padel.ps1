$ErrorActionPreference = "Stop"

# ========= Config =========
$BaseUrl = "http://localhost:8000"
$DbUser  = "padel"
$DbName  = "padel_mvp"

# 4 usuarios de prueba (2 hombres, 2 mujeres)
$Players = @(
  @{ phone="+573001111111"; alias="andres_m1"; gender="M"; primary="5ta" }, # HM 5ta -> MX C (según tu map)
  @{ phone="+573002222222"; alias="carlos_m2"; gender="M"; primary="6ta" }, # HM 6ta -> MX D
  @{ phone="+573003333333"; alias="laura_f1";  gender="F"; primary="D"   }, # WM D -> MX D
  @{ phone="+573004444444"; alias="sofia_f2";  gender="F"; primary="B"   }  # WM B -> MX B
)

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

function Wait-ForDb {
  param([int]$Retries = 60)
  Step "Esperando DB (pg_isready)..."
  for ($i=1; $i -le $Retries; $i++) {
    try {
      $out = docker compose exec -T db pg_isready -U $DbUser -d $DbName 2>$null
      if ($out -match "accepting connections") {
        Write-Host "DB OK"
        return
      }
    } catch {}
    Start-Sleep -Seconds 1
  }
  throw "DB no respondió (pg_isready) después de $Retries segundos."
}

function Wait-ForApi {
  param([int]$Retries = 60)
  Step "Esperando API (/health)..."
  for ($i=1; $i -le $Retries; $i++) {
    try {
      $r = Invoke-RestMethod "$BaseUrl/health"
      if ($r.ok -eq $true) {
        Write-Host "API OK"
        return
      }
    } catch {}
    Start-Sleep -Seconds 1
  }
  throw "API no respondió /health después de $Retries segundos."
}

function ReqOtp($phone) {
  Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/otp/request" `
    -ContentType "application/json" `
    -Body (@{ phone_e164=$phone } | ConvertTo-Json)
}

function VerifyOtp($phone, $code) {
  Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/otp/verify" `
    -ContentType "application/json" `
    -Body (@{ phone_e164=$phone; code=$code } | ConvertTo-Json)
}

function PatchProfile($token, $alias, $gender, $primaryCode) {
  Invoke-RestMethod -Method Patch -Uri "$BaseUrl/me/profile" `
    -Headers @{ Authorization="Bearer $token" } `
    -ContentType "application/json" `
    -Body (@{
      alias=$alias
      gender=$gender
      primary_category_code=$primaryCode
      is_public=$true
    } | ConvertTo-Json)
}

function GetMe($token) {
  Invoke-RestMethod -Uri "$BaseUrl/me" -Headers @{ Authorization="Bearer $token" }
}

function GetLadderStates($token) {
  Invoke-RestMethod -Uri "$BaseUrl/me/ladder-states" -Headers @{ Authorization="Bearer $token" }
}

function CreateMatch($token, $participants, $sets) {
  $playedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  $body = @{
    club_id = $null
    played_at = $playedAt
    participants = $participants
    score = @{
      score_json = @{ sets = $sets }
    }
  } | ConvertTo-Json -Depth 10

  Invoke-RestMethod -Method Post -Uri "$BaseUrl/matches" `
    -Headers @{ Authorization="Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
}

function ConfirmMatch($token, $matchId, $status="confirmed") {
  Invoke-RestMethod -Method Post -Uri "$BaseUrl/matches/$matchId/confirm" `
    -Headers @{ Authorization="Bearer $token" } `
    -ContentType "application/json" `
    -Body (@{ status=$status; source="app" } | ConvertTo-Json)
}

function GetMyMatches($token) {
  Invoke-RestMethod -Uri "$BaseUrl/me/matches?limit=20&offset=0" `
    -Headers @{ Authorization="Bearer $token" }
}

function GetMatchDetail($token, $matchId) {
  Invoke-RestMethod -Uri "$BaseUrl/matches/$matchId/detail" `
    -Headers @{ Authorization="Bearer $token" }
}

function GetConfirmations($token, $matchId) {
  Invoke-RestMethod -Uri "$BaseUrl/matches/$matchId/confirmations" `
    -Headers @{ Authorization="Bearer $token" }
}

function Sql($query) {
  docker compose exec -T db psql -U $DbUser -d $DbName -c $query
}

# ========= RUN =========

Step "RESET: down -v"
docker compose down -v | Out-Host

Step "UP: db + api"
docker compose up -d | Out-Host

Wait-ForDb
Wait-ForApi

Step "Migraciones Alembic"
docker compose run --rm api alembic upgrade head | Out-Host

# ---- Crear usuarios: OTP request -> verify -> token, y guardar user_id ----
Step "Crear 4 usuarios (OTP request+verify)"
$Tokens = @{}
$UserIds = @{}

foreach ($pl in $Players) {
  $phone = $pl.phone
  $r = ReqOtp $phone
  $code = $r.dev_code
  $v = VerifyOtp $phone $code

  $Tokens[$phone] = $v.access_token
  Write-Host "$phone => OTP $code => TOKEN OK"

  $me = GetMe $Tokens[$phone]
  $UserIds[$phone] = $me.id
  Write-Host "user_id: $($me.id)"
}

# ---- Onboarding: profile + category principal (crea ladder-states HM/WM + MX) ----
Step "Onboarding (perfil + categoría principal)"
foreach ($pl in $Players) {
  $phone = $pl.phone
  PatchProfile $Tokens[$phone] $pl.alias $pl.gender $pl.primary | Out-Null

  $ls = GetLadderStates $Tokens[$phone]
  $lsJson = ($ls | ConvertTo-Json -Depth 6)
  Write-Host "$($pl.alias) ladder-states => $lsJson"
}

# ---- Crear match MX (2M + 2F) por parejas ----
# Team1: M1 + F1
# Team2: M2 + F2
Step "Crear match MX (por parejas M+F vs M+F)"
$u1 = $UserIds[$Players[0].phone] # andres_m1 (M)
$u2 = $UserIds[$Players[1].phone] # carlos_m2 (M)
$u3 = $UserIds[$Players[2].phone] # laura_f1  (F)
$u4 = $UserIds[$Players[3].phone] # sofia_f2  (F)

$participants = @(
  @{ user_id=$u1; team_no=1 },
  @{ user_id=$u3; team_no=1 },
  @{ user_id=$u2; team_no=2 },
  @{ user_id=$u4; team_no=2 }
)

# marcador válido: 6-4 7-5 (gana Team1)
$sets = @(
  @{ t1=6; t2=4 },
  @{ t1=7; t2=5 }
)

$m = CreateMatch $Tokens[$Players[0].phone] $participants $sets
$mid = $m.id
Write-Host "MATCH ID: $mid | ladder=$($m.ladder_code) | category_id=$($m.category_id) | status=$($m.status)"

# ---- Confirmación 3/4 ----
Step "Confirmar 3/4 (debe pasar a verified y aplicar ranking)"
ConfirmMatch $Tokens[$Players[0].phone] $mid "confirmed" | Out-Host
ConfirmMatch $Tokens[$Players[2].phone] $mid "confirmed" | Out-Host
ConfirmMatch $Tokens[$Players[1].phone] $mid "confirmed" | Out-Host
# El 4to queda pendiente a propósito

# ---- Validaciones DB ----
Step "Validación DB: match status, rank_processed_at"
Sql "SELECT id, status, confirmed_count, has_dispute, rank_processed_at FROM matches WHERE id = '$mid';" | Out-Host

Step "Validación DB: rating_events (4 filas)"
Sql "SELECT user_id, old_rating, new_rating, delta, k_factor, weight, created_at FROM rating_events WHERE match_id = '$mid' ORDER BY created_at;" | Out-Host

# ---- Endpoints frontend ----
Step "Endpoint: GET /me/matches"
(GetMyMatches $Tokens[$Players[0].phone] | ConvertTo-Json -Depth 8) | Out-Host

Step "Endpoint: GET /matches/{id}/detail"
(GetMatchDetail $Tokens[$Players[0].phone] $mid | ConvertTo-Json -Depth 10) | Out-Host

Step "Endpoint: GET /matches/{id}/confirmations"
(GetConfirmations $Tokens[$Players[0].phone] $mid | ConvertTo-Json -Depth 10) | Out-Host

Step "DONE ✅"
Write-Host "Match ID final: $mid"
