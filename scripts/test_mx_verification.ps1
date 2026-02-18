# scripts/test_mx_verification.ps1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. .\scripts\padel_lib.ps1
Set-Base "http://localhost:8000"
$base = Get-Base
Write-Host "BASE=$base"

function Assert([bool]$cond, [string]$msg) {
  if (-not $cond) { throw "ASSERT FAIL: $msg" }
}

function HttpError($_) {
  $resp = $_.Exception.Response
  $code = if ($resp) { [int]$resp.StatusCode.value__ } else { -1 }
  $body = $_.ErrorDetails.Message
  return [PSCustomObject]@{ code = $code; body = $body }
}

function Expect-Http([scriptblock]$fn, [int]$codeExpected, [string]$contains = $null) {
  try {
    & $fn | Out-Null
    throw "Expected HTTP $codeExpected but got success"
  } catch {
    $e = HttpError $_
    Assert ($e.code -eq $codeExpected) "Expected HTTP $codeExpected, got $($e.code). body=$($e.body)"
    if ($contains) {
      Assert ($e.body -match [regex]::Escape($contains)) "Expected body to contain '$contains'. body=$($e.body)"
    }
    return $e
  }
}

# Genera phones únicos por corrida
$seed = Get-Random -Minimum 1000 -Maximum 8999
function Phone([int]$n) { return "+5730099{0:0000}" -f ($seed + $n) }

Write-Host "seed=$seed"

# --------------------------
# TEST A: usuario crudo NO elegible
# --------------------------
$t_raw = Get-Token (Phone 1)
$elig_raw = Invoke-RestMethod -Method Get -Uri "$base/me/play-eligibility" -Headers @{ Authorization="Bearer $t_raw" }
$elig_raw | ConvertTo-Json -Depth 10 | Write-Host
Assert (-not $elig_raw.can_create_match) "Raw user should NOT be able to create match"

# --------------------------
# TEST B: usuario con perfil SI elegible
# --------------------------
$u_ok = New-UserAndProfileUnique (Phone 2) "ok" "M" "5ta"
$elig_ok = Invoke-RestMethod -Method Get -Uri "$base/me/play-eligibility" -Headers @{ Authorization="Bearer $($u_ok.token)" }
$elig_ok | ConvertTo-Json -Depth 10 | Write-Host
Assert ($elig_ok.can_create_match) "Profiled user should be able to create match"

# --------------------------
# Crea 4 jugadores MX (2M + 2F)
# --------------------------
$u1 = New-UserAndProfileUnique (Phone 11) "p1" "M" "5ta"
$u2 = New-UserAndProfileUnique (Phone 12) "p2" "M" "6ta"
$u3 = New-UserAndProfileUnique (Phone 13) "p3" "F" "D"
$u4 = New-UserAndProfileUnique (Phone 14) "p4" "F" "B"

Write-Host "`nLadder states (debug):"
(Get-MyLadderStates $u1.token) | ConvertTo-Json -Depth 10 | Write-Host
(Get-MyLadderStates $u2.token) | ConvertTo-Json -Depth 10 | Write-Host
(Get-MyLadderStates $u3.token) | ConvertTo-Json -Depth 10 | Write-Host
(Get-MyLadderStates $u4.token) | ConvertTo-Json -Depth 10 | Write-Host

# Assert: todos tienen ladder MX
function HasMX($states) { return @($states | Where-Object { $_.ladder_code -eq "MX" }).Count -ge 1 }
Assert (HasMX (Get-MyLadderStates $u1.token)) "u1 missing MX ladder state"
Assert (HasMX (Get-MyLadderStates $u2.token)) "u2 missing MX ladder state"
Assert (HasMX (Get-MyLadderStates $u3.token)) "u3 missing MX ladder state"
Assert (HasMX (Get-MyLadderStates $u4.token)) "u4 missing MX ladder state"

$score = @{ sets = @(@{t1=6;t2=4}, @{t1=7;t2=5}) }
$playedAt = (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("yyyy-MM-ddTHH:mm:ssZ")

# --------------------------
# TEST C: crear match OK
# --------------------------
$m = New-MatchMX-Creator $u1.token $u1 $u2 $u3 $u4 $score $playedAt
$m | ConvertTo-Json -Depth 10 | Write-Host
$mid = $m.id
Assert ($m.status -eq "pending_confirm") "Expected pending_confirm at creation"
Write-Host "mid=$mid"

# Confirmations iniciales: creador confirmado, los demás pending
$conf0 = Get-MatchConfirmations -token $u1.token -matchId $mid
$conf0 | ConvertTo-Json -Depth 10 | Write-Host
Assert ($conf0.confirmed_count -eq 1) "At creation confirmed_count should be 1"

# --------------------------
# TEST D1: confirma 1 jugador del equipo 2 => DEBE quedar verified (regla nueva)
# --------------------------
$r_u2 = Confirm-Match -token $u2.token -matchId $mid -status confirmed -source "ps1"
$r_u2 | ConvertTo-Json -Depth 5 | Write-Host

$detail1 = Get-MatchDetail -token $u1.token -matchId $mid
$detail1 | ConvertTo-Json -Depth 10 | Write-Host
Assert ($detail1.status -eq "verified") "Expected status=verified when teams_confirmed reaches 2 (1 per team)"

# Confirm extra luego de verified => esperado 409 (si tu política es bloquear post-verified)
Expect-Http { Confirm-Match -token $u3.token -matchId $mid -status confirmed -source "ps1" } 409 "estado=verified" | Out-Null

# --------------------------
# TEST D2: escenario alterno: 2 confirmaciones del MISMO equipo NO verifican
# --------------------------
$m2 = New-MatchMX-Creator $u1.token $u1 $u2 $u3 $u4 $score $playedAt
$mid2 = $m2.id
Write-Host "`nmid2=$mid2"

# Confirma u3 (mismo equipo que u1)
$r_u3 = Confirm-Match -token $u3.token -matchId $mid2 -status confirmed -source "ps1"
$r_u3 | ConvertTo-Json -Depth 5 | Write-Host

$detail2a = Get-MatchDetail -token $u1.token -matchId $mid2
$detail2a | ConvertTo-Json -Depth 10 | Write-Host
Assert ($detail2a.status -eq "pending_confirm") "Should remain pending_confirm if only team 1 has confirmed"

# Ahora confirma u2 (equipo 2) => debe pasar a verified
$r_u2b = Confirm-Match -token $u2.token -matchId $mid2 -status confirmed -source "ps1"
$r_u2b | ConvertTo-Json -Depth 5 | Write-Host

$detail2b = Get-MatchDetail -token $u1.token -matchId $mid2
$detail2b | ConvertTo-Json -Depth 10 | Write-Host
Assert ($detail2b.status -eq "verified") "Expected verified after first confirmation from the other team"

# --------------------------
# TEST E: no-participant intenta confirmar => debe fallar (403 o 404 según tu implementación)
# --------------------------
$ux = New-UserAndProfileUnique (Phone 99) "x" "M" "5ta"
Expect-Http { Confirm-Match -token $ux.token -matchId $mid2 -status confirmed -source "ps1" } 403 | Out-Null

Write-Host "`n✅ ALL TESTS PASSED"
Write-Host "Si algo falla, mira: docker compose logs -f --tail 200 api"
