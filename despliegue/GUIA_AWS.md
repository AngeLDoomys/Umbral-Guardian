# Publicar la API central en AWS Academy (Learner Lab)

Arquitectura: **EC2** (Ubuntu, API Flask con gunicorn + Caddy con HTTPS) y
**RDS MySQL** (base central, sin acceso desde internet). El nodo de la portería
habla solo con la API por `https://<subdominio>.duckdns.org`.

```
PC portería ──HTTPS──> EC2 (Caddy :443 → gunicorn 127.0.0.1:5000) ──3306──> RDS MySQL
                       grupo ug-api                                         grupo ug-rds
```

Tiempo estimado: 45 a 60 minutos (RDS tarda ~10 minutos en crearse).

---

## 0. En tu PC, antes de empezar

1. WampServer encendido (ícono verde).
2. En PowerShell, en la carpeta del proyecto:
   ```powershell
   powershell -ExecutionPolicy Bypass -File despliegue\preparar_paquete.ps1
   ```
   Crea `despliegue\paquete\` con el código, el instalador, los dos secretos y la
   copia de la base. **Contiene secretos: no lo compartas ni lo subas a GitHub.**

## 1. Abrir el Learner Lab

1. AWS Academy → tu curso → **Modules → Launch AWS Academy Learner Lab**.
2. **Start Lab** y espera el círculo **verde** junto a «AWS». Haz clic en **AWS**.
3. Arriba a la derecha, la región debe ser **N. Virginia (us-east-1)**.
4. En el Learner Lab: **AWS Details → Download PEM**. Guarda `labsuser.pem` en Descargas.

> La sesión dura 4 horas. Al terminar, AWS apaga el servidor; al volver a
> iniciarla cambia su IP pública. El instalador deja el subdominio
> actualizándose solo, así que no hay que tocar nada.

## 2. Subdominio gratuito (DuckDNS)

1. Entra a <https://www.duckdns.org> con Google o GitHub.
2. Crea un subdominio, por ejemplo `umbralguardian-mt` (queda
   `umbralguardian-mt.duckdns.org`).
3. Copia el **token** que aparece arriba en la página.

## 3. Grupos de seguridad (firewall)

Consola → **EC2 → Security Groups → Create security group** (VPC por defecto):

| Nombre | Regla de entrada | Origen |
|---|---|---|
| `ug-api` | SSH (22) | **My IP** |
| | HTTP (80) | Anywhere-IPv4 (lo usa Let's Encrypt) |
| | HTTPS (443) | Anywhere-IPv4 |
| `ug-rds` | MySQL/Aurora (3306) | el grupo **`ug-api`** (no una IP) |

Así la base solo acepta conexiones desde el servidor de la API.

## 4. Base de datos RDS

Consola → **RDS → Create database**:

- **Standard create** → **MySQL** → versión **8.4.x**.
- Templates: **Free tier** (si no aparece, **Dev/Test**).
- DB instance identifier: `umbral-central`.
- Master username: `admin` · **Self managed** · escribe una contraseña y **anótala**.
- Instance class: **db.t3.micro** (o db.t4g.micro).
- Storage: 20 GB, **desmarca** «Enable storage autoscaling».
- Connectivity: VPC por defecto · **Public access: No** ·
  VPC security group: **Choose existing → `ug-rds`** (quita `default`).
- **Monitoring: desmarca «Enhanced Monitoring»** — en el Learner Lab, si queda
  marcado, la creación falla por permisos.
- Additional configuration: deja **Initial database name** vacío (la copia la crea).
- **Create database**. Cuando el estado sea *Available*, copia el **Endpoint**
  (pestaña *Connectivity & security*).

## 5. Servidor EC2

Consola → **EC2 → Launch instance**:

- Name: `umbral-api`.
- AMI: **Ubuntu Server 24.04 LTS**.
- Instance type: **t3.small** (2 GB de memoria: el registro desde el celular procesa
  las fotos con OpenCV; en t3.micro puede quedarse sin memoria).
- Key pair: **vockey**.
- Network settings → **Select existing security group → `ug-api`**.
- Storage: 8 GB está bien.
- **Launch instance**. Copia su **Public IPv4 address**.

## 6. Subir el paquete

En PowerShell, en la carpeta del proyecto (cambia `IP_PUBLICA`):

```powershell
$pem = "$env:USERPROFILE\Downloads\labsuser.pem"
icacls $pem /inheritance:r /grant:r "$($env:USERNAME):R"
scp -i $pem -r despliegue\paquete ubuntu@IP_PUBLICA:~/
ssh -i $pem ubuntu@IP_PUBLICA
```

La primera vez pregunta si confías en el servidor: escribe `yes`.

## 7. Instalar (dentro del servidor, por SSH)

```bash
cd ~/paquete
sudo bash instalar_servidor.sh umbralguardian-mt TU_TOKEN_DUCKDNS
```

La primera vez crea `/etc/umbral/api.env` y avisa que hay que editarlo:

```bash
sudo nano /etc/umbral/api.env
```

Cambia `UG_CENTRAL_HOST` por el **Endpoint** de RDS y `UG_CENTRAL_PASSWORD` por
la contraseña maestra. Guarda con `Ctrl+O`, `Enter`, `Ctrl+X`.

Copia la base a RDS (pide la contraseña maestra):

```bash
mysql -h ENDPOINT_DE_RDS -u admin -p < umbral_central.sql
```

Vuelve a ejecutar el instalador; ahora debe terminar con «API local OK»:

```bash
sudo bash instalar_servidor.sh umbralguardian-mt TU_TOKEN_DUCKDNS
```

Borra los secretos que subiste (el instalador ya los copió a su lugar):

```bash
rm -rf ~/paquete
```

## 8. Probar

En el navegador de tu PC: `https://umbralguardian-mt.duckdns.org/api/salud`
→ debe mostrar `{"ok": true}` con candado (HTTPS).

