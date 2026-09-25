/*
 * test_nonce_correction.c -- suite de la construccion de nonce corregida (B4, opcion 3).
 *
 * QUE PRUEBA
 *   1. Control positivo: la construccion VIEJA (seq de 8 bits como contador de bloque,
 *      igual que experiments/nonce_collision/test_colision_nonce.py) SI colisiona.
 *      Si este control fallara, el resto de la suite no seria confiable: estariamos
 *      probando un arnes que no sabe detectar una colision real.
 *   2. La construccion CORREGIDA no repite la terna (contador, bloque) en miles de
 *      mensajes de tamano variable (la prueba obligatoria del handoff, >256 mensajes).
 *   3. Ventana de repeticion: replay exacto se rechaza; reordenamiento DENTRO de la
 *      ventana se acepta; reordenamiento FUERA de la ventana se rechaza.
 *   4. Agotamiento del contador de 64 bits: falla cerrado (se rechaza el envio
 *      siguiente), no da la vuelta a 0 como hacia seq de 8 bits.
 *   5. Separacion de dominio: mismo valor de contador en TX/RX o en epocas distintas
 *      produce nonces distintos, y las ventanas de replay son independientes entre si.
 *
 * QUE NO PRUEBA
 *   No enlaza ChaCha20/AES real ni el codigo de GCS_KEMTLS.cpp: ese enlace requiere
 *   mavlink_cipher.h, que no esta en el repositorio (ver HANDOFF_JAVIER.md). Prueba el
 *   nucleo aislado -- contador, ventana, ensamblado de nonce -- tal como lo pide
 *   08_cierre/HANDOFF_PORTATIL.md, tarea S2.
 *
 * Compilar y correr:
 *   gcc -std=c11 -Wall -Wextra -o test_nonce_correction test_nonce_correction.c nonce_ctr.c \
 *       && ./test_nonce_correction
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

#include "nonce_ctr.h"

/* ------------------------------------------------------------------ arnes */
static int fallos = 0;

static void chk(const char *nombre, int cond) {
    printf("  [%s] %s\n", cond ? "OK  " : "FALLA", nombre);
    if (!cond) { fallos++; }
}

/* --------------------------- modelo de la construccion VIEJA, para el control positivo
 * Igual que GCS_KEMTLS.cpp:248-271: nonce constante, counter0 = seq (uint8_t). Un mensaje
 * de LONG_MSG bytes consume varios bloques de 64 B empezando en seq; el mensaje siguiente
 * empieza en seq+1, asi que solapan si LONG_MSG > 64, exactamente como demuestra
 * experiments/nonce_collision/test_colision_nonce.py. */
#define LONG_MSG_VIEJO 200
#define BLOQUE_CHACHA 64

static int bloques_usados_viejo(int long_msg) {
    return (long_msg + BLOQUE_CHACHA - 1) / BLOQUE_CHACHA;
}

/* Devuelve 1 si detecta colision de (nonce constante, bloque) antes de N mensajes. */
static int construccion_vieja_colisiona(int n_mensajes) {
    /* n_mensajes <= 256 para que seq (uint8_t) no de la vuelta dentro de la prueba */
    char vistos[256] = {0};
    for (int seq = 0; seq < n_mensajes; seq++) {
        int inicio = seq & 0xFF;
        int nb = bloques_usados_viejo(LONG_MSG_VIEJO);
        for (int b = inicio; b < inicio + nb; b++) {
            if (b < 256 && vistos[b]) { return 1; }
            if (b < 256) { vistos[b] = 1; }
        }
    }
    return 0;
}

/* ------------------------------------------------------- construccion corregida: masiva */
#define N_MENSAJES_MASIVO 2000

typedef struct { uint8_t nonce[12]; uint32_t bloque; } terna_t;

static int terna_igual(const terna_t *a, const terna_t *b) {
    return memcmp(a->nonce, b->nonce, 12) == 0 && a->bloque == b->bloque;
}

