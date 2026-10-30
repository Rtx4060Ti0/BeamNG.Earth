$ErrorActionPreference = 'Stop'
$earthEntry = Join-Path $PSScriptRoot 'start.py'
Start-Process -FilePath 'pyw.exe' -ArgumentList @('-3.13', ('"' + $earthEntry + '"'), '--attach') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
