# scripts/test_ladders_verification.ps1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Evita caracteres raros en consola (checkmarks, acentos)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

. "$PSScriptRoot\padel_lib.ps1"

Set-Base "http://localhost:8000"
$BASE = Get-Base

Write-Host "BASE=$BASE"
$seed = Get-Random -Minimum 1000 -Maximum 9999
Write-Host "seed=$seed"

function New-TestUser([string]$phone, [string]$alias, [string]$gender, [string]$category) {
  $out = @(New-UserAndProfileUnique $phone $alias $gender $category)

  # Si el helper devolvió estados de elegibilidad, validarlos (registro/profile gating)
  $elig = @($out | Where-Object {
    $_ -and ($_.PSObject.Properties.Name -contains "can_play") -and ($_.PSObject.Properties.Name -contains "missing")
  })

  if ($elig.Count -ge 2) {
    Assert (-not $elig[0].can_play) "Expected pre-profile can_play=false"
    $missingTxt = (($elig[0].missing -join ",") -as [string])
    Assert ($missingTxt -match "usuario") "Expected 'usuario' missing pre-profile. missing=$missingTxt"
    # tolerante a encoding/acentos
    Assert ($missingTxt -match "gen|gé|gÃ") "Expected gender missing pre-profile. missing=$missingTxt"

    Assert ($elig[-1].can_play) "Expected post-profile can_play=true"
  }

  $u = $out | Select-Object -Last 1

  if (-not $u) {
    throw "New-UserAndProfileUnique devolvió <null>."
  }

  # Normaliza: si no existe .id pero existe .user_id, crea .id = .user_id
  $props = $u.PSObject.Properties.Name
  if (-not ($props -contains "id")) {
    if ($props -contains "user_id") {
      $u | Add-Member -NotePropertyName "id" -NotePropertyValue $u.user_id -Force
    } else {
      $keys = ($props -join ",")
      throw "New-UserAndProfileUnique no devolvió .id ni .user_id. Keys=$keys"
    }
  }

  # Validación mínima de token
  if (-not ($u.PSObject.Properties.Name -contains "token")) {
    $keys = ($u.PSObject.Properties.Name -join ",")
    throw "New-UserAndProfileUnique no devolvió .token. Keys=$keys"
  }

  return $u
}

function Assert([bool]$cond, [string]$msg) {
  if (-not $cond) { throw $msg }
}

function TryConfirm([string]$token, [string]$matchId, [string]$label) {
  try {
    $r = Confirm-Match -token $token -matchId $matchId -status confirmed -source "ps1"
    return @{ ok=$true; body=$r; code=200; err=$null; label=$label }
  } catch {
    $code = $null
    try { $code = [int]$_.Exception.Response.StatusCode } catch {}
    $errMsg = $null
    try { $errMsg = $_.ErrorDetails.Message } catch {}
    if (-not $errMsg) { $errMsg = $_.Exception.Message }
    return @{ ok=$false; body=$null; code=$code; err=$errMsg; label=$label }
  }
}

function New-MatchGeneric(
  [string]$token,
  [string]$ladderCode,
  $u1, $u2, $u3, $u4,
  $score,
  [string]$playedAt
) {
  $body = @{
    ladder_code = $ladderCode
    played_at   = $playedAt
    club_id     = $null
    participants = @(
      @{ user_id = [string]$u1.id; team_no = 1 },
      @{ user_id = [string]$u3.id; team_no = 1 },
      @{ user_id = [string]$u2.id; team_no = 2 },
      @{ user_id = [string]$u4.id; team_no = 2 }
    )
    score = @{
      score_json = $score
    }
  }

  return Invoke-RestMethod -Method Post -Uri "$BASE/matches" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body ($body | ConvertTo-Json -Depth 10)
}

function Get-TeamMap($token, $matchId) {
  $c = Get-MatchConfirmations -token $token -matchId $matchId
  $map = @{}
  foreach ($row in $c.rows) { $map[$row.user_id] = $row.team_no }
  return @{ raw=$c; teamMap=$map }
}

