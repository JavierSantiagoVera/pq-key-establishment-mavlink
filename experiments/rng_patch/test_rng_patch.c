/*
 * test_rng_patch.c -- prueba de inyeccion de fallo para el parche de RNG (hallazgo A8).
 *
 * QUE PRUEBA
 *   Que ante un fallo de la fuente de entropia el codigo parcheado (a) marca un flag
 *   sticky consultable, (b) pone a CERO todo el bufer, y (c) no se cuelga cuando la
 *   fuente devuelve 0 bytes. Y por contraste, que el codigo ORIGINAL no hace nada de
 *   eso: retorna en silencio dejando el bufer con basura.
 *
 * COMO
 *   Se incluyen primero las cabeceras del sistema, de modo que las que incluyen los
 *   .c bajo prueba queden como no-ops; despues se redefinen open/read/close a stubs.
 *   Asi los stubs afectan solo al codigo bajo prueba, no a las cabeceras.
 *
 * LIMITE DECLARADO
 *   En este host __linux__ no esta definido, asi que se ejercita la ruta de respaldo
 *   /dev/urandom, no la de getrandom(). Ambas convergen en el mismo bloque de manejo
 *   de fallo, que es lo que el parche cambia.
 *
 * Compilar y correr:
 *   gcc -std=c11 -Wall -Wextra -o test_rng_patch test_rng_patch.c && ./test_rng_patch
 */
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/types.h>

/* ------------------------------------------------------------ stubs de E/S */
static int  g_open_ok;      /* 0 => open() falla */
static int  g_read_ret;     /* bytes por lectura; -1 error, 0 EOF */
static int  g_reads_ok;     /* cuantas lecturas buenas antes de fallar */
static int  g_read_calls;

static int t_open(const char *p, int f, ...) { (void)p; (void)f;
    return g_open_ok ? 7 : -1; }
static int t_close(int fd) { (void)fd; return 0; }

static ssize_t t_read(int fd, void *buf, size_t n) {
    (void)fd;
    g_read_calls++;
    if (g_read_calls > g_reads_ok) {
        errno = EIO;
        return g_read_ret;                 /* -1 o 0, segun el caso */
    }
    size_t k = n < 4 ? n : 4;              /* relleno parcial deliberado */
    memset(buf, 0xAB, k);
    return (ssize_t)k;
}

/* ------------------------------------------- codigo bajo prueba, parcheado */
#define open  t_open
#define read  t_read
#define close t_close
#include "randombytes_linux.c"
#undef open
#undef read
#undef close

/* ---------------------------------------- codigo original, para contraste */
#define open  t_open
#define read  t_read
#define close t_close
#define randombytes randombytes_original
#include "original_randombytes_linux.c"
#undef randombytes
#undef open
#undef read
#undef close

/* ------------------------------------------------------------------ arnes */
static int fallos = 0;

static void chk(const char *nombre, int cond) {
    printf("  [%s] %s\n", cond ? "OK  " : "FALLA", nombre);
    if (!cond) { fallos++; }
}

static int todo_cero(const unsigned char *b, size_t n) {
    for (size_t i = 0; i < n; i++) { if (b[i]) { return 0; } }
    return 1;
}

static void reset(int open_ok, int reads_ok, int read_ret) {
    g_open_ok = open_ok; g_reads_ok = reads_ok;
    g_read_ret = read_ret; g_read_calls = 0;
    ap_kem_entropy_reset_for_test();
}

int main(void) {
    unsigned char buf[32];

    printf("1. Camino feliz: la fuente entrega todos los bytes\n");
    reset(1, 100, -1);
    memset(buf, 0, sizeof buf);
    randombytes(buf, sizeof buf);
    chk("no marca fallo de entropia", ap_kem_entropy_failed() == 0);
    chk("el bufer queda relleno", !todo_cero(buf, sizeof buf));

    printf("2. open(/dev/urandom) falla: no hay entropia en absoluto\n");
    reset(0, 0, -1);
    memset(buf, 0xFF, sizeof buf);
    randombytes(buf, sizeof buf);
    chk("marca fallo de entropia", ap_kem_entropy_failed() != 0);
    chk("el bufer queda a cero", todo_cero(buf, sizeof buf));

    printf("3. Relleno PARCIAL y luego error: el caso peligroso\n");
    reset(1, 2, -1);                        /* 2 lecturas de 4 B, luego EIO */
    memset(buf, 0xFF, sizeof buf);
    randombytes(buf, sizeof buf);
    chk("marca fallo de entropia", ap_kem_entropy_failed() != 0);
    chk("borra el bufer ENTERO, no solo la cola", todo_cero(buf, sizeof buf));

    printf("4. La fuente devuelve 0 bytes: no debe colgarse\n");
    reset(1, 0, 0);                         /* read() devuelve 0 siempre */
    memset(buf, 0xFF, sizeof buf);
    randombytes(buf, sizeof buf);           /* si cuelga, el test nunca termina */
    chk("retorna sin bucle infinito", 1);
    chk("marca fallo de entropia", ap_kem_entropy_failed() != 0);

    printf("5. El flag es sticky hasta el reset explicito\n");
    chk("sigue marcado tras la llamada", ap_kem_entropy_failed() != 0);
    reset(1, 100, -1);
    chk("el reset de prueba lo limpia", ap_kem_entropy_failed() == 0);

    printf("6. CONTRASTE: el codigo ORIGINAL ante el mismo fallo parcial\n");
    reset(1, 2, -1);
    memset(buf, 0xFF, sizeof buf);
    randombytes_original(buf, sizeof buf);
    chk("deja basura en el bufer (el defecto)", !todo_cero(buf, sizeof buf));
    chk("no senala nada al llamador (el defecto)", ap_kem_entropy_failed() == 0);

    printf("\n%s  (%d fallos)\n", fallos ? "HAY FALLOS" : "TODO CORRECTO", fallos);
    return fallos ? 1 : 0;
}
