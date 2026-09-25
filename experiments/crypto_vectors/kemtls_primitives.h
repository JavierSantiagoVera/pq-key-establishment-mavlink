// kemtls_primitives.h -- copia textual de las funciones de derivacion de clave de
// GCS_KEMTLS.cpp:153-209 (firmware-fork/libraries/
// GCS_MAVLink/GCS_KEMTLS.cpp), sin la palabra 'static' para poder enlazarlas desde este
// arnes de pruebas. Ver README.md de esta carpeta para el porque de la copia en vez de
// enlazar el .cpp original (depende del HAL de ArduPilot, no compila suelto).
//
// sha256() SI es la funcion real: se compila y enlaza sin modificar
// libraries/AP_KEM/vendor/pqclean/common/sha2.c, que no depende del HAL.
#pragma once
#include <cstdint>
#include <cstddef>

extern "C" void sha256(uint8_t *out, const uint8_t *in, size_t inlen);

void hmac_sha256(const uint8_t *key, size_t klen,
                  const uint8_t *msg, size_t mlen,
                  uint8_t out[32]);

// HKDF-Extract(salt, IKM) -> PRK  (RFC 5869 #2.2, sha256 como hash)
void hkdf_extract(const uint8_t salt[32], const uint8_t *ikm, size_t ikm_len,
                   uint8_t prk_out[32]);

// Expand de una sola ronda con etiqueta de dominio ("ardupilot-hqc-v1:" + label +
// context), NO es el HKDF-Expand generico de RFC 5869 (que itera con un contador para
// L > tamano de hash) -- aqui L esta topado a 32 B, que es exactamente un bloque de
// SHA-256, asi que basta una ronda. Documentado como construccion propia del proyecto
// en README.md; se prueba por comparacion cruzada, no contra un vector oficial.
void hkdf_expand_label(const uint8_t prk[32],
                        const char *label, const uint8_t *context, size_t ctx_len,
                        uint8_t *out, size_t L);