function Run-Ladder([string]$title, [string]$ladderCode, $u1, $u2, $u3, $u4) {
  Write-Host ""
  Write-Host "===================="
  Write-Host "TEST LADDER: $title ($ladderCode)"
  Write-Host "===================="

  $usersById = @{}
  foreach ($u in @($u1,$u2,$u3,$u4)) { $usersById[[string]$u.id] = $u }

  $score = @{ sets = @(@{t1=6;t2=4}, @{t1=7;t2=5}) }
  $playedAt = (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("yyyy-MM-ddTHH:mm:ssZ")

  # MATCH A: 1 por equipo => VERIFIED
  $mA = New-MatchGeneric $u1.token $ladderCode $u1 $u2 $u3 $u4 $score $playedAt
  Write-Host "matchA id=$($mA.id) status=$($mA.status) ladder=$($mA.ladder_code)"
  Assert ($mA.status -eq "pending_confirm") "Expected matchA pending_confirm"
  Assert ($mA.confirmed_count -eq 1) "Expected matchA confirmed_count=1 at creation"

  $tmA = Get-TeamMap $u1.token $mA.id
  $creatorTeam = $tmA.teamMap[[string]$u1.id]
  Assert ($creatorTeam -in 1,2) "Expected creatorTeam to be 1 or 2"

  $otherTeamUserId = ($tmA.raw.rows | Where-Object { $_.team_no -ne $creatorTeam } | Select-Object -First 1).user_id
  $other = $usersById[$otherTeamUserId]

  $c1 = TryConfirm $other.token $mA.id "A other-team confirm"
  Assert ($c1.ok) "Expected other-team confirm OK on matchA. err=$($c1.err)"

  $dA = Get-MatchDetail -token $u1.token -matchId $mA.id
  Assert ($dA.status -eq "verified") "Expected matchA VERIFIED after 1 per team"

  $dupA = TryConfirm $other.token $mA.id "A duplicate after verified"
  Assert (-not $dupA.ok) "Expected duplicate confirm to fail AFTER verified (matchA)"

  Write-Host "matchA VERIFIED OK"

  # MATCH B: 2 del mismo equipo => sigue PENDING
  # y duplicate mientras pending puede ser 409 o 200 idempotente (sin cambios)
  $mB = New-MatchGeneric $u1.token $ladderCode $u1 $u2 $u3 $u4 $score $playedAt
  Write-Host "matchB id=$($mB.id) status=$($mB.status) ladder=$($mB.ladder_code)"
  Assert ($mB.status -eq "pending_confirm") "Expected matchB pending_confirm"

  $tmB = Get-TeamMap $u1.token $mB.id
  $creatorTeamB = $tmB.teamMap[[string]$u1.id]

  $teammateId = ($tmB.raw.rows | Where-Object { $_.team_no -eq $creatorTeamB -and $_.user_id -ne [string]$u1.id } | Select-Object -First 1).user_id
  $teammate = $usersById[$teammateId]

  $c2 = TryConfirm $teammate.token $mB.id "B teammate confirm"
  Assert ($c2.ok) "Expected teammate confirm OK on matchB. err=$($c2.err)"
  Assert ($c2.body.teams_confirmed -eq 1) "Expected teams_confirmed=1 after same-team confirm (matchB)"

  $dB1 = Get-MatchDetail -token $u1.token -matchId $mB.id
  Assert ($dB1.status -eq "pending_confirm") "Expected matchB still pending_confirm after same-team confirm"

  # Duplicate confirm while pending: accept either
  $dupB = TryConfirm $teammate.token $mB.id "B duplicate while pending"
  if ($dupB.ok) {
    Assert ($dupB.body.confirmed_count -eq $c2.body.confirmed_count) "Duplicate OK should NOT change confirmed_count (matchB)"
    Assert ($dupB.body.teams_confirmed -eq $c2.body.teams_confirmed) "Duplicate OK should NOT change teams_confirmed (matchB)"
    Write-Host "matchB duplicate while pending: idempotent OK (no change)"
  } else {
    Assert ($dupB.code -eq 409) "Expected duplicate to be 409 if not idempotent (matchB). got=$($dupB.code) err=$($dupB.err)"
    Write-Host "matchB duplicate while pending: 409 OK"
  }

  # Ahora confirma alguien del otro equipo => VERIFIED
  $otherTeamUserIdB = ($tmB.raw.rows | Where-Object { $_.team_no -ne $creatorTeamB } | Select-Object -First 1).user_id
  $otherB = $usersById[$otherTeamUserIdB]

  $c3 = TryConfirm $otherB.token $mB.id "B other-team confirm"
  Assert ($c3.ok) "Expected other-team confirm OK on matchB. err=$($c3.err)"

  $dB2 = Get-MatchDetail -token $u1.token -matchId $mB.id
  Assert ($dB2.status -eq "verified") "Expected matchB VERIFIED after 1 per team"

  # Post-verified confirm from remaining user should fail
  $remainingId = ($tmB.raw.rows | Where-Object { $_.user_id -ne [string]$u1.id -and $_.user_id -ne $teammateId -and $_.user_id -ne $otherTeamUserIdB } | Select-Object -First 1).user_id
  $remaining = $usersById[$remainingId]
  $post = TryConfirm $remaining.token $mB.id "B post-verified confirm"
  Assert (-not $post.ok) "Expected confirm to fail after verified (matchB)"

  Write-Host "matchB VERIFIED OK"

  # Unauthorized confirm: user que NO es participante => 403
$unauthI = switch ($ladderCode) {
  "MX" { 901 }
  "HM" { 902 }
  "WM" { 903 }
  Default { 999 }
}

$uX = New-TestUser (Phone $unauthI) ("x_${ladderCode}_$seed") `
  $(if ($ladderCode -eq "WM") {"F"} else {"M"}) `
  $(if ($ladderCode -eq "WM") {"D"} else {"5ta"})

$unauth = TryConfirm $uX.token $mA.id "Unauthorized confirm"
Assert (-not $unauth.ok) "Expected unauthorized confirm to fail"
Assert ($unauth.code -eq 403) "Expected unauthorized confirm 403. got=$($unauth.code) err=$($unauth.err)"

Write-Host "unauthorized confirm OK"
}


function Phone([int]$i) {
  return "+57" + ("300{0}{1:D3}" -f $seed, $i)
}

# MX: 2M + 2F
$mx1 = New-TestUser (Phone 1) "mx1_$seed" "M" "5ta"
$mx2 = New-TestUser (Phone 2) "mx2_$seed" "M" "6ta"
$mx3 = New-TestUser (Phone 3) "mx3_$seed" "F" "D"
$mx4 = New-TestUser (Phone 4) "mx4_$seed" "F" "B"

Run-Ladder "MX" "MX" $mx1 $mx2 $mx3 $mx4

# HM: 4M
$hm1 = New-TestUser (Phone 5) "hm1_$seed" "M" "5ta"
$hm2 = New-TestUser (Phone 6) "hm2_$seed" "M" "5ta"
$hm3 = New-TestUser (Phone 7) "hm3_$seed" "M" "6ta"
$hm4 = New-TestUser (Phone 8) "hm4_$seed" "M" "6ta"

Run-Ladder "HM" "HM" $hm1 $hm2 $hm3 $hm4

# WM: 4F
$wm1 = New-TestUser (Phone 11) "wm1_$seed" "F" "D"
$wm2 = New-TestUser (Phone 12) "wm2_$seed" "F" "D"
$wm3 = New-TestUser (Phone 13) "wm3_$seed" "F" "B"
$wm4 = New-TestUser (Phone 14) "wm4_$seed" "F" "B"

Run-Ladder "WM" "WM" $wm1 $wm2 $wm3 $wm4

Write-Host ""
Write-Host "ALL TESTS PASSED"
