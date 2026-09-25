// chacha20.c -- ver chacha20.h. Algoritmo tal como lo especifica RFC 8439 #2.3-#2.4.
#include "chacha20.h"
#include <string.h>

static uint32_t rotl32(uint32_t x, int n) {
    return (x << n) | (x >> (32 - n));
}

static void quarter_round(uint32_t *s, int a, int b, int c, int d) {
    s[a] += s[b]; s[d] ^= s[a]; s[d] = rotl32(s[d], 16);
    s[c] += s[d]; s[b] ^= s[c]; s[b] = rotl32(s[b], 12);
    s[a] += s[b]; s[d] ^= s[a]; s[d] = rotl32(s[d], 8);
    s[c] += s[d]; s[b] ^= s[c]; s[b] = rotl32(s[b], 7);
}

static uint32_t load_le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void store_le32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v);
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

void chacha20_block(const uint8_t key[32], const uint8_t nonce[12], uint32_t counter,
                     uint8_t out[64])
{
    uint32_t state[16];
    state[0] = 0x61707865u; state[1] = 0x3320646eu;
    state[2] = 0x79622d32u; state[3] = 0x6b206574u;
    for (int i = 0; i < 8; i++) {
        state[4 + i] = load_le32(key + 4 * i);
    }
    state[12] = counter;
    for (int i = 0; i < 3; i++) {
        state[13 + i] = load_le32(nonce + 4 * i);
    }

    uint32_t working[16];
    memcpy(working, state, sizeof(state));

    for (int round = 0; round < 10; round++) {
        quarter_round(working, 0, 4, 8, 12);
        quarter_round(working, 1, 5, 9, 13);
        quarter_round(working, 2, 6, 10, 14);
        quarter_round(working, 3, 7, 11, 15);
        quarter_round(working, 0, 5, 10, 15);
        quarter_round(working, 1, 6, 11, 12);
        quarter_round(working, 2, 7, 8, 13);
        quarter_round(working, 3, 4, 9, 14);
    }

    for (int i = 0; i < 16; i++) {
        store_le32(out + 4 * i, working[i] + state[i]);
    }
}

void chacha20_xor(const uint8_t key[32], const uint8_t nonce[12], uint32_t counter,
                   const uint8_t *in, uint8_t *out, size_t len)
{
    uint8_t block[64];
    size_t off = 0;
    while (off < len) {
        chacha20_block(key, nonce, counter, block);
        size_t chunk = (len - off < 64) ? (len - off) : 64;
        for (size_t i = 0; i < chunk; i++) {
            out[off + i] = in[off + i] ^ block[i];
        }
        off += chunk;
        counter++;
    }
}
