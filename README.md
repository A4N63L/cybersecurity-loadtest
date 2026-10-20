# GameVault · Carga HTTP acotada y mediciones reales

Adaptación de `attacker/flood.py` del archivo del maestro `fail2ban-ddos.zip`.
Conserva el limitador compartido, trabajadores, plazo fijo y evento de parada;
añade argumentos, métricas y separación de errores. Usa solo la biblioteca estándar
de **Python 3.10+**. No necesita pip ni acceso a credenciales.

Proyecto local independiente, preparado para Git, sin remoto ni push.
El código y los resultados saneados de `results/` son versionables.

## Archivos

- `flood.py`: generador de una sola ruta/destino, con límite global entre workers.
- `run_campaign.py`: campaña fija, secuencial, observador B y restauración de estado.
- `PROTOCOL.md`: criterio y límites escritos antes de medir.
- `render_results.py`: genera tablas **a partir de JSON reales**, sin estimar cifras.
- `test_flood.py`: comprobaciones locales de clasificación, presupuesto global e interrupción.
- `check_restoration.py`: control sin carga HTTP que verifica `finally` y watchdog ante SIGKILL.
- [`results/20261020T040045Z/SUMMARY.md`](results/20261020T040045Z/SUMMARY.md): tablas reales por servicio.

## Instalación y ejecución individual

Desde esta carpeta:

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
