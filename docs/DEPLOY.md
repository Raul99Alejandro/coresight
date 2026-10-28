# Despliegue de la demo

URL: https://coresight.analizac.com (VPS compartido de AnaliZac).

Reglas del VPS (`centro-de-mando/vault/analizac/_empresa/despliegue.md`):
- Es una caja compartida: `nginx -t` y `reload`, nunca `restart`.
- Docker se salta ufw: el contenedor publica solo en `127.0.0.1:8610`.
- En el VPS docker requiere `sudo` (el usuario de `analizac-vps` no está en el grupo docker).
- Imágenes construidas en la PC y subidas con `docker save -o`, `scp` y `docker load -i` (Actions sigue bloqueado). Llevan `vps.keep=true` para que el prune nocturno no las borre.
- `META_API_KEY` vive solo en `/etc/coresight.env` (modo 600), nunca en git ni en la imagen.

La imagen solo lleva fotos públicas (Onkalo, Commons, CC BY-SA 4.0; Nevada U12G cajas 1 y 3, DOE, dominio público). El Kaggle (NC) no entra: `.dockerignore` es una lista blanca.

## Una sola vez
1. DNS: registro A `coresight` -> IP del VPS en hPanel (analizac.com no tiene wildcard).
2. En el VPS, Raúl crea `/etc/coresight.env` con `META_API_KEY=...` y `chmod 600`.
3. `/opt/coresight/compose.yml` = `deploy/compose.yml`.
4. nginx: `deploy/nginx-coresight.conf` en `sites-available`, enlace en `sites-enabled`, `nginx -t`, `systemctl reload nginx`, luego `certbot --nginx -d coresight.analizac.com`.

## Cada versión (Bash en la PC)
En PowerShell 5.1, `docker save | ssh` corrompe el tar ("invalid tar header"): se guarda a un archivo y se copia con `scp`.
```bash
tag=$(git rev-parse --short HEAD)
docker build -t coresight:$tag .
docker save -o /tmp/coresight-$tag.tar coresight:$tag
scp /tmp/coresight-$tag.tar analizac-vps:/tmp/
ssh analizac-vps "sudo docker load -i /tmp/coresight-$tag.tar && rm /tmp/coresight-$tag.tar"
ssh analizac-vps "cd /opt/coresight && echo $tag | sudo tee .tag && sudo IMAGE_TAG=$tag docker compose up -d && sudo docker ps --filter name=coresight"
curl https://coresight.analizac.com/api/health
```

## Límites de la demo pública
- 20 análisis, 120 dictados y 200 toques de SAM por hora en total (`CORESIGHT_MAX_*` en `compose.yml`), para que un extraño no gaste los créditos.
- Las cajas revisadas viven en el volumen `coresight-data`; la caché de SAM y Muse Spark en `coresight-cache`, así una muestra ya analizada no se vuelve a pagar.
