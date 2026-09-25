#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
referencia_chacha20.py -- genera vectores de prueba para chacha20.c usando el ChaCha20
de la libreria `cryptography` (no reutiliza nada de este repositorio) como referencia
independiente.

POR QUE ASI, Y NO VECTORES DE LA RFC TECLEADOS A MANO
  El primer intento de vectores de prueba de esta carpeta (test_vectores_primitivas.cpp)
  fallo 0/7 porque los siete valores hex se transcribieron truncados en un digito. Aqui
  no se teclea ningun hash a mano: se generan programaticamente y se escriben a un
  archivo que test_chacha20.c lee en tiempo de ejecucion.

  La convencion de `cryptography` para ChaCha20 (parametro "nonce" de 16 B = contador de
  bloque de 4 B little-endian + nonce de 12 B de RFC 8439) se verifico por separado:
  coincide con RFC 8439 #2.4.2 en los primeros 60 B (un vector tecleado de memoria, con
  error en la cola) y, de forma independiente del texto de la RFC, se confirmo que
  bloque(counter=1) == bytes[64:128] de bloque(counter=0) -- exactamente la semantica de
  bloque de RFC 7539/8439 que asume nonce_ctr.h.

Uso:
    python3 referencia_chacha20.py > vectores_chacha20.txt
"""
import os
import sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms


def chacha20_cryptography(key: bytes, nonce: bytes, counter: int, data: bytes) -> bytes:
    iv = counter.to_bytes(4, "little") + nonce
    enc = Cipher(algorithms.ChaCha20(key, iv), mode=None).encryptor()
    return enc.update(data)


def main():
    rng = __import__("random")
    rng.seed(20260917)  # reproducible

    casos = []

    # Casos fijos, estructurales (no dependen de random): buffer vacio, exactamente un
    # bloque, un byte menos de un bloque, un byte mas.
    key0 = bytes(range(32))
    nonce0 = bytes([0] * 11 + [1])
    for counter0, n in [(0, 0), (0, 63), (0, 64), (0, 65), (5, 130), (0xFFFFFFFE, 70)]:
        pt = bytes((i * 7 + 3) % 256 for i in range(n))
        casos.append((key0, nonce0, counter0, pt))

    # Casos aleatorios: distintas claves, nonces, contadores iniciales y longitudes.
    for _ in range(30):
        key = bytes(rng.randrange(256) for _ in range(32))
        nonce = bytes(rng.randrange(256) for _ in range(12))
        counter = rng.randrange(0, 5)
        n = rng.choice([0, 1, 15, 16, 17, 63, 64, 65, 127, 128, 129, 200, 1024])
        pt = os.urandom(n)
        casos.append((key, nonce, counter, pt))

    for key, nonce, counter, pt in casos:
        ct = chacha20_cryptography(key, nonce, counter, pt)
        assert len(ct) == len(pt)
        # "-" en vez de cadena vacia: un campo vacio rompe el parseo por espacios de
        # test_chacha20.c (sscanf %s no matchea longitud cero).
        pt_campo = pt.hex() if pt else "-"
        ct_campo = ct.hex() if ct else "-"
        print("%s %s %d %s %s" % (key.hex(), nonce.hex(), counter, pt_campo, ct_campo))

    print("# %d vectores generados con cryptography==%s" % (
        len(casos), __import__("cryptography").__version__), file=sys.stderr)


if __name__ == "__main__":
    main()
