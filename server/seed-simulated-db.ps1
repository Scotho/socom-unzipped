<#
.SYNOPSIS
  Create (or inspect) the encrypted simulated.db that Horizon's Server.Database uses in SimulatedMode.

.DESCRIPTION
  In SimulatedMode Horizon keeps accounts/clans/per-app settings in memory and, when
  "SimulatedEncryptionKey" is set in config\db.config.json, persists them to config\simulated.db
  as AES-256-CBC(PKCS7) encrypted JSON with a 16-byte IV prefix, key = SHA256(passphrase).
  (See Server.Database\DbSimulated.cs.)

  There is no other way to set per-app settings in simulated mode: DbController.SetServerSettings()
  is a no-op there, so EnableEncryption / CreateAccountOnNotFound etc. for app id 10472 must be
  seeded into this file.

  This script writes a fresh simulated.db containing:
    * one test account (default: socom / socom) for the given app id
    * per-app settings for that app id

  Run it while the servers are STOPPED; Horizon reads the file once at start-up and rewrites it
  whenever an account is created/changed (so re-seeding overwrites anything the game created).

.PARAMETER AppId            Medius app id (default 10472 = SOCOM II NTSC)
.PARAMETER AccountName      Test account name (default socom)
.PARAMETER Password         Test account password (default socom). Stored as lowercase-hex SHA256, like Utils.ComputeSHA256.
.PARAMETER EnableEncryption Value for the per-app EnableEncryption setting (default False; Horizon's own titles run with False).
.PARAMETER CreateAccountOnNotFound  If True, MAS auto-creates an account on first login (default True).
.PARAMETER Show             Decrypt and print the existing simulated.db instead of writing one.
#>
[CmdletBinding()]
param(
    [int]$AppId = 10472,
    [string]$AccountName = 'socom',
    [string]$Password = 'socom',
    [ValidateSet('True', 'False')][string]$EnableEncryption = 'False',
    [ValidateSet('True', 'False')][string]$CreateAccountOnNotFound = 'True',
    [switch]$Show
)

$ErrorActionPreference = 'Stop'
$ConfigDir = Join-Path $PSScriptRoot 'config'
$DbCfgPath = Join-Path $ConfigDir 'db.config.json'
$DbPath    = Join-Path $ConfigDir 'simulated.db'

if (-not (Test-Path $DbCfgPath)) { throw "Missing $DbCfgPath" }
$dbCfg = Get-Content $DbCfgPath -Raw | ConvertFrom-Json
$passphrase = $dbCfg.SimulatedEncryptionKey
if ([string]::IsNullOrEmpty($passphrase)) { throw 'db.config.json has no SimulatedEncryptionKey; set one first (persistence is disabled without it).' }

function Get-Sha256Hex([string]$s) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return (($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($s)) | ForEach-Object { $_.ToString('x2') }) -join '') }
    finally { $sha.Dispose() }
}
function Get-AesKey([string]$s) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($s)) }   # 32 bytes = AES-256 key (DbSimulated.DeriveKey)
    finally { $sha.Dispose() }
}

if ($Show) {
    if (-not (Test-Path $DbPath)) { Write-Host "No simulated.db at $DbPath"; return }
    $raw = [IO.File]::ReadAllBytes($DbPath)
    $aes = [System.Security.Cryptography.Aes]::Create()
    try {
        $aes.Key = Get-AesKey $passphrase
        $aes.IV  = $raw[0..15]
        $dec = $aes.CreateDecryptor()
        $plain = $dec.TransformFinalBlock($raw, 16, $raw.Length - 16)
        [Text.Encoding]::UTF8.GetString($plain)
    } finally { $aes.Dispose() }
    return
}

# --- Build the DbSimulated document (property names must match Server.Database\DbSimulated.cs / Models\AccountDTO.cs)
$account = [ordered]@{
    AccountId               = 1
    AccountName             = $AccountName
    AccountPassword         = (Get-Sha256Hex $Password)
    Friends                 = @()
    Ignored                 = @()
    AccountWideStats        = @(0) * 100      # Constants.LADDERSTATSWIDE_MAXLEN
    AccountCustomWideStats  = @(0) * 1000
    ClanId                  = $null
    MediusStats             = ''
    MachineId               = ''
    IsBanned                = $false
    AppId                   = $AppId
    Metadata                = $null
    ResetPasswordOnNextLogin = $false
}
$appSettings = [ordered]@{
    EnableEncryption        = $EnableEncryption
    CreateAccountOnNotFound = $CreateAccountOnNotFound
    DisableAccountCreation  = 'False'
    EnableAccountWhitelist  = 'False'
    EnableMediusFileServices = 'False'
    TextFilterDefault       = ''
    TextFilterAccountName   = ''
}
$doc = [ordered]@{
    AccountIdCounter        = 2
    ClanIdCounter           = 1
    ClanMessageIdCounter    = 1
    ClanInvitationIdCounter = 1
    Accounts                = @($account)
    Clans                   = @()
    AppSettings             = [ordered]@{ "$AppId" = $appSettings }
}
$json = $doc | ConvertTo-Json -Depth 6
$plainBytes = [Text.Encoding]::UTF8.GetBytes($json)

# --- Encrypt exactly like DbSimulated.Save: IV || AES-CBC-PKCS7(json)
$aes = [System.Security.Cryptography.Aes]::Create()
try {
    $aes.Key = Get-AesKey $passphrase
    $aes.GenerateIV()
    $enc = $aes.CreateEncryptor()
    $cipher = $enc.TransformFinalBlock($plainBytes, 0, $plainBytes.Length)
    $out = New-Object byte[] ($aes.IV.Length + $cipher.Length)
    [Array]::Copy($aes.IV, 0, $out, 0, $aes.IV.Length)
    [Array]::Copy($cipher, 0, $out, $aes.IV.Length, $cipher.Length)
    [IO.File]::WriteAllBytes($DbPath, $out)
} finally { $aes.Dispose() }

Write-Host "Wrote $DbPath ($($out.Length) bytes)"
Write-Host "  account  : $AccountName / $Password  (app id $AppId, sha256 stored)"
Write-Host "  settings : EnableEncryption=$EnableEncryption CreateAccountOnNotFound=$CreateAccountOnNotFound"
Write-Host "Verify with: .\seed-simulated-db.ps1 -Show"
