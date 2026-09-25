// benchmark_cpu.cpp -- cota superior analitica de costo de CPU de las primitivas
// criptograficas, tal como pide ../energy_reanalysis/FORENSICS_energia.md (causa C4)
// en vez de una medicion de sistema (bateria) que ya se demostro irrecuperable.
//
// QUE MIDE
//   SHA-256 (real, enlazado), HMAC-SHA256 y HKDF (copia textual de GCS_KEMTLS.cpp,
//   ver ../crypto_vectors/README.md) y ChaCha20 (implementacion nueva, validada por
//   comparacion diferencial, ver ../crypto_vectors/README.md), sobre tamanos de
//   payload representativos de MAVLink: HEARTBEAT (9 B), COMMAND_LONG (33 B), un
//   tamano medio (64 B), el payload maximo de un solo frame MAVLink v2 (255 B,
//   MAVLINK_MAX_PAYLOAD_LEN) y 1024 B (mas alla de un frame, referencia de escalado).
//
// QUE NO MIDE
//   Esto corre en el CPU x86 del portatil (Ryzen), NO en el ARM Cortex-A9 del Bebop.
//   Sirve para (a) validar que el metodo funciona y (b) dar el costo RELATIVO entre
//   primitivas (cuanto mas cuesta ChaCha20 que SHA-256, etc.), que no deberia cambiar
//   demasiado entre arquitecturas para primitivas sin aceleracion por hardware. NO
//   sirve como cifra absoluta para el articulo -- para eso hace falta compilar esto
//   mismo con un cross-compiler ARM y correrlo en el Bebop por telnet (ver README.md,
//   "Para correrlo en el Bebop").
//
// Compilar y correr: ver README.md.
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <vector>
#include <algorithm>
#include <chrono>

#include "../crypto_vectors/kemtls_primitives.h"
#include "../crypto_vectors/chacha20.h"

extern "C" {
#include "../../firmware-fork/libraries/AP_KEM/vendor/pqclean/crypto_kem/hqc-128/clean/api.h"
}

using Clock = std::chrono::steady_clock;

static double ns_de(Clock::duration d) {
    return std::chrono::duration<double, std::nano>(d).count();
}

static double percentil(std::vector<double> &v, double p) {
    std::sort(v.begin(), v.end());
    size_t k = (size_t)((p / 100.0) * (v.size() - 1));
    return v[k];
}

struct Resumen { double p50, p95, mediana_bytes_por_s; };

/* Corre f() N veces, midiendo el tiempo de CADA llamada por separado (no un promedio
 * de un lote), para poder sacar p50/p95 en vez de solo la media -- misma disciplina
 * que arnes_baseline.py. */
template <typename F>
static Resumen medir(F f, int n, size_t bytes_por_llamada) {
    std::vector<double> muestras_ns;
    muestras_ns.reserve(n);
    for (int i = 0; i < n; i++) {
        auto t0 = Clock::now();
        f();
        auto t1 = Clock::now();
        muestras_ns.push_back(ns_de(t1 - t0));
    }
    Resumen r;
    r.p50 = percentil(muestras_ns, 50);
    r.p95 = percentil(muestras_ns, 95);
    r.mediana_bytes_por_s = bytes_por_llamada / (r.p50 / 1e9);
    return r;
}

static void imprimir(const char *primitiva, size_t bytes, const Resumen &r) {
    printf("  %-14s %5zu B   p50=%8.1f ns   p95=%8.1f ns   %8.1f MB/s\n",
           primitiva, bytes, r.p50, r.p95, r.mediana_bytes_por_s / 1e6);
}

