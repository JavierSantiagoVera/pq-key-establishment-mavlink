// randombytes() para PQClean, usando el generador de numeros aleatorios POR HARDWARE
// de la ESP32 (esp_fill_random(), periferico RNG real integrado en el chip) -- a
// diferencia de randombytes_pico.c (proyecto hermano en hqc_encaps_pico/), que usa un
// PRNG por software porque el RP2040 no trae un TRNG dedicado. No es el randombytes_linux.c
// auditado en gap_analysis.md (A8) ni su parche en ../rng_patch/ -- no lo reemplaza ni lo
// valida, es solo el generador de entropia minimo para este banco de pruebas.

#include <stdint.h>
#include <stddef.h>
#include "esp_random.h"
#include "randombytes.h" // renombra a PQCLEAN_randombytes via macro, igual que llaman hqc.c/kem.c

int randombytes(uint8_t *output, size_t n) {
    esp_fill_random(output, n);
    return 0;
}
