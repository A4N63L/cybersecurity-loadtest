# GameVault · Carga HTTP acotada y mediciones reales

Adaptación de `attacker/flood.py` del archivo del maestro `fail2ban-ddos.zip`.
Conserva el limitador compartido, trabajadores, plazo fijo y evento de parada;
añade argumentos, métricas y separación de errores. Usa solo la biblioteca estándar
de **Python 3.10+**. No necesita pip ni acceso a credenciales.

Repositorio publicado: https://github.com/A4N63L/cybersecurity-loadtest.
El código y los resultados saneados de `results/` son versionables.

## Ejecución posterior del original y límite histórico

**El original intacto se ejecutó el 21 de octubre de 2026, y después se comprobó
brevemente el adaptado.** Las evidencias están en
[original-followup-20261021T033842Z/FOLLOWUP.md](results/original-followup-20261021T033842Z/FOLLOWUP.md).
Se conserva el archivo extraído sin editar en `reference/attacker/flood.py`, con
SHA-256 `48189b9442150d04c1771d83df3cf57eed3048536e2f44dba7fe17cca9d35434`.

**Sigue sin acreditarse una ejecución del original anterior al desarrollo de la
adaptación.** La nueva evidencia es una subsanación posterior, no prueba de ese
orden histórico. Leer el ZIP o comparar código tampoco lo habría demostrado.

