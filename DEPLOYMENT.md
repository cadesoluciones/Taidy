# Despliegue de NEXUS-BDB

Registro del despliegue real y del proceso a seguir para futuras
actualizaciones. Si la IP o el servidor cambian, actualiza la sección
"Servidor actual" — el resto del documento no depende de la IP concreta.

## Servidor actual

| | |
|---|---|
| IP | `172.16.12.41` (red interna) |
| SO | Rocky Linux 9.8 (Blue Onyx) |
| Acceso | SSH como `root`, clave dedicada `nexus-bdb-deploy` (ver "Acceso SSH" abajo) |
| Ruta del despliegue | `/opt/nexus-bdb` (clon git de la rama `migration/streamlit-to-react`) |
| Puerto | `8000` (abierto en firewalld, zona `public`) |
| URL | `http://172.16.12.41:8000` |

## Actualizar la aplicación (lo normal, día a día)

```bash
ssh root@172.16.12.41
cd /opt/nexus-bdb
git pull
task docker:up
```

`task docker:up` ya se encarga de: comprobar que `config.json`/`tables.yaml`/
`factorial_tables.yaml`/`.env`/`exports` existen (los restaura si no, ver
`scripts/docker-bootstrap.sh`), reconstruir la imagen (Docker cachea las
capas que no cambiaron, así que suele tardar segundos si solo cambió código
Python/TS) y recrear el contenedor. El volumen `taidy_data` (usuarios,
programaciones, flujos, historial, auditoría) persiste entre actualizaciones
— no se pierde nada.

Para ver logs en vivo: `task docker:logs`. Para parar: `task docker:down`.

## Qué se instaló en el servidor (para uno nuevo)

Si el despliegue se mueve a otra máquina Linux desde cero, esto es lo que
hay que preparar (todo como `root` o con `sudo`):

### 1. Paquetes base

```bash
dnf -y install dnf-plugins-core git
dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

`systemctl enable --now docker` es la pieza que hace que Docker (y por tanto
el contenedor, que tiene `restart: unless-stopped` en `docker-compose.yml`)
**arranque solo cuando se enciende la máquina** — verificado con un reinicio
real de la VM: Docker y el contenedor volvieron a estar arriba sin
intervención manual.

Instalar `task` (opcional, pero recomendado para que los comandos de este
documento funcionen tal cual):

```bash
sh -c "$(curl -ssL https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin
```

### 2. Firewall

El repo es **público** en GitHub, así que no hace falta ninguna clave para
clonarlo. Solo hay que abrir el puerto de la app:

```bash
firewall-cmd --permanent --zone=public --add-port=8000/tcp
firewall-cmd --reload
```

(Si el firewall usa otra zona, `firewall-cmd --get-default-zone` lo dice.)

### 3. SELinux

Si el host tiene SELinux en `Enforcing` (compruébalo con `getenforce`; es el
caso por defecto en RHEL/Rocky/CentOS), el contenedor no podrá leer/escribir
los archivos montados por bind-mount (`config.json`, `tables.yaml`,
`factorial_tables.yaml`, `exports/`) aunque los permisos Unix sean
correctos. `docker-compose.yml` ya lleva la etiqueta `:z` en esos volúmenes
para relabelarlos automáticamente -- no hace falta tocar nada más. (Ese
`:z` no afecta a Windows/macOS ni a Linux sin SELinux, así que no hay que
quitarlo si el destino cambia de sistema.)

### 4. Clonar y arrancar

```bash
mkdir -p /opt/nexus-bdb
git clone --branch migration/streamlit-to-react https://github.com/cadesoluciones/Taidy.git /opt/nexus-bdb
cd /opt/nexus-bdb
```

Falta el `.env` con los secretos reales (`BC_CLIENT_SECRET`,
`FACTORIAL_API_KEY`, `FABRIC_CLIENT_SECRET`, ...) -- **no está en git**.
Cópialo desde un entorno que ya lo tenga configurado:

```bash
# Desde tu máquina, con el .env real en el directorio del proyecto:
scp .env root@<nueva-ip>:/opt/nexus-bdb/.env
ssh root@<nueva-ip> "chmod 600 /opt/nexus-bdb/.env"
```

Y arranca:

```bash
task docker:up
```

## Acceso SSH

Este despliegue usa una clave dedicada (no la clave personal de nadie),
generada específicamente para desplegar NEXUS-BDB: `~/.ssh/nexus-bdb-deploy`
en la máquina desde la que se despliega. Si se pierde o se quiere rotar,
basta con generar una nueva y añadir la pública a
`/root/.ssh/authorized_keys` en el servidor (con la contraseña de root, una
sola vez) -- exactamente como se hizo la primera vez.

**Nota de seguridad**: el acceso actual es `root` por contraseña. Se
recomienda, en cuanto sea posible:
- Cambiar la contraseña de `root` (la inicial era trivial).
- Desactivar el login por contraseña en `sshd_config`
  (`PasswordAuthentication no`) una vez la clave esté instalada, dejando
  solo acceso por clave.

## Verificación tras un despliegue nuevo

```bash
curl -s http://<ip>:8000/health          # {"status":"ok"}
docker compose ps                         # el contenedor debe estar "Up"
systemctl is-enabled docker                # debe decir "enabled"
```

Primer login: usuario `admin`, contraseña `changeme` -- la app obliga a
cambiarla en el primer inicio de sesión (es una instancia nueva, con su
propia base de datos, no comparte usuarios con ningún otro entorno).
