# Ejecución posterior real del original y comprobación del adaptado

Fecha: **21 de octubre de 2026 UTC**. Esto subsana la falta de una ejecución
documentada del original, pero **no acredita que se ejecutase antes de desarrollar
la adaptación**. No se modifican fechas ni resultados de la campaña del día 20.

## Identidad y entorno

- Fuente: `attacker/flood.py` de `fail2ban-ddos.zip`, extraído sin editar.
- Copia versionada: [reference/attacker/flood.py](../../reference/attacker/flood.py),
  dentro de `videojuegos-loadtest/`.
- SHA-256 antes y después:
  `48189b9442150d04c1771d83df3cf57eed3048536e2f44dba7fe17cca9d35434`.
- Daemon: `unix:///tmp/opencode/games-docker.sock`, el seleccionado por `lab.sh`.
- Red interna independiente: `172.30.240.0/24`, sin solaparse con las redes Docker
  ni rutas no predeterminadas observadas. Ningún puerto se publicó en el host.
- Víctimas: Dockerfiles del ZIP con `nginx:1.27-alpine`, sus configuraciones y sitios
  intactos. Protegida con Fail2Ban/iptables y `NET_ADMIN`/`NET_RAW`; sin privilegio global.
- Cliente: imagen ya existente `python:3.12-slim`, script montado read-only.
  Se omitió la construcción del cliente Alpine con curl porque no se necesita para
  ejecutar el original, que solo usa la biblioteca estándar.
- Límites: protegida 256 MiB/1 CPU; no protegida 96 MiB/0,5 CPU; cliente 128 MiB/0,5 CPU.

`provenance.json` conserva también el hash del ZIP y de cada archivo extraído de
las víctimas. `original.build.compose.json` describe solo la construcción temporal
de las dos víctimas. Los comandos completos están en `commands.txt`.

## Original: comando y salida

```bash
docker --host unix:///tmp/opencode/games-docker.sock exec \
  -e DURATION=10 -e CONCURRENCY=3 -e REQUESTS_PER_SECOND=20 \
  games-original-20261021t033842z-attacker python3 /flood.py
```

Inicio externo: **03:41:39.712734 UTC**. Fin: **03:42:02.882472 UTC**.
Duración externa: **23,172 s**; cada destino tuvo 10 s de emisión, con drenaje de
conexiones al terminar. Código de salida: **0**. Orden observado en stdout:

| Orden | Destino | Total del original | HTTP 200 | No-200/fallos agrupados |
|---|---|---|---|---|
| 1 | `http://victim-protected:80/` | 87 | 64 | 23 |
| 2 | `http://victim-unprotected:80/` | 200 | 200 | 0 |

La salida literal está en `original.stdout.txt`; `original-execution.json` conserva
comando, entorno numérico, fechas, orden, hash y resumen. `original.stderr.txt`
está vacío. El original no proporciona latencias ni desglose de timeouts/conexión;
no se inventan esas cifras.

### Interpretación del protegido

Se observó la IP real `172.30.240.20` en el access log. El 21 de octubre a
**03:41:44.196 UTC**, Fail2Ban registró su Ban. La regla INPUT del namespace tenía
**35 paquetes REJECT**, y otro cliente con IP `172.30.240.11` seguía accediendo
a la víctima protegida. Véase `original-before.json` y `original-after.json`.

Esto demuestra el veto de esa IP y disponibilidad para otro origen. **No demuestra
que cada uno de los 23 fallos agrupados sea un bloqueo individual**: el programa
original mezcla códigos HTTP no-200, timeouts y errores de conexión en su resumen.
Tampoco el contador de paquetes equivale al de peticiones. No se afirma una caída
general ni una capacidad máxima.

## Adaptado: comprobación posterior, no benchmark repetido

```bash
docker --host unix:///tmp/opencode/games-docker.sock exec \
  games-original-20261021t033842z-adapted python3 /work/flood.py frontend 4200 \
  --scheme http --path / --duration 5 --concurrency 1 --rps 2 --timeout 1
```

Se lanzó **después** de finalizar el original: comando externo de **03:42:07.738100
a 03:42:14.062615 UTC**. El generador midió **5,003026 s** desde 03:42:09.003403 UTC.
Resultado: **10 intentos, 10 HTTP 200, cero timeouts/errores de conexión/protocolo**;
**1,998790 RPS** completados. Código de salida 0, sin interrupción.

El cliente se conectó solo a la red existente del dashboard, con IP `172.29.0.7`.
La jail del frontend permaneció activa y no se añadieron excepciones ni se
levantaron vetos del dashboard. Esta comprobación del HTML no mide carga máxima,
login, LDAP o escritura de juegos. Se conservan `adapted-execution.json` y
`adapted-result.json`, sin cabeceras ni cuerpos.

## Estado del dashboard y limpieza

Al comenzar, el daemon persistente conservaba sus imágenes y contenedores, pero
los cinco servicios estaban detenidos tras el reinicio. Solo se arrancaron esos
contenedores: no se recrearon, no se reconstruyeron sus imágenes, no se restauraron
bases ni se modificó su configuración. La preparación de las víctimas originales
fue independiente. Las huellas de configuración se publican, no el contenido de
sus variables privadas.

`cleanup.json` confirma la retirada de los cuatro contenedores temporales
(dos víctimas, atacante y cliente de comprobación), la red y las dos etiquetas
temporales de imagen. También se eliminó el directorio temporal propio de trabajo.
Se conservaron imágenes y datos del dashboard, la imagen Python reutilizada y la
caché del daemon; no se hizo prune global.

`dashboard-after.json` confirma los mismos IDs de contenedor, IDs de imagen y
huellas de configuración, los cinco servicios healthy y estas cuatro jails activas:

- Frontend: `http-flood`.
- Backend: `http-flood`.
- Keycloak: `http-flood`.
- OpenLDAP: `ldaps-connections`.

Dos intentos de preparación anteriores no ejecutaron carga: uno encontró metadatos
IPAM nulos y el otro una opción incompatible del selector de builder de la CLI.
Se corrigió únicamente el auxiliar de preparación; sus `outcome.json` y limpieza
se conservan en los directorios terminados en `033512Z` y `033711Z`. No cuentan
como ejecuciones del original.
