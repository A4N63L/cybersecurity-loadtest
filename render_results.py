#!/usr/bin/env python3
"""Render tables from actual sanitized JSON; never generates measurement values."""
import json
from pathlib import Path
import sys

directory = Path(sys.argv[1]).resolve()
campaign = json.loads((directory / 'campaign.json').read_text())
stages = [json.loads((directory / name).read_text()) for name in campaign['stages']]
labels = {'protected_baseline': 'Activa, basal', 'capacity': 'Activa, A exento',
          'capacity_repeat': 'A exento, repetición', 'protected_comparison': 'Activa, sin excepción'}
lines = ['# Resultados reales: campaña ' + directory.name, '',
         f"UTC: {campaign['started_at_utc']} → {campaign['ended_at_utc']}.", '',
         'Protocolo previo: [PROTOCOL.md](../../PROTOCOL.md). Campaña completa: **' + str(campaign['complete']) + '**.',
         'Todos los escalones: GET, 10 s, timeout 1 s, conexiones nuevas que se cierran al terminar.',
         'RPS HTTP = respuestas completadas / tiempo real, incluido el drenaje final.',
         'Latencias en ms, únicamente de HTTP completadas: los timeouts no entran en sus percentiles.',
         'T/O = timeouts; Conn = errores de conexión; Proto = errores de protocolo.', '']
summary = {'campaign': directory.name, 'complete': campaign['complete'], 'services': {}}
for service in ('frontend', 'backend', 'keycloak'):
    rows = [stage for stage in stages if stage['service'] == service]
    if not rows:
        lines += ['## ' + service, '', 'Sin mediciones registradas en esta campaña.', '']
        continue
    lines += ['## ' + service, '',
        '| Protección / modalidad | RPS / workers | Intentos / HTTP | HTTP 200 / otros | RPS HTTP | p50 | p95 | p99 | T/O | Conn | Proto | Resultado |',
        '|---|---|---|---|---|---|---|---|---|---|---|---|']
    for row in rows:
        config, latency = row['configuration'], row['http_latency_ms']
        result = 'Veto IP, no caída' if row['demonstrated_ban'] else ('Estable' if row['stable_without_ban'] else 'No estable')
        latency_values = ['—' if latency[q] is None else f'{latency[q]:.3f}' for q in ('p50', 'p95', 'p99')]
        fields = [labels[row['mode']], f"{config['rps_limit_global']:g} / {config['concurrency']}",
            f"{row['attempted']} / {row['http_completed']}",
            f"{row['http_statuses'].get('200', 0)} / {row['http_completed'] - row['http_statuses'].get('200', 0)}",
            f"{row['rps_completed']:.3f}", *latency_values, str(row['timeouts']),
            str(sum(row['connection_errors'].values())), str(sum(row['protocol_errors'].values())), result]
        lines.append('| ' + ' | '.join(fields) + ' |')
    repeated = [row for row in rows if row['mode'] == 'capacity_repeat' and row['stable_without_ban']]
    best = max(repeated, key=lambda row: row['configuration']['rps_limit_global']) if repeated else None
    samples = [sample for row in rows for sample in row['resource_samples']]
    target = 'ciber-p1-games-' + service + '-1'
    metrics = {'max_container_cpu_percent_sampled': max(s['containers'][target]['cpu_percent'] for s in samples),
        'max_container_memory_mib_sampled': max(s['containers'][target]['memory_bytes'] for s in samples) / 1024**2,
        'max_host_cpu_percent_sampled': max(s['host_cpu_percent'] for s in samples),
        'min_host_available_gib_sampled': min(s['host_available_bytes'] for s in samples) / 1024**3,
        'observer_b_checks': len(samples),
        'observer_b_http_200': sum(s['observer_b']['status'] == 200 for s in samples),
        'max_observer_b_latency_ms': max(s['observer_b']['latency_ms'] for s in samples),
        'max_restart_count_observed': max(state['restarts'] for s in samples for state in s['states'].values())}
    summary['services'][service] = {'highest_repeated_stable_stage': {
        'requested_rps': best['configuration']['rps_limit_global'], 'completed_rps': best['rps_completed'],
        'http_completed': best['http_completed'], 'latency_ms': best['http_latency_ms']} if best else None,
        'resources': metrics,
        'protected_comparison': [{k: row[k] for k in ('http_completed', 'timeouts', 'connection_errors', 'protection')}
                                 for row in rows if row['mode'] == 'protected_comparison']}
    lines += ['', f"Recursos observados en los {len(rows)} escalones (máximos/mínimos **muestreados**):", '',
        '| CPU contenedor máx. | RAM contenedor máx. | CPU host máx. | MemAvailable host mín. | B: HTTP 200 / sondeos | Latencia B máx. | Reinicios observados |',
        '|---|---|---|---|---|---|---|',
        f"| {metrics['max_container_cpu_percent_sampled']:.2f}% | {metrics['max_container_memory_mib_sampled']:.2f} MiB | "
        f"{metrics['max_host_cpu_percent_sampled']:.2f}% | {metrics['min_host_available_gib_sampled']:.2f} GiB | "
        f"{metrics['observer_b_http_200']} / {metrics['observer_b_checks']} | {metrics['max_observer_b_latency_ms']:.3f} ms | "
        f"{metrics['max_restart_count_observed']} |", '']
    if best:
        lines += [f"**Mayor carga estable observada dentro del límite probado: {best['configuration']['rps_limit_global']:g} RPS "
                  f"solicitados, repetidos; {best['rps_completed']:.3f} RPS HTTP alcanzados en la repetición.**", '']
protected = [row for row in stages if row['mode'] == 'protected_comparison']
confirmed = sum(row['demonstrated_ban'] for row in protected)
capacity = [row for row in stages if row['mode'].startswith('capacity')]
capacity_failures = sum(not row['stable_without_ban'] for row in capacity)
lines += ['## Interpretación y estado final', '',
    f'B tenía una IP real diferente de A. Vetos demostrados en {confirmed}/{len(protected)} comparaciones protegidas: '
    'evento Ban nuevo, IP en la lista, contador de firewall positivo y B disponible. Cuando se cumplen esas '
    'condiciones, la caída del RPS completado de A corresponde al veto, no a una indisponibilidad general '
    'ni al límite de capacidad del servicio.', '',
    'Todas las jails continuaron activas. Para capacidad se exceptuó temporalmente solo A; las excepciones '
    'se retiraron y los vetos de prueba se levantaron al terminar. Estado final igual al inicial: **' +
    str(campaign['protection_matches_initial']) + '**.', '',
    f'Escalones de capacidad sin veto que incumplieron estabilidad: {capacity_failures}/{len(capacity)}. '
    'Los errores de las filas protegidas se conservan separados en los JSON. '
    'La disponibilidad y recursos son observaciones muestreadas; 10 s no acreditan resistencia prolongada.', '',
    'Estas cifras no son capacidad máxima: solo describen las tres rutas públicas y el límite probado. '
    'No se midieron login PKCE, LDAP/TLS bajo carga, escrituras SQLite, descarga de todos los assets '
    'ni rendimiento simultáneo de las tres superficies.', '']
(directory / 'SUMMARY.md').write_text('\n'.join(lines))
(directory / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
