/*
 * nonce_ctr.h -- nucleo de la construccion de nonce corregida (decision B4, opcion 3).
 *
 * QUE ES
 *   La especificacion que ya fija el articulo (cas-sc-template.tex:1470-1473):
 *     1. contador monotono de sesion, >= 64 bits
 *     2. viaja explicito en la trama, no se infiere de un campo recibido
 *     3. separacion de dominio por direccion y por epoca de clave
 *     4. ventana de repeticion (anti-replay) en el receptor
 *     5. fail-closed al agotarse, en vez de dar la vuelta
 *     6. el contador de BLOQUE (RFC 7539) se reinicia en cada mensaje
 *   Ver experiments/nonce_collision/B4_formato_nonce.md para el porque de cada punto.
 *
 * QUE NO ES
 *   No integra con GCS_KEMTLS.cpp ni con un cifrador real: ese codigo (mavlink_cipher.h,
 *   los helpers parcheados) no esta en este repositorio y no se espera que llegue (ver
 *   HANDOFF_JAVIER.md). Este modulo es el nucleo aislado --- contador, ventana de replay,
 *   ensamblado de nonce --- probado por si mismo, tal como pide 08_cierre/HANDOFF_PORTATIL.md S2.
 *   La separacion por direccion/epoca del IV de 96 bits ya esta resuelta y verificada en
 *   GCS_KEMTLS.cpp:344-345 (etiquetas HKDF "iv:tx"/"iv:rx"); aqui se modela con un prefijo de
 *   32 bits para poder ensamblar y probar el nonce completo sin repetir esa derivacion.
 */
#ifndef NONCE_CTR_H
#define NONCE_CTR_H

#include <stdint.h>
#include <stdbool.h>

typedef enum { DIR_TX = 0, DIR_RX = 1 } direction_t;

/* Contexto del emisor: un contador monotono de 64 bits por (direccion, epoca de clave). */
typedef struct {
    direction_t direction;
    uint32_t key_epoch;
    uint64_t next_counter;
    bool exhausted;         /* fail-closed: una vez agotado, no se rearma sin nueva epoca */
} sender_ctx_t;

void sender_ctx_init(sender_ctx_t *ctx, direction_t dir, uint32_t epoch);

/*
 * Entrega el siguiente contador para un mensaje nuevo. Devuelve false y no avanza el
 * estado si el contexto ya esta agotado (fail-closed): la sesion debe rechazarse y
 * renegociar epoca, no envolver el contador.
 */
bool sender_ctx_next(sender_ctx_t *ctx, uint64_t *counter_out);

/*
 * Ventana de repeticion del receptor, estilo IPsec/WireGuard (bitmap deslizante de 64
 * posiciones sobre el contador mas alto visto). Independiente por (direccion, epoca): un
 * cambio de epoca exige una ventana nueva, así que ningun contador de la epoca vieja se
 * acepta en la nueva (parte de la separacion de dominio, no solo del IV).
 */
typedef struct {
    direction_t direction;
    uint32_t key_epoch;
    uint64_t highest_seen;
    uint64_t seen_bitmap;   /* bit i => (highest_seen - i) ya se vio */
    bool initialized;
} replay_window_t;

void replay_window_init(replay_window_t *w, direction_t dir, uint32_t epoch);

/*
 * true  => contador nuevo, se acepta y se marca visto.
 * false => replay (ya visto) o demasiado viejo (fuera de la ventana de 64): se descarta.
 */
bool replay_window_check_and_update(replay_window_t *w, uint64_t counter);

/*
 * Ensambla el nonce de 12 bytes (formato ChaCha20/RFC 7539): 4 bytes de prefijo de
 * direccion/epoca (aqui, un sustituto del IV de HKDF ya verificado) + 8 bytes del
 * contador explicito, big-endian. Los 12 bytes resultantes son unicos mientras el
 * contador no se repita bajo el mismo prefijo, que es exactamente lo que garantizan
 * sender_ctx_t y replay_window_t.
 */
void assemble_nonce(uint32_t domain_prefix, uint64_t counter, uint8_t out[12]);

/*
 * Contador de bloque RFC 7539 (32 bits): se reinicia a 0 en cada mensaje nuevo y
 * avanza un bloque por cada 64 B de carga util consumidos dentro de ESE mensaje.
 * No debe confundirse con sender_ctx_t.next_counter, que es el contador por mensaje.
 */
static inline uint32_t block_counter_for_offset(uint32_t byte_offset_in_message) {
    return byte_offset_in_message / 64;
}

#endif /* NONCE_CTR_H */
