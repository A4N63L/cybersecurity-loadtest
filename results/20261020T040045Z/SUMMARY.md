# Resultados reales: campaña 20261020T040045Z

UTC: 2026-10-20T04:00:45.943460+00:00 → 2026-10-20T04:06:10.503906+00:00.

Protocolo previo: [PROTOCOL.md](../../PROTOCOL.md). Campaña completa: **True**.
Todos los escalones: GET, 10 s, timeout 1 s, conexiones nuevas que se cierran al terminar.
RPS HTTP = respuestas completadas / tiempo real, incluido el drenaje final.
Latencias en ms, únicamente de HTTP completadas: los timeouts no entran en sus percentiles.
T/O = timeouts; Conn = errores de conexión; Proto = errores de protocolo.

## frontend

| Protección / modalidad | RPS / workers | Intentos / HTTP | HTTP 200 / otros | RPS HTTP | p50 | p95 | p99 | T/O | Conn | Proto | Resultado |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Activa, basal | 2 / 1 | 20 / 20 | 20 / 0 | 1.999 | 2.064 | 2.349 | 81.766 | 0 | 0 | 0 | Estable |
| Activa, A exento | 5 / 2 | 50 / 50 | 50 / 0 | 4.995 | 1.785 | 2.382 | 19.747 | 0 | 0 | 0 | Estable |
| Activa, A exento | 10 / 3 | 100 / 100 | 100 / 0 | 9.982 | 1.890 | 2.430 | 3.013 | 0 | 0 | 0 | Estable |
| Activa, A exento | 19 / 3 | 190 / 190 | 190 / 0 | 18.933 | 1.938 | 2.523 | 3.582 | 0 | 0 | 0 | Estable |
| A exento, repetición | 19 / 3 | 190 / 190 | 190 / 0 | 18.937 | 1.871 | 2.412 | 24.901 | 0 | 0 | 0 | Estable |
| Activa, sin excepción | 19 / 3 | 94 / 64 | 64 / 0 | 6.341 | 1.842 | 2.302 | 70.612 | 18 | 12 | 0 | Veto IP, no caída |

Recursos observados en los 6 escalones (máximos/mínimos **muestreados**):

| CPU contenedor máx. | RAM contenedor máx. | CPU host máx. | MemAvailable host mín. | B: HTTP 200 / sondeos | Latencia B máx. | Reinicios observados |
|---|---|---|---|---|---|---|
| 44.55% | 32.02 MiB | 42.37% | 5.28 GiB | 24 / 24 | 74.004 ms | 0 |

**Mayor carga estable observada dentro del límite probado: 19 RPS solicitados, repetidos; 18.937 RPS HTTP alcanzados en la repetición.**

## backend

| Protección / modalidad | RPS / workers | Intentos / HTTP | HTTP 200 / otros | RPS HTTP | p50 | p95 | p99 | T/O | Conn | Proto | Resultado |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Activa, basal | 2 / 1 | 20 / 20 | 20 / 0 | 1.999 | 3.489 | 4.487 | 25.697 | 0 | 0 | 0 | Estable |
| Activa, A exento | 5 / 2 | 50 / 50 | 50 / 0 | 4.995 | 3.494 | 4.350 | 25.868 | 0 | 0 | 0 | Estable |
| Activa, A exento | 10 / 3 | 100 / 100 | 100 / 0 | 9.982 | 3.556 | 4.495 | 6.341 | 0 | 0 | 0 | Estable |
| Activa, A exento | 19 / 3 | 190 / 190 | 190 / 0 | 18.904 | 3.653 | 4.441 | 14.185 | 0 | 0 | 0 | Estable |
| A exento, repetición | 19 / 3 | 189 / 189 | 189 / 0 | 18.841 | 3.496 | 4.376 | 5.747 | 0 | 0 | 0 | Estable |
| Activa, sin excepción | 19 / 3 | 94 / 62 | 62 / 0 | 5.649 | 3.500 | 4.234 | 25.123 | 20 | 12 | 0 | Veto IP, no caída |

Recursos observados en los 6 escalones (máximos/mínimos **muestreados**):

| CPU contenedor máx. | RAM contenedor máx. | CPU host máx. | MemAvailable host mín. | B: HTTP 200 / sondeos | Latencia B máx. | Reinicios observados |
|---|---|---|---|---|---|---|
| 49.33% | 105.50 MiB | 40.98% | 5.25 GiB | 24 / 24 | 75.131 ms | 0 |

**Mayor carga estable observada dentro del límite probado: 19 RPS solicitados, repetidos; 18.841 RPS HTTP alcanzados en la repetición.**

## keycloak

| Protección / modalidad | RPS / workers | Intentos / HTTP | HTTP 200 / otros | RPS HTTP | p50 | p95 | p99 | T/O | Conn | Proto | Resultado |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Activa, basal | 2 / 1 | 20 / 20 | 20 / 0 | 1.999 | 6.990 | 8.183 | 34.052 | 0 | 0 | 0 | Estable |
| Activa, A exento | 5 / 2 | 50 / 50 | 50 / 0 | 4.995 | 7.373 | 9.502 | 29.144 | 0 | 0 | 0 | Estable |
| Activa, A exento | 10 / 3 | 100 / 100 | 100 / 0 | 9.982 | 6.224 | 8.339 | 8.664 | 0 | 0 | 0 | Estable |
| Activa, A exento | 19 / 3 | 190 / 190 | 190 / 0 | 18.935 | 5.705 | 7.243 | 12.672 | 0 | 0 | 0 | Estable |
| A exento, repetición | 19 / 3 | 190 / 190 | 190 / 0 | 18.937 | 5.213 | 6.182 | 9.214 | 0 | 0 | 0 | Estable |
| Activa, sin excepción | 19 / 3 | 99 / 70 | 70 / 0 | 6.725 | 4.684 | 6.048 | 75.866 | 18 | 11 | 0 | Veto IP, no caída |

Recursos observados en los 6 escalones (máximos/mínimos **muestreados**):

| CPU contenedor máx. | RAM contenedor máx. | CPU host máx. | MemAvailable host mín. | B: HTTP 200 / sondeos | Latencia B máx. | Reinicios observados |
|---|---|---|---|---|---|---|
| 50.66% | 569.10 MiB | 41.48% | 5.25 GiB | 24 / 24 | 85.877 ms | 0 |

**Mayor carga estable observada dentro del límite probado: 19 RPS solicitados, repetidos; 18.937 RPS HTTP alcanzados en la repetición.**

## Interpretación y estado final

B tenía una IP real diferente de A. Vetos demostrados en 3/3 comparaciones protegidas: evento Ban nuevo, IP en la lista, contador de firewall positivo y B disponible. Cuando se cumplen esas condiciones, la caída del RPS completado de A corresponde al veto, no a una indisponibilidad general ni al límite de capacidad del servicio.

Todas las jails continuaron activas. Para capacidad se exceptuó temporalmente solo A; las excepciones se retiraron y los vetos de prueba se levantaron al terminar. Estado final igual al inicial: **True**.

Escalones de capacidad sin veto que incumplieron estabilidad: 0/12. Los errores de las filas protegidas se conservan separados en los JSON. La disponibilidad y recursos son observaciones muestreadas; 10 s no acreditan resistencia prolongada.

Estas cifras no son capacidad máxima: solo describen las tres rutas públicas y el límite probado. No se midieron login PKCE, LDAP/TLS bajo carga, escrituras SQLite, descarga de todos los assets ni rendimiento simultáneo de las tres superficies.
