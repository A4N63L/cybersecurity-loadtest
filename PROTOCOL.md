# Protocolo fijado antes de medir

## Límites y criterio

Un servicio a la vez. Escalones de **10 segundos**. Generador con máximo 20 RPS
globales entre todos sus workers, duración máxima 10 s y concurrencia máxima 4.
La campaña reserva un presupuesto de **1 RPS y una conexión** al observador B:
usa carga A de 2, 5, 10 y 19 RPS, con 1, 2, 3 y 3 workers respectivamente.
B envía como máximo una petición cada dos segundos, sin reintentos. Por tanto,
la campaña no supera 20 RPS ni cuatro peticiones simultáneas entre A y B.
Los healthchecks preexistentes siguen funcionando y se contabilizan aparte.

Un escalón sin veto será estable solo si cumple todo:

- 100 % de respuestas HTTP con el estado esperado, cero timeouts/errores de
  conexión/protocolo, sin interrupción.
- RPS HTTP completado ≥ 95 % del solicitado, contando el tiempo real y el drenaje.
- Latencia HTTP p95 ≤ 250 ms y p99 ≤ 500 ms (rango más cercano, sin interpolar).
- B responde siempre con el estado esperado y latencia < 1 s.
- Todos los servicios siguen healthy, sin OOM ni cambio de contador de reinicios.
- MemAvailable del host ≥ 1 GiB. CPU global del host < 85 % sostenido en dos
  muestras consecutivas. Se vigilan también CPU/RAM de los cinco servicios y clientes.

Se detiene la escalada ante cualquier incumplimiento. Se repite una vez el mayor
escalón estable. Si todos pasan: **mayor carga estable observada dentro del límite
probado**, nunca capacidad máxima. La muestra es breve y no acredita estabilidad
prolongada ni otros endpoints.

## Operaciones

| Servicio | Destino en bridge | Operación medida | Esperado |
|---|---|---|---|
| Frontend | `http://frontend:4200/` | HTML inicial servido por Nginx; no descarga de assets ni ejecución Angular | 200 |
| Backend | `http://backend:8000/health` | Nginx + respuesta de salud FastAPI; no CRUD/SQLite ni autenticación | 200 |
| Keycloak | `http://keycloak:8080/realms/games-lab/.well-known/openid-configuration` | Documento de discovery OIDC; no login, emisión JWT o bind LDAP | 200 |

## Protección y orden

Por servicio:

1. Basal con jail activa: 2 RPS × 10 s, concurrencia 1.
2. Capacidad sin veto para A: 5, 10 y 19 RPS × 10 s, concurrencia 2/3/3.
3. Repetición del mayor escalón estable bajo las mismas condiciones.
4. Comparación con jail activa, sin excepción: 19 RPS × 10 s (o el mayor escalón
   alcanzado). Un veto esperado no cuenta como fallo de capacidad si B sigue sano.

Las jails **no se paran ni se ponen en idle**. Para cada escalón de capacidad se
añade únicamente A a `ignoreip`, sin alterar el archivo de configuración ni las
excepciones previas. La excepción se retira tras el escalón y un drenaje de 2 s
para que el polling procese el log. Un watchdog dentro del namespace retira la
excepción a los 25 s aunque el controlador muera. Además, `finally` la restaura
ante error, SIGINT o SIGTERM. Se verifica el estado al terminar cada escalón y
las cuatro jails al finalizar la campaña. Se desbanea únicamente A si la prueba
protegida lo bloquea; se conservan otros vetos preexistentes.

El generador corre en un cliente Python independiente, sin privilegios, sin
socket Docker ni credenciales. B tiene otra IP real en la red bridge existente;
antes de medir se verifica que el access log registra la IP del socket de A.
No se utilizan cabeceras para simular IPs ni se crean subredes nuevas.

## Observación e interpretación

Cada dos segundos aproximadamente se toman CPU/RAM mediante Docker stats, CPU y
MemAvailable del host, estado/reinicios de servicios y una petición desde B.
Son observaciones muestreadas, no máximos instantáneos garantizados.

- HTTP 4xx/5xx: el servidor respondió; registrar el estado, no llamarlo bloqueo.
- Timeout/error de conexión de A: por sí solo no demuestra veto ni caída.
- Veto: IP observada + lista de vetos/evento Ban + regla/contador del firewall,
  fallo de A y disponibilidad de B.
- Indisponibilidad general: también falla B y se contrasta salud/reinicios/recursos.

No se envían ni conservan Authorization, cookies, tokens, contraseñas o cuerpos.
Las respuestas se consumen y descartan. El JSON conserva configuración saneada,
estados/categorías de error, tiempos agregados y muestras de recursos.
