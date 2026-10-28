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
4. Cookie del visitante (puntos 1 y 2 del tercer análisis): en `/etc/coresight.env` agregar `CORESIGHT_SESSION_SECRET=` con 64 caracteres al azar (`openssl rand -hex 32`). Firma la cookie `cs_visitor` que dice de quién es cada caja. Si falta, el servidor genera uno al arrancar y cada reinicio solo olvida de quién eran las cajas subidas.
5. Vigilancia de créditos (punto G): `/etc/coresight-ops.env` con `CORESIGHT_OPS_TOKEN=...` (modo 600). Sin ese archivo `/ops` y `/api/ops/usage` responden 404.
6. nginx: `deploy/nginx-coresight.conf` en `sites-available`, enlace en `sites-enabled`, `nginx -t`, `systemctl reload nginx`, luego `certbot --nginx -d coresight.analizac.com`.

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
.venv/Scripts/python scripts/prewarm_demo.py https://coresight.analizac.com
```
`prewarm_demo.py` corre cada muestra pública y la captura del recorrido: la segunda vez debe decir 0 llamadas en vivo. También revisa que `/api/showcase` tenga la caja de Nevada, una caja aprobada con agentes y su barreno (la portada y el recorrido de 60 s los usan).

## Límites de la demo pública
- 20 análisis, 120 dictados y 200 toques de SAM por hora en total (`CORESIGHT_MAX_*` en `compose.yml`), para que un extraño no gaste los créditos.
- Por visitante (la IP que ve nginx en `X-Real-IP`): 5 análisis en 10 minutos (`CORESIGHT_MAX_ANALYSES_PER_VISITOR`). Las muestras ya están en caché: tienen su propio tope de 200 por hora y no gastan el de las fotos subidas.
- La compuerta lee el tamaño de la foto del encabezado antes de decodificarla: más de 8000 px por lado, más de 20 MB, GIF, PDF, TIFF, HEIC o un archivo dañado se rechazan con un mensaje claro (`tests/test_abuse.py`).
- `https://coresight.analizac.com/ops` (solo nosotros, con el token): llamadas reales, respuestas de la caché, errores, 429 y tokens por modelo en la última hora, 24 h y desde el inicio, y lo que queda de cada tope. Lo escribe `meta_client.py` en `usage.jsonl` del volumen de caché, sin prompts ni imágenes.
- Cada navegador ve solo sus cajas (cookie firmada `cs_visitor`, HttpOnly, SameSite=Lax, Secure detrás de https): la lista "Boxes", las imágenes y toda ruta de una caja ajena responden 404. La portada, el recorrido y el barreno público usan cajas fijadas (`pinned`), de solo lectura para todos (403 al corregir o aprobar); "Try a sample box" crea una copia del visitante. Al primer arranque sin cajas fijadas, el servidor fija las muestras que la portada ya mostraba (`pin_legacy_samples`). Para fijar otra: `curl -X POST -H "X-Ops-Token: ..." https://coresight.analizac.com/api/ops/pin/{id}` (`?pinned=false` la suelta). `/api/ops/usage` lista las fijadas.
- Las cajas revisadas viven en el volumen `coresight-data`; la caché de SAM y Muse Spark en `coresight-cache`, así una muestra ya analizada no se vuelve a pagar.
