#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cuenta instrucciones ARM (Thumb-2) EJECUTADAS DINAMICAMENTE, no solo bloques de
traduccion, cruzando dos logs de qemu-arm-static:

  - log de -d in_asm,nochain  -> disassembly ESTATICO de cada bloque unico (una vez)
  - log de -d exec,nochain    -> traza de EJECUCION (cada visita a un bloque, incluye
                                  repeticiones por bucles)

Thumb-2 tiene instrucciones de 16 o 32 bits. Regla estandar: si los 5 bits superiores
del primer halfword (bits 15:11) valen 0b11101/0b11110/0b11111 (>=0x1D), es el primer
halfword de una instruccion de 32 bits; si no, es una instruccion completa de 16 bits.
Verificado contra objdump que el binario es Thumb-2 (arm-none-linux-gnueabihf-gcc sin
-mthumb todavia genera Thumb por defecto en este toolchain).
"""
import sys
import re
import collections

def instrucciones_en_bytes(data: bytes) -> int:
    n = 0
    i = 0
    L = len(data)
    while i + 1 < L:
        h0 = data[i] | (data[i + 1] << 8)
        top5 = (h0 >> 11) & 0x1F
        if top5 in (0x1D, 0x1E, 0x1F) and i + 3 < L:
            i += 4
        else:
            i += 2
        n += 1
    return n


def parse_in_asm(path):
    """-> dict direccion_hex_int -> num_instrucciones_estaticas_del_bloque"""
    bloques = {}
    addr = None
    hexbuf = []
    with open(path, "r", errors="replace") as f:
        for line in f:
            m = re.match(r"^0x([0-9a-fA-F]+):", line)
            if m:
                if addr is not None and hexbuf:
                    bloques[addr] = instrucciones_en_bytes(bytes.fromhex("".join(hexbuf)))
                addr = int(m.group(1), 16)
                hexbuf = []
                continue
            m2 = re.match(r"^OBJD-T:\s*([0-9a-fA-F]+)", line)
            if m2 and addr is not None:
                hexbuf.append(m2.group(1))
        if addr is not None and hexbuf:
            bloques[addr] = instrucciones_en_bytes(bytes.fromhex("".join(hexbuf)))
    return bloques


def parse_exec_counts(path):
    """-> Counter direccion_hex_int -> veces_ejecutado"""
    cnt = collections.Counter()
    pat = re.compile(r"^Trace \d+: 0x[0-9a-fA-F]+ \[[0-9a-fA-F]+/([0-9a-fA-F]+)/")
    with open(path, "r", errors="replace") as f:
        for line in f:
            m = pat.match(line)
            if m:
                cnt[int(m.group(1), 16)] += 1
    return cnt


def main():
    if len(sys.argv) != 3:
        print("uso: contar_instrucciones_arm.py <log_in_asm> <log_exec>")
        return 1
    estatico = parse_in_asm(sys.argv[1])
    dinamico = parse_exec_counts(sys.argv[2])

    total_instrucciones = 0
    total_tbs_ejecutados = 0
    sin_disasm = 0
    for addr, veces in dinamico.items():
        total_tbs_ejecutados += veces
        ninst = estatico.get(addr)
        if ninst is None:
            sin_disasm += veces
            continue
        total_instrucciones += ninst * veces

    print(f"bloques unicos con disassembly : {len(estatico)}")
    print(f"bloques unicos ejecutados      : {len(dinamico)}")
    print(f"ejecuciones de bloque (total)  : {total_tbs_ejecutados}")
    print(f"ejecuciones sin disassembly    : {sin_disasm}  (deberia ser 0 o casi 0)")
    print(f"INSTRUCCIONES DINAMICAS TOTAL  : {total_instrucciones}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
