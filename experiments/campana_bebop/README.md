# Campaña en el Bebop — preparado para el Día 0

**Qué es esta carpeta:** el lugar donde va a vivir todo lo que se mida contra el Bebop
real (`08_cierre/PLAN_CAMPANA.md` §5: `<fecha>/<condición>_<bloque>/`). Hoy, sin dron a
mano, se dejó listo el **Día 0** (§1: inspeccionar y respaldar sin cambiar nada) para no
perder tiempo de batería el día que sí haya un Bebop.

## Qué hay

| Archivo | Qué hace | Probado contra un Bebop real |
|---|---|---|
| [`dia0_inspeccion.sh`](dia0_inspeccion.sh) | Automatiza `PLAN_CAMPANA.md` §1.1 (inspección por telnet) y §1.2 (respaldo del binario + `APM/CFG/*` por FTP, con SHA-256) | **No.** Se escribió y se probó el camino de error (sin Bebop conectado, aborta limpio en el ping) — ver más abajo |
| [`monitor_cpu_bebop.sh`](monitor_cpu_bebop.sh) | M5 de `PLAN_CAMPANA.md` §3: lee `/proc/stat` a 1 Hz y calcula %CPU, `cpu.csv` a la salida — corre **en el Bebop por telnet**, en paralelo a `arnes_baseline.py` en el portátil | **No.** Se probó la lógica de calculo contra `/proc/stat` de este portátil — ver más abajo |

## Qué SÍ se verificó hoy (2026-09-17), sin Bebop

- El script es sintácticamente válido (`bash -n`) y ejecutable.
- El camino de "no hay Bebop conectado" funciona: si `ping` a la IP no responde, aborta
  con el mensaje exacto que pide `PLAN_CAMPANA.md` §1 ("si telnet no responde, anotarlo y
  parar") y no deja nada a medio escribir salvo el log del ping.
- Las herramientas que usa están instaladas en este portátil: `telnet`, `ftp`, `nc`,
  `sha256sum`, `ping` — todas confirmadas con `command -v`.
- La sintaxis de `ftp -n` con comandos por stdin funciona en este sistema (probado contra
  un puerto cerrado en `localhost`: se conecta, falla la conexión, no se cuelga).

## `monitor_cpu_bebop.sh` — probado sin el Bebop

Escrito en `/bin/sh` puro (POSIX), sin bashismos ni `awk`/`python`: el Día 0 todavía no
confirmó que este Bebop tenga Python, así que no se asume. Solo `read` y aritmética de
shell (`$(( ))`), que están en cualquier BusyBox `ash`.

Probado el 2026-09-17 con `sh` (no `bash`) contra `/proc/stat` **de este portátil**
(mismo formato de `/proc/stat` que cualquier kernel Linux, incluido el del Bebop 1):
calcula porcentajes de CPU plausibles (2-4 % en este portátil casi inactivo), sin
errores de sintaxis ni de aritmética. `NO VERIFICADO`: que la salida de `/proc/stat` del
kernel del Bebop tenga el mismo número de campos (los kernels muy viejos a veces no
traen `iowait`/`irq`/`softirq` — si faltan, `read` los deja vacíos y la aritmética con un
campo vacío falla; hay que probarlo contra el Bebop real antes de confiar en la primera
fila de `cpu.csv`).

## Qué NO se puede verificar sin un Bebop de verdad

- Si el `telnet` de BusyBox del Bebop acepta el bloque de comandos completo por un pipe
  sin esperar el prompt de cada uno (funciona así en la mayoría de BusyBox `ash`, pero
  `NO VERIFICADO` en este Bebop concreto).
- Si el servidor FTP anónimo responde en este Bebop, y si las rutas
  `/data/ftp/internal_000/APM/CFG/` existen tal cual (son las que trae
  `PLAN_CAMPANA.md` §1.1, citadas de la documentación de ArduPilot leída el 2026-09-15;
  `NO VERIFICADO` en este dron).
- Todo lo demás de §1.3 (qué decidir según lo que se vea) sigue siendo criterio humano —
  el script junta evidencia, no decide.

## Uso, el día que haya Bebop

```bash
# 1. Conectarse al WiFi del Bebop (SSID propio del dron).
# 2. Hélices quitadas (regla de PLAN_CAMPANA.md #2, vale desde el día 0 por seguridad).
cd experiments/campana_bebop
./dia0_inspeccion.sh                 # o ./dia0_inspeccion.sh <IP>, si no es 192.168.42.1
```

Si el paso de FTP falla (`NO SE PUDO copiar por FTP` en la salida), el script no inventa
otro mecanismo — imprime las alternativas que ya están en el plan (`nc`, o copiar por
telnet) y para ahí. Decidir el mecanismo real es parte de lo que dice
`PLAN_CAMPANA.md` §1.2: *"se decide ese día"*.

## Dónde queda todo

- Log de inspección y de FTP: `salidas/<fecha>/` (no se versiona, es reproducible).
- Respaldo (binario + `APM/CFG/*` + `SHA256SUMS.txt`): `../../08_cierre/bebop_backup/<fecha>/`
  — **esto sí es evidencia** (`PLAN_CAMPANA.md` §1: *"es la única copia del sistema que
  se publicó"*), no está en `.gitignore`. Decidir con Javier si el binario se comitea tal
  cual o si solo se comitea `SHA256SUMS.txt` y el binario se guarda aparte por tamaño.

## Después del Día 0

Con lo que diga §1.3 (fork viejo / stock / no arranca), lo siguiente ya no depende del
fork del proxy para la condición **A** (línea base, `arnes_baseline.py` de
[`../baseline_harness/`](../baseline_harness/) apuntando al Bebop en vez de a SITL — mismo
script, cambiar `--host`). Las condiciones **B** y **C** sí siguen en suspenso hasta que
se resuelva la arquitectura con Nicolás (ver `CLAUDE.md`).