## 9. Conectar el nodo de la portería

En `nodo.json` del programa cambia solo la dirección (la clave del nodo es la misma):

```json
{
  "api_url": "https://umbralguardian-mt.duckdns.org",
  "clave_nodo": "(la que ya tiene)"
}
```

Abre el programa e inicia sesión. Borra también `despliegue\paquete\` de tu PC.

## 10. Probar el registro desde el celular

1. En el programa: **📱 Registro móvil** → «Residente nuevo», unidad, **Generar QR**.
   (La primera vez el equipo publica su clave pública en la nube.)
2. Escanea el QR con tu celular **usando datos móviles** (no el WiFi de la casa):
   así compruebas que funciona desde cualquier lugar.
3. Completa datos, consentimiento y las 5 fotos. Cada foto se revisa al instante.
4. En el programa, la solicitud aparece en la bandeja (se revisa sola cada minuto,
   o con **🔄 Revisar nuevos**). **✔ Aprobar** la registra con su rostro y vehículo.

> El enlace del QR usa `api_url` de `nodo.json`: con la API en tu PC
> (`http://127.0.0.1:5000`) el QR solo funciona en ese mismo PC.

---

## El día de la feria

1. **30 minutos antes**: AWS Academy → Learner Lab → **Start Lab**.
2. En la consola revisa que **EC2 `umbral-api`** esté *Running* y **RDS
   `umbral-central`** *Available*. Si alguno está detenido: *Instance state → Start*
   (EC2) o *Actions → Start* (RDS; tarda unos minutos).
3. Espera 2 a 3 minutos (DuckDNS se actualiza al arrancar) y abre
   `https://<subdominio>.duckdns.org/api/salud`.
4. Si la sesión de 4 horas está por vencer, en el Learner Lab presiona
   **Start Lab** otra vez para renovarla.

**Respaldo si falla internet en la feria:** el programa inicia sesión sin
conexión con la última sincronización (hasta 7 días), así que el Monitor,
residentes y patentes siguen funcionando. La gestión de cuentas, el panel del
proveedor y el registro desde el celular necesitan la nube.

## Si algo falla

| Síntoma | Revisar |
|---|---|
| `ssh` dice *UNPROTECTED PRIVATE KEY* | volver a correr el `icacls` del paso 6 |
| `ssh` no conecta | tu IP cambió: edita la regla SSH de `ug-api` con **My IP** |
| «API local» no responde | `sudo journalctl -u umbral-api -n 50` y los datos de `/etc/umbral/api.env` |
| `mysql` no conecta a RDS | grupo `ug-rds` con origen `ug-api`; RDS *Available* |
| No hay candado / HTTPS falla | puertos 80 y 443 abiertos en `ug-api`; `cat /var/log/duckdns.log` debe decir `OK`; `sudo journalctl -u caddy -n 30` |
| El subdominio apunta a una IP vieja | `sudo systemctl start duckdns.service` |

## Costo

Se descuenta del crédito del Learner Lab (normalmente US$50 a 100) solo mientras
la sesión está activa: t3.small ≈ US$0,02/h y db.t3.micro ≈ US$0,02/h, unos
US$0,04 por hora de sesión. El saldo se ve en el panel del Learner Lab.
