// chacha20.h -- ChaCha20 (RFC 8439), implementado desde cero porque no existe en el
// repositorio (mavlink_cipher.h, de donde saldria en el firmware real, no esta en el
// snapshot -- ver README.md de esta carpeta). NO es una copia de codigo del proyecto:
// es una implementacion nueva, escrita para (a) enlazarla a
// ../nonce_correction/ y demostrar con bytes reales que la construccion corregida no
// repite keystream, y (b) medir su costo de CPU en ../energy_cpu_bound/ (causa C4).
//
// Validada por comparacion diferencial contra el ChaCha20 de la libreria `cryptography`
// de Python (referencia_chacha20.py), no contra vectores tecleados a mano -- ver README.md
// sobre por que (un vector RFC mal transcrito ya causo un 0/7 falso en este mismo repo).
#pragma once
#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// key: 32 B. nonce: 12 B (RFC 8439, formato de 96 bits). counter: contador de bloque de
// 32 bits -- es EXACTAMENTE block_counter_for_offset() de nonce_ctr.h.
// out debe tener espacio para len bytes; in y out pueden apuntar al mismo buffer.
void chacha20_xor(const uint8_t key[32], const uint8_t nonce[12], uint32_t counter,
                   const uint8_t *in, uint8_t *out, size_t len);

// Un solo bloque de 64 B de keystream (sin XOR) -- lo usa chacha20_xor() y sirve para
// probar el desplazamiento de bloque de forma aislada.
void chacha20_block(const uint8_t key[32], const uint8_t nonce[12], uint32_t counter,
                     uint8_t out[64]);

#ifdef __cplusplus
}
#endif
