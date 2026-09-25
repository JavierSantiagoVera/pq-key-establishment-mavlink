// randombytes() para el RP2040, usando pico_rand (SDK oficial) como fuente.
//
// Esto NO es el randombytes_linux.c que se audito en 03_review/gap_analysis.md (A8) --
// es una implementacion nueva, solo para este banco de pruebas de ciclos en la Pico.
// No reemplaza nada del firmware del fork ni se propone como tal.
//
// pico_rand mezcla ROSC + timer + contador de bus (ver pico/rand.h) para sembrar un PRNG
// de 128 bits en software. Alcanza para un benchmark de tiempos (no estamos midiendo
// seguridad de la clave generada, solo cuanto tarda encapsular), pero se declara así de
// explicito para no confundirlo con una fuente de entropia validada para uso real.

#include <string.h>
#include "pico/rand.h"
#include "randombytes.h"

int randombytes(uint8_t *output, size_t n) {
    size_t escrito = 0;
    while (escrito < n) {
        rng_128_t r;
        get_rand_128(&r);
        size_t quedan = n - escrito;
        size_t copiar = quedan < sizeof(r.r) ? quedan : sizeof(r.r);
        memcpy(output + escrito, r.r, copiar);
        escrito += copiar;
    }
    return 0;
}