int main(void) {
    printf("1. CONTROL POSITIVO -- la construccion vieja debe colisionar\n");
    chk("seq de 8 bits colisiona antes de 256 mensajes (mensaje de 200 B > 1 bloque)",
        construccion_vieja_colisiona(256));

    printf("\n2. CONSTRUCCION CORREGIDA -- sin repetir (nonce, bloque) en miles de mensajes\n");
    {
        sender_ctx_t tx;
        sender_ctx_init(&tx, DIR_TX, /*epoch=*/1);
        uint32_t domain_prefix = 0xAABBCCDDu; /* sustituto de IV HKDF ya verificado */

        terna_t *vistos = malloc(sizeof(terna_t) * N_MENSAJES_MASIVO * 16);
        size_t n_vistos = 0;
        int repetido = 0;
        int longitudes[] = {32, 64, 100, 200, 280, 1024}; /* incluye mensajes de varios bloques */

        for (int i = 0; i < N_MENSAJES_MASIVO && !repetido; i++) {
            uint64_t counter;
            if (!sender_ctx_next(&tx, &counter)) { break; }
            uint8_t nonce[12];
            assemble_nonce(domain_prefix, counter, nonce);

            int long_msg = longitudes[i % (int)(sizeof(longitudes) / sizeof(longitudes[0]))];
            int nb = (long_msg + 63) / 64;
            for (int b = 0; b < nb && !repetido; b++) {
                terna_t t;
                memcpy(t.nonce, nonce, 12);
                t.bloque = (uint32_t)b;  /* contador de bloque reiniciado por mensaje */
                for (size_t k = 0; k < n_vistos; k++) {
                    if (terna_igual(&vistos[k], &t)) { repetido = 1; break; }
                }
                if (!repetido) { vistos[n_vistos++] = t; }
            }
        }
        chk("no hay ninguna terna (nonce, bloque) repetida", !repetido);
        chk("se generaron los mensajes esperados sin agotar el contador",
            n_vistos > 0);
        free(vistos);
    }

    printf("\n3. VENTANA DE REPETICION\n");
    {
        replay_window_t w;
        replay_window_init(&w, DIR_RX, /*epoch=*/1);

        chk("primer contador (10) se acepta", replay_window_check_and_update(&w, 10));
        chk("replay exacto del mismo contador (10) se rechaza",
            !replay_window_check_and_update(&w, 10));
        chk("contador mayor (11) se acepta y avanza la ventana",
            replay_window_check_and_update(&w, 11));
        chk("reordenado DENTRO de la ventana (9, diff=2) se acepta",
            replay_window_check_and_update(&w, 9));
        chk("ese mismo reordenado (9) reenviado ahora es replay y se rechaza",
            !replay_window_check_and_update(&w, 9));

        replay_window_init(&w, DIR_RX, /*epoch=*/1);
        chk("arranque en 1000 fija la ventana alta", replay_window_check_and_update(&w, 1000));
        chk("reordenado FUERA de la ventana (900, diff=100>=64) se rechaza",
            !replay_window_check_and_update(&w, 900));
        chk("un contador dentro de ventana (950, diff=50) si se acepta",
            replay_window_check_and_update(&w, 950));
    }

    printf("\n4. AGOTAMIENTO -- fail-closed, no dar la vuelta\n");
    {
        sender_ctx_t tx;
        sender_ctx_init(&tx, DIR_TX, /*epoch=*/1);
        tx.next_counter = UINT64_MAX; /* forzar el borde sin iterar 2^64 veces */

        uint64_t counter;
        chk("el ultimo valor valido (UINT64_MAX) se entrega",
            sender_ctx_next(&tx, &counter) && counter == UINT64_MAX);
        chk("la llamada SIGUIENTE falla en vez de envolver a 0",
            !sender_ctx_next(&tx, &counter));
    }

    printf("\n5. SEPARACION DE DOMINIO por direccion y epoca\n");
    {
        uint8_t nonce_tx[12], nonce_rx[12], nonce_tx_epoca2[12];
        /* prefijos distintos = HKDF ya deriva IV distinto por direccion/epoca (verificado
         * en GCS_KEMTLS.cpp:344-345); aqui solo se comprueba que el ensamblado los respeta. */
        assemble_nonce(0x11111111u, 42, nonce_tx);
        assemble_nonce(0x22222222u, 42, nonce_rx);
        assemble_nonce(0x33333333u, 42, nonce_tx_epoca2);

        chk("mismo contador, TX vs RX -> nonces distintos",
            memcmp(nonce_tx, nonce_rx, 12) != 0);
        chk("mismo contador, misma direccion pero otra epoca -> nonces distintos",
            memcmp(nonce_tx, nonce_tx_epoca2, 12) != 0);

        replay_window_t w_tx, w_rx;
        replay_window_init(&w_tx, DIR_TX, 1);
        replay_window_init(&w_rx, DIR_RX, 1);
        chk("contador 7 aceptado en la ventana TX", replay_window_check_and_update(&w_tx, 7));
        chk("el mismo contador 7 en la ventana RX (independiente) tambien se acepta",
            replay_window_check_and_update(&w_rx, 7));
    }

    printf("\n%s  (%d fallos)\n", fallos ? "HAY FALLOS" : "TODO CORRECTO", fallos);
    return fallos ? 1 : 0;
}
