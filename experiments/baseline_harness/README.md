# Arnés de medida de línea base (S3 del portátil)

**Qué es:** `arnes_baseline.py` mide M1 (comando→ACK), M2 (RTT vía `TIMESYNC`) y M3
(jitter de `ATTITUDE`), tal como los define
[`../../08_cierre/PLAN_CAMPANA.md`](../../08_cierre/PLAN_CAMPANA.md) §3. Es la tarea
**S3** de [`../../08_cierre/HANDOFF_PORTATIL.md`](../../08_cierre/HANDOFF_PORTATIL.md).

**Qué NO es — léase antes de citar cualquier número de aquí:** esto corre contra SITL,
que compila para el host con reloj simulado. El jitter que mida es **jitter de Linux, no
de un autopiloto real** (`NOTAS_ONBOARDING.txt` §7, "la trampa de la tarea 3"). Sirve para
verificar que el arnés funciona — que junta las muestras, empareja comando/ACK,
distingue réplica de pérdida — antes de gastar batería en el Bebop mañana. Ninguna cifra
de una corrida contra SITL cierra C5.

## Uso

```bash
source ~/venv-ardupilot/bin/activate.fish
cd ~/ardupilot && Tools/autotest/sim_vehicle.py -v ArduCopter --console   # en otra terminal

cd experiments/baseline_harness
python3 arnes_baseline.py --host tcp:127.0.0.1:5762 --duration 20 \
    --out-dir salidas/$(date +%Y%m%d_%H%M%S)_sitl
```

Se conecta al puerto **secundario** de SITL (`5762`), no al `5760` que ya usa la consola
de MAVProxy — así no compiten por la misma conexión. `5762` es el mismo puerto de las
capturas `previous_pcaps/hqc_handshake_*.pcapng` que ya están en el repo.

## Salida

Por corrida: `m1_comando_ack.jsonl`, `m2_timesync.jsonl`, `m3_attitude_jitter.jsonl` (una
muestra por línea) y `resumen.json` (p50/p95/p99 recalculados a partir de esos archivos —
no hay ningún número que no salga de releer el `.jsonl`). Los binarios de compilación y
las carpetas `salidas/` no se versionan (ver `.gitignore`); si una corrida es la evidencia
que hay que citar, se copia aparte con su fecha y su `git log --oneline -1` de
`~/ardupilot`, igual que pide `PLAN_CAMPANA.md` §5 para la campaña real.

## Rehearsal del 2026-09-16

10 s por métrica, contra SITL recién compilado (`b2b1b3d279`): 0 comandos perdidos (M1),
0 TIMESYNC perdidos (M2), 0 huecos > 100 ms (M3). El arnés funciona de punta a punta.
Cifras no citables (ver arriba).

## Rehearsal más largo del 2026-09-17 (experimento #5 de `08_cierre/README.md` §B-bis)

Tres bloques de 120 s cada uno (`A_1`, `A_2`, `A_3`, nomenclatura de `PLAN_CAMPANA.md` §5),
seguidos, no intercalados con otra condición porque B/C no existen todavía (ver
`campana_bebop/README.md` sobre por qué "intercalado" no aplica sin más de una condición).
Objetivo: ver si hay deriva entre corridas, no solo que el arnés funcione una vez.

| Bloque | M1 p50/p95/p99 (ms) | M2 p50/p95/p99 (ms) | M3 p50/p95/p99 (ms) | Pérdidas |
|---|---|---|---|---|
| A_1 | 3.07 / 5.68 / 5.89 | 3.04 / 5.65 / 5.88 | 17.62 / 23.33 / 23.44 | 0 |
| A_2 | 3.00 / 5.62 / 5.86 | 3.00 / 5.62 / 5.84 | 17.60 / 23.32 / 23.40 | 0 |
| A_3 | 3.04 / 5.68 / 5.87 | 3.02 / 5.64 / 5.87 | 17.63 / 23.33 / 23.42 | 0 |

**Sin deriva perceptible entre bloques** — los tres caen dentro de ±0.05 ms entre sí en
cada percentil. Sigue siendo jitter de Linux del portátil, no del Bebop (misma advertencia
de siempre): esto valida que el arnés y la metodología de bloques repetidos no introducen
inestabilidad propia, no que el sistema real vaya a comportarse igual.

## Firma del lado GCS (`--firmar`, 2026-09-17)

`HALLAZGO_firma_no_exigida.md` encontró que la GCS real nunca firma (0 de 12 tramas
capturadas). `--firmar` hace que este arnés sí firme sus mensajes salientes (`SETUP_SIGNING`
+ firma local), para poder medir el sistema con las dos mitades arregladas (FC exigiendo,
GCS firmando) — ver `../signing_policy/HALLAZGO_firma_no_exigida.md` §12 para el resultado
medido (0 pérdidas en M1/M2/M3 contra un FC parchado). No verifica la firma del FC: eso lo
audita `../signing_policy/firma_en_sitl.py`.

```bash
python3 arnes_baseline.py --host tcp:127.0.0.1:5760 --duration 20 --firmar --out-dir salidas/...
```

## Para la campaña real (C8, condición A)

Mismo script, contra el Bebop real: subir `--duration` a lo que pida el bloque (5 min por
`PLAN_CAMPANA.md` §2), usar el puerto que exponga el `arducopter` del dron en vez de
`tcp:127.0.0.1:5762`, y guardar la salida bajo
`experiments/campana_bebop/<fecha>/A_<bloque>/` junto con `meta.json` (batería, RSSI,
canal, hashes) como pide `PLAN_CAMPANA.md` §5.
