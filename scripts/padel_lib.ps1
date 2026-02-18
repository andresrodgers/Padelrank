# scripts/padel_lib.ps1
# Librería de funciones para testear la API desde PowerShell.
# NO resetea Docker. NO corre migraciones.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Base URL (puedes sobreescribirla llamando Set-Base)
$script:BASE = "http://localhost:8000"

function Set-Base([string]$base) {
  if (-not $base) { throw "base vacío" }
  $script:BASE = $base.TrimEnd("/")
}

function New-UserAndProfileUnique($phone, $baseAlias, $gender, $cat) {
  $suffix = $phone.Substring($phone.Length - 4)
  New-UserAndProfile $phone "${baseAlias}_$suffix" $gender $cat
}

function Get-Base() { return $script:BASE }

function Assert-JWT([string]$token) {
  if (-not $token) { throw "TOKEN VACÍO" }
  if ($token.Split(".").Count -ne 3) { throw "TOKEN NO ES JWT" }
}

function Invoke-Api {
  param(
    [Parameter(Mandatory=$true)][string]$Method,
    [Parameter(Mandatory=$true)][string]$Path,
    [hashtable]$Headers = $null,
    [object]$Body = $null
  )

  $uri = "$script:BASE$Path"

  $params = @{
    Method      = $Method
    Uri         = $uri
    ContentType = "application/json"
  }
  if ($Headers) { $params.Headers = $Headers }
  if ($null -ne $Body) {
    $params.Body = ($Body | ConvertTo-Json -Depth 20)
  }

  return Invoke-RestMethod @params
}

function Get-Token([string]$phone) {
  # /auth/otp/request -> devuelve dev_code en ENV=dev
  $r = Invoke-Api -Method Post -Path "/auth/otp/request" -Body @{ phone_e164 = $phone }
  $code = $r.dev_code
  if (-not $code) { throw "No llegó dev_code. Revisa ENV=dev" }

  $v = Invoke-Api -Method Post -Path "/auth/otp/verify" -Body @{ phone_e164 = $phone; code = $code }
  $token = ($v.access_token).Trim()
  Assert-JWT $token
  return $token
}

function Get-Me([string]$token) {
  return Invoke-RestMethod -Method Get -Uri "$script:BASE/me" -Headers @{ Authorization="Bearer $token" }
}

function Patch-MyProfile {
  param(
    [Parameter(Mandatory=$true)][string]$token,
    [Parameter(Mandatory=$true)][string]$alias,
    [Parameter(Mandatory=$true)][string]$gender,
    [Parameter(Mandatory=$true)][string]$primaryCategoryCode,
    [bool]$isPublic = $true
  )

  $null = Invoke-RestMethod -Method Patch -Uri "$script:BASE/me/profile" `
    -Headers @{ Authorization="Bearer $token" } `
    -ContentType "application/json" `
    -Body (@{
      alias = $alias
      gender = $gender
      primary_category_code = $primaryCategoryCode
      is_public = $isPublic
    } | ConvertTo-Json)
}

function Get-MyLadderStates([string]$token) {
  return Invoke-RestMethod -Method Get -Uri "$script:BASE/me/ladder-states" `
    -Headers @{ Authorization="Bearer $token" }
}

function New-UserAndProfile {
  param(
    [Parameter(Mandatory=$true)][string]$phone,
    [Parameter(Mandatory=$true)][string]$alias,
    [Parameter(Mandatory=$true)][string]$gender,
    [Parameter(Mandatory=$true)][string]$primaryCategoryCode
  )

  $token = Get-Token $phone
  Patch-MyProfile -token $token -alias $alias -gender $gender -primaryCategoryCode $primaryCategoryCode
  $me = Get-Me $token

  return [PSCustomObject]@{
    phone   = $phone
    alias   = $alias
    gender  = $gender
    token   = $token
    user_id = $me.id
  }
}

function New-MatchMX-Creator {
  param(
    [Parameter(Mandatory=$true)][string]$creatorToken,
    [Parameter(Mandatory=$true)]$u1,
    [Parameter(Mandatory=$true)]$u2,
    [Parameter(Mandatory=$true)]$u3,
    [Parameter(Mandatory=$true)]$u4,
    [Parameter(Mandatory=$true)]$scoreJson,
    [Parameter(Mandatory=$true)][string]$playedAtZ
  )

  $body = @{
    club_id = $null
    played_at = $playedAtZ
    participants = @(
      @{ user_id = [string]$u1.user_id; team_no = 1 },
      @{ user_id = [string]$u3.user_id; team_no = 1 },
      @{ user_id = [string]$u2.user_id; team_no = 2 },
      @{ user_id = [string]$u4.user_id; team_no = 2 }
    )
    score = @{
      score_json = $scoreJson
    }
  }

  return Invoke-RestMethod -Method Post -Uri "$script:BASE/matches" `
    -Headers @{ Authorization="Bearer $creatorToken" } `
    -ContentType "application/json" `
    -Body ($body | ConvertTo-Json -Depth 20)
}

function Confirm-Match {
  param(
    [Parameter(Mandatory=$true)][string]$token,
    [Parameter(Mandatory=$true)][string]$matchId,
    [ValidateSet("confirmed")][string]$status = "confirmed",
    [string]$source = "ps1"
  )

  $body = @{
    status = $status
    source = $source
  }

  return Invoke-RestMethod -Method Post -Uri "$script:BASE/matches/$matchId/confirm" `
    -Headers @{ Authorization="Bearer $token" } `
    -ContentType "application/json" `
    -Body ($body | ConvertTo-Json)
}

function Get-MatchDetail {
  param([string]$token, [string]$matchId)
  return Invoke-RestMethod -Method Get -Uri "$script:BASE/matches/$matchId/detail" `
    -Headers @{ Authorization="Bearer $token" }
}

function Get-MatchConfirmations {
  param([string]$token, [string]$matchId)
  return Invoke-RestMethod -Method Get -Uri "$script:BASE/matches/$matchId/confirmations" `
    -Headers @{ Authorization="Bearer $token" }
}

function Search-Users {
  param([string]$token, [string]$q)
  $qq = [uri]::EscapeDataString($q)
  return Invoke-RestMethod -Method Get -Uri "$script:BASE/users/search?q=$qq" `
    -Headers @{ Authorization="Bearer $token" }
}
