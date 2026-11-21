# =============================================================================
# Arma despliegue\paquete\ con todo lo que se sube al servidor de AWS:
#   umbral_api.zip        código de la API (servidor\ + core\licencia.py, security.py)
#   instalar_servidor.sh  instalador (con finales de línea de Linux)
#   secreto.key, licencia_privada.pem   SECRETOS: no los comparta ni los suba a GitHub
#   umbral_central.sql    copia de la base central actual (WampServer encendido)
#
# Uso (PowerShell, en la carpeta del proyecto):
#   powershell -ExecutionPolicy Bypass -File despliegue\preparar_paquete.ps1
# =============================================================================
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$salida = Join-Path $PSScriptRoot "paquete"
$tmp = Join-Path $env:TEMP "umbral_api_staging"

Remove-Item -Recurse -Force $salida, $tmp -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $salida, "$tmp\servidor", "$tmp\core", "$tmp\despliegue", "$tmp\modelos" | Out-Null

# código: solo lo que importa la API (incluido el registro desde el celular)
Copy-Item "$raiz\servidor\*.py" "$tmp\servidor\"
Copy-Item "$raiz\config.py" "$tmp\"
foreach ($m in "__init__", "licencia", "security", "cifrado", "textos", "face_utils", "plate_utils") {
    Copy-Item "$raiz\core\$m.py" "$tmp\core\"
}
# modelos de rostro (revisión de fotos y vector SFace en la nube)
Copy-Item "$raiz\modelos\face_detection_yunet_2023mar.onnx", "$raiz\modelos\face_recognition_sface_2021dec.onnx" "$tmp\modelos\"
Copy-Item "$raiz\despliegue\requirements_servidor.txt", "$raiz\despliegue\api.env.ejemplo" "$tmp\despliegue\"
Compress-Archive -Path "$tmp\*" -DestinationPath "$salida\umbral_api.zip"
Remove-Item -Recurse -Force $tmp

# instalador con finales de línea LF (bash no acepta CRLF)
$sh = (Get-Content "$raiz\despliegue\instalar_servidor.sh" -Raw) -replace "`r`n", "`n"
[IO.File]::WriteAllText("$salida\instalar_servidor.sh", $sh, (New-Object Text.UTF8Encoding $false))

# secretos: la misma clave privada que firmó las licencias de los nodos existentes
Copy-Item "$raiz\servidor\secreto.key", "$raiz\servidor\licencia_privada.pem" $salida

# copia de la base central (cuentas, condominios, planes, pagos y nodos)
$dump = Get-ChildItem "C:\wamp64\bin\mysql\*\bin\mysqldump.exe" -ErrorAction SilentlyContinue |
        Select-Object -Last 1
if (-not $dump) { throw "No se encontró mysqldump de WampServer en C:\wamp64\bin\mysql" }
& $dump.FullName -u root --databases umbral_central --single-transaction --routines `
    --set-gtid-purged=OFF --no-tablespaces --default-character-set=utf8mb4 `
    --result-file="$salida\umbral_central.sql"
if ($LASTEXITCODE -ne 0) { throw "mysqldump falló: ¿está WampServer encendido (ícono verde)?" }

Write-Host ""
Write-Host "Paquete listo en $salida" -ForegroundColor Green
Get-ChildItem $salida | Format-Table Name, Length -AutoSize
Write-Host "ATENCION: contiene secretos. Bórrelo después de subirlo al servidor." -ForegroundColor Yellow