La campaña conservada en `results/20261020T040045Z/` corresponde a la **versión
adaptada**, entre 04:00:45 y 04:06:10 UTC del 20 de octubre de 2026. Su campo
`complete=true` significa que terminó esa campaña, no que se haya acreditado la
ejecución previa del original. Sus cifras y fechas siguen intactas; la ejecución
posterior se guarda en otro directorio. El contraste completo está en
[CONTRASTE-ENUNCIADO.md](https://github.com/A4N63L/cybersecurity-backend/blob/main/CONTRASTE-ENUNCIADO.md).

| Aspecto | `attacker/flood.py` original del ZIP | Adaptación entregada |
|---|---|---|
| Destinos | `victim-protected` y `victim-unprotected`, secuenciales, HTTP/80 y `/` fijos | Un host y puerto posicionales; esquema y ruta por argumentos |
| Carga | Variables `DURATION`, `CONCURRENCY`, `REQUESTS_PER_SECOND`; valores autónomos 20 s / 40 / 50 RPS; máximos 300 s / 500 / 500 RPS | CLI; valores por defecto 10 s / 1 / 2 RPS; límites de esta etapa 10 s / 4 / 20 RPS |
| Límite de tasa | Compartido entre workers de cada destino | Compartido entre todos los workers del único destino, sin recuperar retrasos con ráfagas |
| Transporte | `urllib.request`, GET y timeout fijo 2 s; seguimiento normal de redirecciones | `http.client`, HTTP/HTTPS, timeout configurable; sin seguir redirecciones, cierre explícito y descarte acotado del cuerpo |
| Errores | Cuenta estados; agrupa timeout/conexión como `000` y resume no-200 como fallos | Estados HTTP, timeouts, errores de conexión y protocolo separados |
| Resultados | Totales y porcentaje no-200; sin RPS alcanzado ni percentiles | JSON saneado, completadas, RPS real y p50/p95/p99 |
| Interrupción | Ctrl+C y evento de parada | SIGINT/SIGTERM, parada de nuevas peticiones y JSON parcial |

Se mantienen del original el patrón de pool de trabajadores, plazo fijo, evento
de parada y limitador global. `run_campaign.py` añade la observación de recursos,
el cliente B y las excepciones temporales de Fail2Ban; no forma parte del original.

### Subsanación realizada el 21 de octubre de 2026 UTC

Se construyeron únicamente las dos víctimas temporales con sus Dockerfiles,
Nginx, filtro, jail, entrypoint y sitios del ZIP sin editar. Respondieron como
`victim-protected` y `victim-unprotected` en HTTP/80, en la red interna independiente
`172.30.240.0/24`, sin publicar puertos. El cliente reutilizó `python:3.12-slim`
en vez del cliente Alpine/curl del ZIP: el original solo usa la biblioteca estándar.
No se reconstruyeron imágenes del dashboard.

Comando efectivamente ejecutado, conservado también en `original-execution.json`:

```bash
docker --host unix:///tmp/opencode/games-docker.sock exec \
  -e DURATION=10 -e CONCURRENCY=3 -e REQUESTS_PER_SECOND=20 \
  games-original-20261021t033842z-attacker python3 /flood.py
```

La emisión se configuró a 10 s por destino, secuenciales; el proceso completo duró
23,172 s, incluidos arranque y drenaje de conexiones con timeout. Salida literal
en `original.stdout.txt`:

| Destino, por orden | Intentos contabilizados por el original | HTTP 200 | No-200/fallos agrupados |
|---|---|---|---|
| `victim-protected` | 87 | 64 | 23 |
| `victim-unprotected` | 200 | 200 | 0 |

Se confirmó un Ban de `172.30.240.20` y una regla con 35 paquetes rechazados;
otro cliente, `172.30.240.11`, siguió accediendo a la víctima protegida. Eso
demuestra el veto de la IP, **no una atribución individual de los 23 fallos**:
el original no separa sus errores de transporte ni todos los códigos no-200,
y paquetes rechazados no equivalen a peticiones HTTP.

Después, a las 03:42:07 UTC, se lanzó el adaptado en otro cliente conectado solo
a la red del dashboard, con sus argumentos reales:

```bash
docker --host unix:///tmp/opencode/games-docker.sock exec \
  games-original-20261021t033842z-adapted python3 /work/flood.py frontend 4200 \
  --scheme http --path / --duration 5 --concurrency 1 --rps 2 --timeout 1
```

Completó 10 HTTP 200, sin errores, en 5,003 s medidos por el generador (1,999 RPS).
Fue una comprobación breve, **no una repetición de los benchmarks**. Sus tiempos
y salida están en `adapted-execution.json` y `adapted-result.json`.

Los contenedores indicados en esos comandos históricos ya fueron eliminados,
junto con las dos etiquetas de imagen y la red temporal. Las cuatro jails del
dashboard quedaron activas, sin excepciones nuevas, y se conservaron sus IDs,
imágenes y huellas de configuración. El dashboard se encontró detenido tras
reiniciar el daemon y solo se arrancaron sus contenedores existentes.

Dos preparaciones previas abortaron **sin ejecutar carga**; sus `outcome.json`
quedan en los directorios `original-followup-20261021T033512Z` y
`original-followup-20261021T033711Z`. No se presentan como ejecuciones del original.

La diferencia histórica permanece: esta ejecución ocurrió después del desarrollo.
La aceptación de la subsanación respecto a ese orden literal corresponde al maestro.

## Archivos

- `flood.py`: generador de una sola ruta/destino, con límite global entre workers.
- `run_campaign.py`: campaña fija, secuencial, observador B y restauración de estado.
- `PROTOCOL.md`: criterio y límites escritos antes de medir.
- `render_results.py`: genera tablas **a partir de JSON reales**, sin estimar cifras.
- `test_flood.py`: comprobaciones locales de clasificación, presupuesto global e interrupción.
- `check_restoration.py`: control sin carga HTTP que verifica `finally` y watchdog ante SIGKILL.
- `reference/`: script y componentes de las víctimas extraídos del ZIP sin editar;
  se conservan para identificar y reproducir la referencia utilizada.
- [`results/20261020T040045Z/SUMMARY.md`](results/20261020T040045Z/SUMMARY.md): tablas reales por servicio.
- [`results/original-followup-20261021T033842Z/`](results/original-followup-20261021T033842Z/FOLLOWUP.md):
  ejecución posterior del original y comprobación del adaptado, con hashes y limpieza.

## Instalación y ejecución individual

Desde esta carpeta:

El comando individual siguiente es un ejemplo de uso; no es el registro de una
ejecución del original ni de la campaña publicada.

```bash
python3 --version
python3 -m unittest -v test_flood.py
python3 flood.py 127.0.0.1 4200 --scheme http --path / --duration 10 --concurrency 1 --rps 2 --timeout 1 --output results/manual-frontend.json
```

Argumentos: host y puerto posicionales; `--scheme http|https`, `--path`, `--duration`,
`--concurrency`, `--rps`, `--timeout`, `--expected-status` y `--output`. Para HTTPS,
`--ca-file` permite una CA de confianza; se mantiene la validación de certificado/nombre.
El host no admite credenciales/URL y la ruta no admite query ni fragmento.

Esta etapa impone duración ≤ **10 s**, concurrencia ≤ **4**, RPS global ≤ **20**,
timeout >0 y ≤2 s. Los valores no se multiplican por el número de workers.
Cada petición abre una conexión y la cierra incluso ante errores. No se siguen
redirecciones: un 302 se cuenta como 302. El cuerpo se consume y descarta, con límite
de 4 MiB. Los timeouts son de socket/conexión/lectura; la resolución DNS depende
del resolvedor del sistema. La campaña usa el DNS local de Docker.

Ctrl+C y SIGTERM detienen nuevas peticiones, drenan los trabajadores y devuelven
JSON parcial con `interrupted=true`, código 130. No se escriben encabezados,
Authorization, cookies, cuerpos ni mensajes de excepción potencialmente sensibles.

Salida JSON:

- `attempted` y `http_completed`; `http_statuses` separados por código.
- `timeouts`, `connection_errors` (DNS/refused/reset/TLS/otros) y `protocol_errors`.
- RPS intentado/completado sobre tiempo real, incluido drenaje.
- p50/p95/p99 de **HTTP completadas**, también si el código no es el esperado.
  Los fallos de transporte quedan fuera de esos percentiles y se muestran aparte.
  Percentiles por rango más cercano, sin interpolación; `null` si no hubo HTTP.

## Repetir la campaña controlada

El laboratorio debe estar ya activo. No lo reconstruye ni modifica sus archivos.
Se requieren las carpetas hermanas `videojuegos-backend` y `videojuegos-auth`, Docker
y permisos para el mismo daemon que selecciona `lab.sh`.

```bash
DOCKER_HOST="$(bash ../videojuegos-backend/lab.sh docker-host)" docker pull python:3.12-slim
python3 run_campaign.py
python3 render_results.py results/20261020T040045Z
```

En la tercera línea usa el directorio que indique **tu** ejecución. El pull prepara
solo el cliente Python independiente; no construye imágenes protegidas. El generador
se ejecuta en `games-loadtest-a`, creado desde `python:3.12-slim`, y B en otro cliente
de la misma imagen. Ninguno usa las imágenes frontend/backend/Keycloak ni recibe
socket Docker, credenciales, privilegios o publicaciones al host. Tienen raíz
read-only, capabilities eliminadas, 128 MiB y 0,5 CPU cada uno.

Se reutiliza `ciber-p1-games_lab` sin crear subredes. Los destinos son los puertos
internos, no los publicados de loopback. Se verifica primero la IP del socket en
los access logs. Los clientes se eliminan al terminar; un lock impide campañas paralelas.

Por servicio: basal protegido 2 RPS; escalones sin veto 5/10/19 RPS; repetición de 19;
comparación protegida 19 RPS. Cada uno dura 10 s. A usa hasta 3 workers y 19 RPS;
B reserva la cuarta conexión y un presupuesto de 1 RPS, realizando sondeos como máximo
cada 2 s. El tráfico de ambos queda dentro de 20 RPS/4 peticiones simultáneas.
Los healthchecks preexistentes del lab no se cambian y son tráfico adicional de fondo.

### Comandos efectivamente utilizados para los resultados publicados

Desde `videojuegos-loadtest`, durante la etapa de mediciones (no ejecutados de
nuevo en este contraste documental):

```bash
docker --host unix:///tmp/opencode/games-docker.sock pull python:3.12-slim
python3 run_campaign.py
python3 render_results.py results/20261020T040045Z
python3 check_restoration.py results/20261020T040045Z
```

El controlador lanzó dentro de A el generador **adaptado** con argumentos como:

```bash
python3 /work/flood.py frontend 4200 --path / --duration 10 --concurrency 3 --rps 19
python3 /work/flood.py backend 8000 --path /health --duration 10 --concurrency 3 --rps 19
python3 /work/flood.py keycloak 8080 --path /realms/games-lab/.well-known/openid-configuration --duration 10 --concurrency 3 --rps 19
```

Son las invocaciones subyacentes del controlador, no órdenes adicionales ejecutadas
manualmente. HTTP y timeout 1 s fueron los valores por defecto. Los JSON de cada
escalón conservan destino, ruta, duración, concurrencia, RPS solicitado, tiempo real
y resultados; `campaign.json` conserva el orden, las IP y el estado de protección.

### Estado de Fail2Ban

La campaña **no detiene ninguna jail**. Solo añade la IP exacta de A a `ignoreip`
durante cada escalón de capacidad; el resto de clientes sigue protegido. Se conserva
la lista previa y se retira únicamente esa excepción, tras un drenaje de 2 s de logs.
Cada operación está envuelta en `finally`; el generador recibe SIGINT ante una
interrupción o alerta del monitor. Un watchdog dentro del namespace retira la excepción
y el veto de prueba a los 25 s aunque el controlador desaparezca. Si expira durante
la medición, esa medición se considera inválida. Se verifica la restauración de
cada escalón y de las **cuatro jails**, incluida LDAPS, al finalizar.

Para inspección independiente, desde el backend:

```bash
bash lab.sh exec -T frontend fail2ban-client status http-flood
bash lab.sh exec -T backend fail2ban-client status http-flood
bash lab.sh exec -T keycloak fail2ban-client status http-flood
bash lab.sh exec -T openldap fail2ban-client status ldaps-connections
```

Si el controlador recibe SIGKILL, el generador igualmente tiene un plazo de 10 s
y el watchdog restaura la excepción. Antes de repetir, inspecciona cualquier cliente
`games-loadtest-a/b` que haya quedado: la campaña no elimina nombres preexistentes.

Se comprobó la restauración tanto ante una excepción del controlador como ante
SIGKILL. El control usa únicamente una dirección TEST-NET sin cliente real y envía
cero peticiones HTTP; resultado en `results/20261020T040045Z/restoration-checks.json`.
Para repetir solo ese control:

```bash
python3 check_restoration.py results/20261020T040045Z
```

## Criterio y alcance de las cifras

El [protocolo previo](PROTOCOL.md) fija: cero errores, 100 % del estado esperado,
RPS completado ≥95 % del solicitado, p95 ≤250 ms, p99 ≤500 ms, B siempre disponible
en menos de 1 s, sin reinicios/OOM, MemAvailable ≥1 GiB y CPU host <85 % sostenido
en dos muestras. Se observa un servicio a la vez y se frena la escalada ante fallos.

| Ruta | Qué mide | Esperado |
|---|---|---|
| Frontend `GET /` | HTML inicial de Nginx; sin assets/Angular en navegador | 200 |
| Backend `GET /health` | Nginx + FastAPI; sin CRUD ni SQLite | 200 |
| Keycloak `GET /realms/games-lab/.well-known/openid-configuration` | Discovery OIDC; sin login/emisión de tokens/LDAP | 200 |

Las tres rutas pasaron 19 RPS y su repetición sin veto. La conclusión es
**mayor carga estable observada dentro del límite probado**, no capacidad máxima.
Consulta las tablas y muestras reales enlazadas arriba para RPS, percentiles,
errores, recursos, estado de protección y observador B.

Resultados de la **repetición**, con excepción temporal solo para A y jail activa:

| Servicio | Duración de emisión | Workers A | RPS solicitado / alcanzado | HTTP 200 completadas | p50 / p95 / p99 (ms) | Errores |
|---|---|---|---|---|---|---|
| Frontend | 10 s | 3 | 19 / 18,937 | 190 | 1,871 / 2,412 / 24,901 | 0 |
| Backend | 10 s | 3 | 19 / 18,841 | 189 | 3,496 / 4,376 / 5,747 | 0 |
| Keycloak | 10 s | 3 | 19 / 18,937 | 190 | 5,213 / 6,182 / 9,214 | 0 |

El RPS alcanzado incluye el tiempo real de emisión y drenaje; por eso no tiene
que ser exactamente 19. Son observaciones breves de esas rutas públicas: no se
midió capacidad máxima ni carga de autenticación, LDAP o escritura de juegos.

### Bloqueo frente a caída

- HTTP 4xx/5xx: hubo respuesta HTTP, no demuestra veto de firewall.
- Timeout/refused de A por sí solo: no demuestra ni bloqueo ni caída.
- Veto demostrado: IP real observada, nuevo Ban, IP vetada, contador de firewall
  positivo, errores de A y B todavía con 200. En las tres comparaciones protegidas
  ocurrió esto; no fue indisponibilidad general.
- Caída general: también falla B; se contrasta con salud, reinicios/OOM y recursos.

Las muestras CPU/RAM son aproximadas cada dos segundos, no picos instantáneos
garantizados. Las pruebas de 10 s y las rutas elegidas no acreditan resistencia
prolongada, rendimiento de login/LDAPS, escritura de juegos o carga simultánea.
