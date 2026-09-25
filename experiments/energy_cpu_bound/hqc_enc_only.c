// Programa minimo: SOLO keypair (una vez) + N encapsulaciones de HQC-128 (PQClean,
// referencia "clean", sin modificar). Nada de SHA-256/HMAC/HKDF/ChaCha20 -- el proposito
// es que el conteo de instrucciones/bloques de traduccion de todo el proceso corresponda
// casi enteramente a esta operacion, no a las primitivas simetricas del banco principal
// (benchmark_cpu.cpp).
//
// Compilar para x86 (referencia, conteo real de instrucciones con perf):
//   gcc -std=c11 -O2 -I"$HQC" -I"$COMMON" -o hqc_enc_only_x86 hqc_enc_only.c \
//       fips202.o randombytes_bench.o hqc_*.o
//   perf stat -e instructions ./hqc_enc_only_x86 1
//
// Compilar para ARM (cross, conteo de bloques de traduccion bajo QEMU):
//   arm-none-linux-gnueabihf-gcc -std=c11 -O2 -static -I"$HQC" -I"$COMMON" \
//       -o hqc_enc_only_arm hqc_enc_only.c fips202_arm.o randombytes_bench_arm.o hqc_*_arm.o
//   qemu-arm-static -d exec,nochain ./hqc_enc_only_arm 1 2>log; wc -l log

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

#include "api.h"

int main(int argc, char **argv) {
    int n = (argc > 1) ? atoi(argv[1]) : 1;
    static uint8_t pk[PQCLEAN_HQC128_CLEAN_CRYPTO_PUBLICKEYBYTES];
    static uint8_t sk[PQCLEAN_HQC128_CLEAN_CRYPTO_SECRETKEYBYTES];
    static uint8_t ct[PQCLEAN_HQC128_CLEAN_CRYPTO_CIPHERTEXTBYTES];
    static uint8_t ss[PQCLEAN_HQC128_CLEAN_CRYPTO_BYTES];

    if (PQCLEAN_HQC128_CLEAN_crypto_kem_keypair(pk, sk) != 0) {
        fprintf(stderr, "ERROR keypair\n");
        return 1;
    }
    for (int i = 0; i < n; i++) {
        if (PQCLEAN_HQC128_CLEAN_crypto_kem_enc(ct, ss, pk) != 0) {
            fprintf(stderr, "ERROR encapsulacion en i=%d\n", i);
            return 1;
        }
    }
    printf("OK: keypair + %d encapsulacion(es)\n", n);
    return 0;
}
