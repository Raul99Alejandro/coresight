# Clip de Glimmer sin red (lo graba Raúl)

Para el premio de modelos abiertos y el tramo 2:30 a 2:50 del video.
Duración final: 20 a 30 s. La descripción tarda unos 8 min en la laptop, así que la parte de espera va acelerada y se dice en pantalla.

## Antes de grabar

1. Cerrar todo lo que no sea la terminal (correo, Discord, navegador).
2. Una sola terminal de PowerShell en `D:\Repos\coresight`, letra grande, fondo oscuro.
3. Grabar la pantalla completa, para que se vea el ícono de red de Windows.

## Toma por toma

| # | En pantalla | Comando o acción | Texto en pantalla (inglés) |
|---|---|---|---|
| 1 | Barra de Windows | Apagar el Wi-Fi y desconectar el cable. Abrir el panel de red para que se vea "No internet" | "Network off" |
| 2 | Terminal | `Test-NetConnection dev.meta.ai -Port 443` (sale `TcpTestSucceeded : False`) | "No route to Meta's API" |
| 3 | Terminal | Levantar Glimmer (comando abajo) hasta que diga `listening on http://127.0.0.1:8080` (unos 30 s) | "Muse Glimmer, open weights, on this laptop" |
| 4 | Segunda terminal | `.venv\Scripts\python scripts\offline_glimmer.py` | "A public core photo, cache off" |
| 5 | Espera | Acelerar 30x o más | "About 8 min on an 8 GB laptop GPU, sped up" |
| 6 | Terminal | El JSON validado con `visible_sulfides` y la línea `Valid GeologyDescription in ... s, no network.` | "Same validated output as the cloud model" |

Comando de la toma 3 (en otra terminal):

```powershell
D:\models\llama.cpp\llama-server.exe -m D:\models\glimmer\Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf --mmproj D:\models\glimmer\mmproj-Muse-Glimmer-30B-Q4_K_M.gguf -a muse-glimmer -c 16384 --host 127.0.0.1 --port 8080
```

## Voz en off (inglés, unos 15 s)

"No internet. Muse Glimmer, Meta's open-weight model, runs on the mine's own laptop. Same photo, same contract, same validated log. Private core never leaves the site."

## Notas

- La foto es `data/raw/commons_potter_07.jpg` (Commons, Potter Mine). En la corrida del día 6, Glimmer marcó sulfuros visibles en ella. Si en la toma no los marca, no se repite ni se edita: se usa lo que salga.
- `offline_glimmer.py` se detiene solo si encuentra red, así que no se puede grabar por error con internet.
- Cada corrida queda en `outputs/describe/offline_runs.jsonl` con los hashes de la imagen y de la respuesta. Ese archivo entra al repo junto con el clip.
- Al terminar: prender la red y apagar llama-server.
