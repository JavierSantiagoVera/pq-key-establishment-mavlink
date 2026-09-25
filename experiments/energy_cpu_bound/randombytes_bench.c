// randombytes() para este banco de pruebas (x86 de referencia y ARM cross-compilado
// para el Bebop), implementando la firma que exige common/randombytes.h de PQClean
// (int randombytes(uint8_t*, size_t)) -- DISTINTA de la firma NIST/SUPERCOP
// (void randombytes(unsigned char*, unsigned long long)) que usa el
// randombytes_linux.c auditado en gap_analysis.md (A8) y parcheado en rng_patch/.
//
// Esto NO es ese archivo, no lo reemplaza y no hereda su parche -- es solo el
// generador de entropia minimo para poder correr crypto_kem_keypair/enc en este
// microbenchmark. Analogo a randombytes_pico.c en experiments/hqc_encaps_pico/.

#include <stdint.h>
#include <stddef.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#if defined(__linux__)
#include <sys/random.h>
#endif
#include "randombytes.h" // renombra a PQCLEAN_randombytes via macro, igual que llaman hqc.c/kem.c

int randombytes(uint8_t *output, size_t n) {
    size_t hecho = 0;
#if defined(__linux__)
    while (hecho < n) {
        ssize_t r = getrandom(output + hecho, n - hecho, 0);
        if (r < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (r == 0) break;
        hecho += (size_t)r;
    }
    if (hecho == n) return 0;
#endif
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd < 0) return -1;
    while (hecho < n) {
        ssize_t r = read(fd, output + hecho, n - hecho);
        if (r <= 0) { close(fd); return -1; }
        hecho += (size_t)r;
    }
    close(fd);
    return 0;
}
