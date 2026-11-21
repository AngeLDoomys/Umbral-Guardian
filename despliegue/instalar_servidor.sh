#!/usr/bin/env bash
# =============================================================================
# Instala la API central de Umbral Guardian en un servidor Ubuntu 24.04 (EC2).
#
#   sudo bash instalar_servidor.sh <subdominio-duckdns> <token-duckdns>
#   ej.: sudo bash instalar_servidor.sh umbralguardian 1a2b3c4d-....
#
# Deja funcionando:
#   - umbral-api.service : la API Flask con gunicorn, solo en 127.0.0.1:5000
#   - caddy              : HTTPS automático (Let's Encrypt) en https://<sub>.duckdns.org
#   - duckdns.timer      : actualiza la IP del subdominio al arrancar y cada 5 min
#                          (en AWS Academy la IP pública cambia en cada sesión)
# Se puede volver a ejecutar: actualiza el código y reinicia los servicios.
# =============================================================================
set -euo pipefail

SUB="${1:?Falta el subdominio de DuckDNS (sin .duckdns.org)}"
TOKEN="${2:?Falta el token de DuckDNS}"
DOMINIO="${SUB}.duckdns.org"
DIR=/opt/umbral-api
ORIGEN="$(cd "$(dirname "$0")" && pwd)"

echo "== 1/6 Paquetes del sistema"
# EC2 viene en UTC: pasadas las 21:00 de Chile la API creía que ya era mañana
# (la fecha de visita mínima del formulario salía un día adelantada)
timedatectl set-timezone America/Santiago
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip mysql-client unzip curl \
    debian-keyring debian-archive-keyring apt-transport-https gnupg
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy
fi

echo "== 2/6 Código de la API en $DIR"
id -u umbral >/dev/null 2>&1 || useradd --system --home "$DIR" --shell /usr/sbin/nologin umbral
mkdir -p "$DIR"
# el zip se arma en Windows: unzip avisa por las barras invertidas (código 1 =
# advertencia, los archivos quedan bien); solo un código mayor es un error
unzip -oq "$ORIGEN/umbral_api.zip" -d "$DIR" || [ $? -eq 1 ]
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install -q --upgrade pip
"$DIR/venv/bin/pip" install -q -r "$DIR/despliegue/requirements_servidor.txt"

echo "== 3/6 Secretos (clave de sesión y clave privada de licencias)"
for f in secreto.key licencia_privada.pem; do
  if [ -f "$ORIGEN/$f" ]; then
    install -m 600 -o umbral -g umbral "$ORIGEN/$f" "$DIR/servidor/$f"
  fi
  [ -f "$DIR/servidor/$f" ] || { echo "ERROR: falta $f (cópielo junto a este script)"; exit 1; }
done
chown -R umbral:umbral "$DIR"

echo "== 4/6 Configuración /etc/umbral/api.env"
mkdir -p /etc/umbral
if [ ! -f /etc/umbral/api.env ]; then
  install -m 600 "$DIR/despliegue/api.env.ejemplo" /etc/umbral/api.env
  echo "   -> EDITE /etc/umbral/api.env con los datos de RDS y vuelva a ejecutar este script"
fi
chmod 600 /etc/umbral/api.env

echo "== 5/6 Servicios"
cat > /etc/systemd/system/umbral-api.service <<EOF
[Unit]
Description=Umbral Guardian - API central
After=network-online.target
Wants=network-online.target

[Service]
User=umbral
WorkingDirectory=$DIR
EnvironmentFile=/etc/umbral/api.env
ExecStart=$DIR/venv/bin/gunicorn --workers 2 --bind 127.0.0.1:5000 --access-logfile - servidor.api:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/umbral/duckdns.sh <<EOF
#!/bin/sh
# ip vacía: DuckDNS usa la IP pública desde la que llega la petición
curl -fsS "https://www.duckdns.org/update?domains=${SUB}&token=${TOKEN}&ip=" -o /var/log/duckdns.log
EOF
chmod 700 /etc/umbral/duckdns.sh

cat > /etc/systemd/system/duckdns.service <<EOF
[Unit]
Description=Actualiza la IP de ${DOMINIO}
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/etc/umbral/duckdns.sh
EOF

cat > /etc/systemd/system/duckdns.timer <<EOF
[Unit]
Description=Actualiza DuckDNS al arrancar y cada 5 minutos

[Timer]
OnBootSec=15s
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

cat > /etc/caddy/Caddyfile <<EOF
${DOMINIO} {
    reverse_proxy 127.0.0.1:5000
    encode gzip
}
EOF

systemctl daemon-reload
systemctl enable --now duckdns.timer
systemctl start duckdns.service
systemctl enable umbral-api.service
systemctl restart umbral-api.service
systemctl enable caddy
systemctl restart caddy

echo "== 6/6 Verificación"
sleep 3
echo -n "DuckDNS: "; cat /var/log/duckdns.log; echo
if curl -fsS http://127.0.0.1:5000/api/salud; then
  echo "   API local OK"
else
  echo "   La API no responde: revise 'journalctl -u umbral-api -n 50' y /etc/umbral/api.env"
fi
echo
echo "Listo. Pruebe desde su PC:  https://${DOMINIO}/api/salud"
echo "(el certificado HTTPS puede tardar un minuto la primera vez)"
