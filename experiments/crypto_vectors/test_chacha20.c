// test_chacha20.c -- compara chacha20.c contra los vectores generados por
// referencia_chacha20.py (ChaCha20 de la libreria `cryptography`, independiente de este
// repositorio). Ver chacha20.h y README.md para el porque de este metodo en vez de
// vectores de la RFC copiados a mano.
//
// Compilar y correr: ver README.md ("ChaCha20").
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "chacha20.h"

static size_t hex_a_bytes(const char *hex, uint8_t *out, size_t max_out) {
    if (strcmp(hex, "-") == 0) return 0;   /* placeholder de cadena vacia, ver referencia_chacha20.py */
    size_t n = strlen(hex) / 2;
    if (n > max_out) n = max_out;
    for (size_t i = 0; i < n; i++) {
        unsigned v;
        sscanf(hex + 2 * i, "%2x", &v);
        out[i] = (uint8_t)v;
    }
    return n;
}

int main(int argc, char **argv) {
    const char *ruta = (argc > 1) ? argv[1] : "vectores_chacha20.txt";
    FILE *f = fopen(ruta, "r");
    if (!f) {
        fprintf(stderr, "No se pudo abrir %s -- correr primero:\n"
                        "  python3 referencia_chacha20.py > %s\n", ruta, ruta);
        return 2;
    }

    unsigned long counter;

    int total = 0, fallos = 0;
    char linea[4096 + 512];
    while (fgets(linea, sizeof(linea), f)) {
        if (linea[0] == '#' || linea[0] == '\n') continue;

        char key_buf[128], nonce_buf[64];
        static char pt_buf[4096], ct_buf[4096];
        int leidos = sscanf(linea, "%127s %63s %lu %4095s %4095s",
                             key_buf, nonce_buf, &counter, pt_buf, ct_buf);
        if (leidos != 5) {
            fprintf(stderr, "Linea mal formada, se salta: %s", linea);
            continue;
        }

        uint8_t key[32], nonce[12];
        static uint8_t pt[2048], ct_esperado[2048], ct_obtenido[2048];
        hex_a_bytes(key_buf, key, sizeof(key));
        hex_a_bytes(nonce_buf, nonce, sizeof(nonce));
        size_t n_pt = hex_a_bytes(pt_buf, pt, sizeof(pt));
        size_t n_ct = hex_a_bytes(ct_buf, ct_esperado, sizeof(ct_esperado));

        total++;
        if (n_pt != n_ct) {
            fallos++;
            printf("[FAIL] caso %d: longitudes de texto claro/cifrado no coinciden\n", total);
            continue;
        }

        chacha20_xor(key, nonce, (uint32_t)counter, pt, ct_obtenido, n_pt);

        if (memcmp(ct_obtenido, ct_esperado, n_pt) == 0) {
            printf("[OK]   caso %d (counter=%lu, %zu B)\n", total, counter, n_pt);
        } else {
            fallos++;
            printf("[FAIL] caso %d (counter=%lu, %zu B)\n", total, counter, n_pt);
        }
    }
    fclose(f);

    printf("\n%d/%d OK\n", total - fallos, total);
    return fallos == 0 ? 0 : 1;
}
