/*
 * randombytes_linux.c — PARCHEADO (hallazgo A8)
 *
 * PROBLEMA ORIGINAL
 *   La firma exigida por PQClean/NIST es `void randombytes(unsigned char*, unsigned long long)`,
 *   sin canal de error. La version original, ante fallo de getrandom() y de /dev/urandom,
 *   ejecutaba `break` y RETORNABA dejando el bufer parcialmente lleno o SIN INICIALIZAR,
 *   sin senalar nada al llamador. Ese bufer alimenta la generacion de claves del KEM:
 *   un fallo de entropia se convertia en material de clave predecible, en silencio.
 *
 * POR QUE NO SE USA abort()
 *   Esto corre en el controlador de vuelo. Abortar el proceso en vuelo es inaceptable:
 *   convierte un fallo de seguridad en un fallo de seguridad fisica (perdida de la aeronave).
 *   La respuesta correcta es DEGRADAR EL HANDSHAKE, no la aeronave.
 *
 * DISENO DEL PARCHE
 *   1. Se conserva la firma exigida por PQClean.
 *   2. Se marca un flag "sticky" cuando la entropia falla o queda incompleta.
 *   3. El bufer se pone a cero ante fallo (no se deja memoria residual como "aleatorio").
 *   4. ap_kem_* consulta el flag y hace fallar la operacion, de modo que la sesion
 *      transita a FAIL por la logica ya existente en la maquina de estados.
 *
 *   El flag es sticky a proposito: una vez que la fuente de entropia fallo en este arranque,
 *   no se vuelve a confiar en ella hasta reiniciar. Es preferible quedarse sin canal seguro
 *   que operar con uno cuya aleatoriedad no se puede justificar.
 */

#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/types.h>
#if defined(__linux__)
#include <sys/random.h>
#endif

#include "randombytes_status.h"

/* 0 = la entropia ha sido correcta en todas las llamadas de este arranque. */
static volatile int s_entropy_failed = 0;

int ap_kem_entropy_failed(void)
{
    return s_entropy_failed;
}

void ap_kem_entropy_reset_for_test(void)
{
    s_entropy_failed = 0;
}

/* Firma fija impuesta por PQClean/NIST SUPERCOP. */
void randombytes(unsigned char *x, unsigned long long xlen)
{
    unsigned char *out = x;
    unsigned long long want = xlen;

    if (x == NULL || xlen == 0) {
        return;
    }

#if defined(__linux__)
    while (xlen > 0) {
        ssize_t n = getrandom(x, (size_t)xlen, 0);
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            break;              /* se intenta el respaldo /dev/urandom */
        }
        if (n == 0) {
            break;              /* sin progreso: evita bucle infinito */
        }
        x += n;
        xlen -= (unsigned long long)n;
    }
    if (xlen == 0) {
        return;                 /* exito por getrandom() */
    }
#endif

    {
        int fd = open("/dev/urandom", O_RDONLY);
        if (fd >= 0) {
            while (xlen > 0) {
                ssize_t n = read(fd, x, (size_t)xlen);
                if (n < 0) {
                    if (errno == EINTR) {
                        continue;
                    }
                    break;
                }
                if (n == 0) {
                    break;      /* EOF inesperado en /dev/urandom */
                }
                x += n;
                xlen -= (unsigned long long)n;
            }
            close(fd);
        }
    }

    if (xlen != 0) {
        /*
         * FALLO DE ENTROPIA. Diferencia clave con la version original:
         *   - se borra TODO el bufer (nada de memoria residual pasando por aleatoria);
         *   - se marca el fallo para que ap_kem_* aborte la operacion criptografica.
         */
        memset(out, 0, (size_t)want);
        s_entropy_failed = 1;
    }
}
