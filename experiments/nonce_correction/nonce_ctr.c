/*
 * nonce_ctr.c -- implementacion. Ver nonce_ctr.h para el contrato y la trazabilidad.
 */
#include "nonce_ctr.h"
#include <limits.h>

void sender_ctx_init(sender_ctx_t *ctx, direction_t dir, uint32_t epoch) {
    ctx->direction = dir;
    ctx->key_epoch = epoch;
    ctx->next_counter = 0;
    ctx->exhausted = false;
}

bool sender_ctx_next(sender_ctx_t *ctx, uint64_t *counter_out) {
    if (ctx->exhausted) {
        return false;                  /* fail-closed: no hay vuelta atras sin rekey */
    }
    *counter_out = ctx->next_counter;
    if (ctx->next_counter == UINT64_MAX) {
        /* Se entrega el ultimo valor valido y se cierra el contexto: la SIGUIENTE
         * llamada falla en vez de dar la vuelta a 0, que es exactamente el defecto
         * original con seq de 8 bits, solo que a una escala irrelevante en la practica. */
        ctx->exhausted = true;
    } else {
        ctx->next_counter++;
    }
    return true;
}

void replay_window_init(replay_window_t *w, direction_t dir, uint32_t epoch) {
    w->direction = dir;
    w->key_epoch = epoch;
    w->highest_seen = 0;
    w->seen_bitmap = 0;
    w->initialized = false;
}

bool replay_window_check_and_update(replay_window_t *w, uint64_t counter) {
    if (!w->initialized) {
        w->initialized = true;
        w->highest_seen = counter;
        w->seen_bitmap = 1ULL;         /* bit 0 == highest_seen, ya visto */
        return true;
    }

    if (counter > w->highest_seen) {
        uint64_t shift = counter - w->highest_seen;
        w->seen_bitmap = (shift >= 64) ? 0ULL : (w->seen_bitmap << shift);
        w->seen_bitmap |= 1ULL;
        w->highest_seen = counter;
        return true;
    }

    uint64_t diff = w->highest_seen - counter;
    if (diff >= 64) {
        return false;                  /* demasiado viejo: fuera de la ventana */
    }
    uint64_t bit = 1ULL << diff;
    if (w->seen_bitmap & bit) {
        return false;                  /* replay: ese contador ya se proceso */
    }
    w->seen_bitmap |= bit;
    return true;                       /* reordenado pero dentro de ventana: se acepta */
}

void assemble_nonce(uint32_t domain_prefix, uint64_t counter, uint8_t out[12]) {
    out[0] = (uint8_t)(domain_prefix >> 24);
    out[1] = (uint8_t)(domain_prefix >> 16);
    out[2] = (uint8_t)(domain_prefix >> 8);
    out[3] = (uint8_t)(domain_prefix);
    for (int i = 0; i < 8; i++) {
        out[4 + i] = (uint8_t)(counter >> (56 - 8 * i));
    }
}
