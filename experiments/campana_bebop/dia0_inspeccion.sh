#!/usr/bin/env bash
# dia0_inspeccion.sh -- automatiza 08_cierre/PLAN_CAMPANA.md #1 ("Dia 0 -- inspeccionar
# el Bebop sin cambiar nada"): conecta por telnet, corre el bloque de comandos de #1.1,
# y respalda /usr/bin/arducopter + APM/CFG/* con su SHA-256 antes de tocar nada.
#
# NO VERIFICADO contra un Bebop real todavia -- se escribio sin acceso a uno. Antes de
# creerle, revisar el log que deja en salidas/<fecha>/ y comparar a mano con lo que
# hubiera dado copiando y pegando los comandos de PLAN_CAMPANA.md #1.1 uno por uno.
# Si algo falla (telnet no arranca el shell, ftp no responde), el plan ya dice que ese
# mecanismo "se decide ese dia" -- este script no inventa uno que no este documentado.
#
# REGLA DURA (PLAN_CAMPANA.md #1): no se sustituye nada del dron sin respaldarlo antes.
#
# Uso:
#   ./dia0_inspeccion.sh [IP_BEBOP]      # default 192.168.42.1
#
# Requisitos: estar conectado al WiFi del Bebop. Este script solo LEE (uname, ps, ls,
# strings, which, cat, netstat) y COPIA archivos -- no escribe ni borra nada en el Bebop.
set -u

IP="${1:-192.168.42.1}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FECHA="$(date +%Y%m%d_%H%M%S)"
SALIDA="$AQUI/salidas/$FECHA"
mkdir -p "$SALIDA"

echo "=== Dia 0 -- inspeccion del Bebop en $IP ==="
echo "Salida en: $SALIDA"
echo

echo "[0] Conectividad ..."
if ! ping -c 2 -W 2 "$IP" > "$SALIDA/00_ping.txt" 2>&1; then
    echo "ABORTA: no hay respuesta de $IP. Revisar que estas conectado al WiFi del Bebop."
    echo "        (PLAN_CAMPANA.md #1: 'si telnet no responde, anotarlo y parar. No se improvisa.')"
    cat "$SALIDA/00_ping.txt"
    exit 1
fi
echo "    OK"

echo "[1] Inspeccion por telnet (PLAN_CAMPANA.md #1.1) ..."
# Bloque EXACTO de PLAN_CAMPANA.md #1.1, con separadores para poder recortar la salida
# de cada comando del log. BusyBox ash normalmente no necesita esperar el prompt entre
# comandos para aceptar el siguiente por el pipe, pero por si acaso se deja un margen.
{
cat <<'CMDS'
echo ===UNAME===
uname -a
echo ===CPUINFO===
cat /proc/cpuinfo | head -20
echo ===FREE===
free
echo ===DF===
df -h
echo ===PROCESOS===
ps | grep -i -e ardu -e dragon
echo ===ARCHIVOS===
ls -la /usr/bin/arducopter /data/ftp/internal_000/APM/ /data/ftp/internal_000/APM/CFG/
echo ===FORK_VIEJO===
strings /usr/bin/arducopter | grep -c "ardupilot-hqc-v1"
echo ===HERRAMIENTAS===
which tcpdump tc iptables python python3 sha256sum md5sum
echo ===RPFILTER===
cat /proc/sys/net/ipv4/conf/all/rp_filter
echo ===NETSTAT===
netstat -uan
echo ===FIN===
exit
CMDS
} | timeout 30 telnet "$IP" > "$SALIDA/01_telnet_inspeccion.log" 2>&1
rc=$?
if [ $rc -ne 0 ] && [ $rc -ne 124 ]; then
    echo "    AVISO: telnet devolvio codigo $rc -- revisar $SALIDA/01_telnet_inspeccion.log a mano."
fi
if ! grep -q "===FIN===" "$SALIDA/01_telnet_inspeccion.log" 2>/dev/null; then
    echo "    AVISO: no se vio el marcador de fin. El log puede estar incompleto (prompt"
    echo "    distinto al esperado, timeout corto, o el bloque de comandos no corrio entero)."
    echo "    Revisar $SALIDA/01_telnet_inspeccion.log; si hace falta, repetir a mano con"
    echo "    'telnet $IP' y pegar los comandos de PLAN_CAMPANA.md #1.1 uno por uno."
fi
echo "    Log: $SALIDA/01_telnet_inspeccion.log"

echo
echo "[2] Fork viejo presente? (busca ===FORK_VIEJO=== seguido de un numero > 0 en el log)"
grep -A1 "===FORK_VIEJO===" "$SALIDA/01_telnet_inspeccion.log" 2>/dev/null

echo
echo "[3] Respaldo (PLAN_CAMPANA.md #1.2) -- intento por FTP anonimo ..."
BACKUP_DIR="$AQUI/../../08_cierre/bebop_backup/$FECHA"
mkdir -p "$BACKUP_DIR"
FTP_LOG="$SALIDA/02_ftp.log"
{
    echo "open $IP"
    echo "user anonymous anonymous"
    echo "binary"
    echo "lcd $BACKUP_DIR"
    echo "get /usr/bin/arducopter arducopter"
    echo "cd /data/ftp/internal_000/APM/CFG"
    echo "mget *"
    echo "bye"
} | ftp -n > "$FTP_LOG" 2>&1
echo "    Log de ftp: $FTP_LOG"

if [ -s "$BACKUP_DIR/arducopter" ]; then
    echo "    OK: arducopter copiado ($(du -h "$BACKUP_DIR/arducopter" | cut -f1))"
else
    echo "    NO SE PUDO copiar por FTP. PLAN_CAMPANA.md #1.2 dice que el mecanismo"
    echo "    'se decide ese dia' -- probar a mano, por ejemplo:"
    echo "      nc $IP 21     # ver si responde un FTP"
    echo "      telnet $IP    # y de ahi, 'cat /usr/bin/arducopter' redirigido por otra via"
    echo "    No se inventa aqui un mecanismo que no este en el plan."
fi

echo
echo "[4] SHA-256 de todo lo respaldado ..."
if [ -d "$BACKUP_DIR" ] && [ "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]; then
    ( cd "$BACKUP_DIR" && sha256sum * > SHA256SUMS.txt 2>/dev/null )
    cat "$BACKUP_DIR/SHA256SUMS.txt" 2>/dev/null
    echo "    Guardado en $BACKUP_DIR/SHA256SUMS.txt"
else
    echo "    Nada que hashear -- el respaldo no trajo archivos (ver paso [3])."
fi

echo
echo "=== Resumen ==="
echo "Log de inspeccion : $SALIDA/01_telnet_inspeccion.log"
echo "Respaldo          : $BACKUP_DIR"
echo "Revisar a mano antes de seguir -- este script NO decide si el fork esta o no,"
echo "solo junta la evidencia (PLAN_CAMPANA.md #1.3 dice que hacer segun lo que se vea)."
