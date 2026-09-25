#!/bin/sh
# monitor_cpu_bebop.sh -- M5 de PLAN_CAMPANA.md #3 ("CPU del Bebop, /proc/stat a 1 Hz").
#
# CORRE EN EL BEBOP POR TELNET, no en el portatil -- por eso es /bin/sh puro (POSIX),
# sin bashismos ni awk/python: el Dia 0 (dia0_inspeccion.sh) todavia no confirmo que
# haya python en este Bebop concreto, asi que no se asume. Solo usa `read` y aritmetica
# de shell ($(( ))), que estan en cualquier busybox ash.
#
# NO VERIFICADO contra un Bebop real todavia -- se escribio sin acceso a uno (igual que
# dia0_inspeccion.sh). Se probo la logica de calculo contra /proc/stat de este portatil
# (Linux x86, formato de /proc/stat identico al de cualquier kernel Linux moderno,
# incluido el del Bebop 1) -- ver README.md "Probado sin el Bebop".
#
# Uso (por telnet, en el propio Bebop):
#   ./monitor_cpu_bebop.sh 300 > cpu.csv &     # 300 s = un bloque de PLAN_CAMPANA.md #2
#   ... correr el bloque de medida desde el portatil (arnes_baseline.py) ...
#   wait
#
# Salida: CSV con cabecera, una fila por segundo: timestamp_epoch,cpu_pct
# (mismo nombre de archivo, cpu.csv, que pide PLAN_CAMPANA.md #5 en el layout de datos).

duracion="${1:-60}"

leer_stat() {
    # Primera linea de /proc/stat: "cpu  user nice system idle iowait irq softirq ..."
    # read descarta campos de mas si /proc/stat trae steal/guest (kernels nuevos). Si el
    # kernel es viejo y trae MENOS campos (sin iowait/irq/softirq), read los deja vacios
    # -- ${var:-0} los trata como 0 en vez de romper la aritmetica.
    read -r _cpu user nice system idle iowait irq softirq _resto < /proc/stat
    user=${user:-0}; nice=${nice:-0}; system=${system:-0}; idle=${idle:-0}
    iowait=${iowait:-0}; irq=${irq:-0}; softirq=${softirq:-0}
    total=$((user + nice + system + idle + iowait + irq + softirq))
    ocupado=$((total - idle - iowait))
    echo "$total $ocupado"
}

echo "timestamp_epoch,cpu_pct"

set -- $(leer_stat)
total_prev=$1
ocupado_prev=$2

i=0
while [ "$i" -lt "$duracion" ]; do
    sleep 1
    set -- $(leer_stat)
    total_cur=$1
    ocupado_cur=$2

    d_total=$((total_cur - total_prev))
    d_ocupado=$((ocupado_cur - ocupado_prev))

    if [ "$d_total" -gt 0 ]; then
        pct=$(( (d_ocupado * 1000 / d_total + 5) / 10 ))  # x10 para redondear, sin floats
    else
        pct=0
    fi

    ts=$(date +%s 2>/dev/null || echo "$i")
    echo "${ts},${pct}"

    total_prev=$total_cur
    ocupado_prev=$ocupado_cur
    i=$((i + 1))
done
