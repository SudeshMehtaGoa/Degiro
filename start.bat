@echo off
echo Starting DEGIRO Dashboard...

REM Generate Windows certificate bundle if missing (needed for yfinance SSL on Windows)
if not exist "%~dp0win_certs.pem" (
    echo Generating Windows certificate bundle...
    powershell -NoProfile -Command "$certs=Get-ChildItem -Path Cert:\LocalMachine\Root;$p='';foreach($c in $certs){$p+='-----BEGIN CERTIFICATE-----'+\"`n\"+[Convert]::ToBase64String($c.RawData,[System.Base64FormattingOptions]::InsertLineBreaks)+\"`n-----END CERTIFICATE-----`n\"};Set-Content -Path '%~dp0win_certs.pem' -Value $p -Encoding ASCII"
    echo Certificate bundle created.
)

python "%~dp0server.py"
pause