int main(int argc, char **argv) {
    int n = (argc > 1) ? atoi(argv[1]) : 20000;
    size_t tamanos[] = {9, 33, 64, 255, 1024};
    printf("== Costo de CPU de las primitivas, n=%d por punto ==\n", n);
    printf("(x86 del portatil -- NO es el ARM del Bebop, ver README.md)\n\n");

    uint8_t key32[32]; for (int i = 0; i < 32; i++) key32[i] = (uint8_t)i;
    uint8_t nonce12[12] = {0};
    std::vector<uint8_t> buf(4096), out(4096);
    for (size_t i = 0; i < buf.size(); i++) buf[i] = (uint8_t)(i * 7 + 1);

    for (size_t tam : tamanos) {
        uint8_t hash_out[32];
        auto r = medir([&]() { sha256(hash_out, buf.data(), tam); }, n, tam);
        imprimir("SHA-256", tam, r);
    }
    printf("\n");
    for (size_t tam : tamanos) {
        uint8_t mac_out[32];
        auto r = medir([&]() { hmac_sha256(key32, 32, buf.data(), tam, mac_out); }, n, tam);
        imprimir("HMAC-SHA256", tam, r);
    }
    printf("\n");
    for (size_t tam : tamanos) {
        uint8_t prk[32], okm[32];
        auto r = medir([&]() {
            hkdf_extract(key32, buf.data(), tam, prk);
            hkdf_expand_label(prk, "bench", buf.data(), 4, okm, 32);
        }, n, tam);
        imprimir("HKDF (E+expand)", tam, r);
    }
    printf("\n");
    for (size_t tam : tamanos) {
        auto r = medir([&]() { chacha20_xor(key32, nonce12, 0, buf.data(), out.data(), tam); }, n, tam);
        imprimir("ChaCha20", tam, r);
    }

    printf("\nCota superior por mensaje (SHA-256 + HMAC + HKDF-expand + ChaCha20, 33 B, "
           "el tamano de COMMAND_LONG):\n");
    {
        uint8_t hash_out[32], mac_out[32], prk[32], okm[32];
        size_t tam = 33;
        auto r = medir([&]() {
            sha256(hash_out, buf.data(), tam);
            hmac_sha256(key32, 32, buf.data(), tam, mac_out);
            hkdf_extract(key32, buf.data(), tam, prk);
            hkdf_expand_label(prk, "bench", buf.data(), 4, okm, 32);
            chacha20_xor(key32, nonce12, 0, buf.data(), out.data(), tam);
        }, n, tam);
        printf("  p50=%.1f ns  p95=%.1f ns  (referencia x86, ver README.md antes de citar)\n",
               r.p50, r.p95);
    }

    // HQC-128 (PQClean, referencia "clean", sin modificar) -- la operacion que el FC
    // SI hace en este diseno es la encapsulacion, no la decapsulacion (esa es de la
    // GCS). Mismo patron que experiments/hqc_encaps_pico/main.c, pero aqui corriendo
    // sobre Linux (x86 de referencia, o ARM del Bebop al cross-compilar), no bare-metal.
    printf("\n== HQC-128 (PQClean clean) -- encapsulacion aislada ==\n");
    {
        static uint8_t pk[PQCLEAN_HQC128_CLEAN_CRYPTO_PUBLICKEYBYTES];
        static uint8_t sk[PQCLEAN_HQC128_CLEAN_CRYPTO_SECRETKEYBYTES];
        static uint8_t ct[PQCLEAN_HQC128_CLEAN_CRYPTO_CIPHERTEXTBYTES];
        static uint8_t ss[PQCLEAN_HQC128_CLEAN_CRYPTO_BYTES];

        auto t0 = Clock::now();
        int rc = PQCLEAN_HQC128_CLEAN_crypto_kem_keypair(pk, sk);
        auto t1 = Clock::now();
        if (rc != 0) {
            fprintf(stderr, "ERROR: crypto_kem_keypair devolvio %d\n", rc);
            return 1;
        }
        printf("  keypair (una vez, informativo): %.1f us\n", ns_de(t1 - t0) / 1000.0);

        int n_hqc = n > 2000 ? 2000 : n; // HQC es mucho mas caro por llamada que las
                                          // primitivas de arriba; 2000 alcanza para
                                          // percentiles estables sin correr minutos.
        auto r = medir([&]() {
            int rc2 = PQCLEAN_HQC128_CLEAN_crypto_kem_enc(ct, ss, pk);
            if (rc2 != 0) { fprintf(stderr, "ERROR encaps rc=%d\n", rc2); exit(1); }
        }, n_hqc, PQCLEAN_HQC128_CLEAN_CRYPTO_CIPHERTEXTBYTES);
        printf("  encapsulacion, n=%d: p50=%.1f us  p95=%.1f us\n",
               n_hqc, r.p50 / 1000.0, r.p95 / 1000.0);
        printf("  (aislada, sin MAVLink/ArduPilot alrededor -- ver README.md antes de citar)\n");
    }
    return 0;
}
