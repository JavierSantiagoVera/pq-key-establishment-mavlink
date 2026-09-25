#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
referencia_hkdf_expand_label.py -- segunda implementacion, independiente, de
hkdf_expand_label (GCS_KEMTLS.cpp:187-209) para la comparacion cruzada de
test_vectores_primitivas.cpp. Usa solo hashlib/hmac de la biblioteca estandar
de Python (no reutiliza nada de este repositorio).

Reproduce el valor "want" de test_hkdf_expand_label_cruzado(). Si algun dia
cambia el vector fijo en el .cpp, este script se corre de nuevo para
recalcularlo -- no se edita el hex a mano.
"""
import hashlib
import hmac


def hkdf_expand_label(prk: bytes, label: str, context: bytes, length: int) -> bytes:
    assert length <= 32, "esta construccion solo cubre L <= tamano de SHA-256"
    prefix = b"ardupilot-hqc-v1:"
    info = prefix + label.encode() + context + bytes([0x01])
    t = hmac.new(prk, info, hashlib.sha256).digest()
    return t[:length]


def main():
    prk = bytes(range(32))
    label = "test-label"
    context = bytes([0x01, 0x02, 0x03, 0x04])
    out = hkdf_expand_label(prk, label, context, 32)
    print("prk    =", prk.hex())
    print("label  =", label)
    print("ctx    =", context.hex())
    print("out    =", out.hex())


if __name__ == "__main__":
    main()
