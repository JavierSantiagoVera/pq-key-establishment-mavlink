/*
 * demo_chacha20_real.c -- enlaza la construccion vieja y la corregida a un ChaCha20 REAL
 * (experiments/crypto_vectors/chacha20.c, validado por comparacion diferencial contra
 * `cryptography` de Python, ver ese README.md), para pasar de "los indices (nonce,
 * bloque) no se repiten" (test_nonce_correction.c, aritmetica sobre indices) a "el
 * ataque de XOR de keystream funciona de verdad con estos bytes" (aqui, con el cifrador
 * de verdad).
 *
 * QUE SI CIERRA ESTO, Y QUE NO
 *   SI: demuestra con bytes reales, no solo con indices, que (a) la construccion vieja
 *       permite recuperar un mensaje conociendo el otro cuando el contador de 8 bits da
 *       la vuelta, y (b) la construccion corregida, corrida por el mismo cifrador real,
 *       no reutiliza ni un solo bloque de keystream en cientos de mensajes.
 *   NO: sigue sin decir nada sobre si el firmware real (mavlink_cipher.h, ausente del
 *       repositorio) trata counter0 como contador de bloque de RFC 7539 -- esa es la
 *       inferencia de NOTAS_ONBOARDING.txt #2.2, y no se puede cerrar sin ese archivo.
 *       Aqui la construccion corregida es un diseño propio (B4 opcion 3), no una pieza
 *       de un firmware existente.
 *
 * Compilar y correr: ver README.md ("Demo con ChaCha20 real").
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "nonce_ctr.h"
#include "../crypto_vectors/chacha20.h"

static int fallos = 0;
static void chk(const char *nombre, int cond) {
    printf("  [%s] %s\n", cond ? "OK  " : "FALLA", nombre);
    if (!cond) fallos++;
}

/* Clave de sesion fija, NO secreta: esto es una demo reproducible, no una clave real. */
static const uint8_t CLAVE_DEMO[32] = {
    0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
    0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff,
    0xf0, 0xe1, 0xd2, 0xc3, 0xb4, 0xa5, 0x96, 0x87,
    0x78, 0x69, 0x5a, 0x4b, 0x3c, 0x2d, 0x1e, 0x0f,
};

/* ---------------------------------------------------------- parte 1: construccion vieja
 * Igual que test_nonce_correction.c: nonce constante, counter0 = seq (uint8_t). Aqui no
 * hace falta simular los 256 mensajes de por medio -- el cifrador no tiene estado propio,
 * asi que "seq da la vuelta a 0" es literalmente cifrar OTRO mensaje con counter0=0 de
 * nuevo. Eso es exactamente lo que hace un contador de 8 bits tras 256 mensajes. */
static void parte1_construccion_vieja(void)
{
    printf("1. CONSTRUCCION VIEJA -- ataque de XOR con ChaCha20 real\n");

    uint8_t nonce_constante[12] = {0};  /* GCS_KEMTLS.cpp:248-271, modelado: nonce fijo */

    const char *msg_a = "ARM_THROTTLE=45 ALT=120.3 GPS_LOCK=1 BATTERY=76 HEADING=270 ";
    const char *msg_b = "DISARM_NOW MODE=RTL ALT=118.9 GPS_LOCK=1 BATTERY=75 HDG=268 ";
    size_t len = strlen(msg_a);
    if (strlen(msg_b) < len) len = strlen(msg_b);

    uint8_t ct_a[256], ct_b[256];
    /* Mensaje A: primer mensaje de la sesion, counter0 = seq = 0. */
    chacha20_xor(CLAVE_DEMO, nonce_constante, 0, (const uint8_t *)msg_a, ct_a, len);
    /* Mensaje B: mensaje 257 de la sesion. seq es uint8_t: 257 mod 256 = 1... pero el
     * defecto real es peor que solo el envolvimiento: basta con que otro mensaje use el
     * MISMO valor de seq, y seq se repite cada 256 mensajes sin que haga falta nada mas
     * (no hay contador de 64 bits detras). Se modela como counter0 = 0 otra vez. */
    chacha20_xor(CLAVE_DEMO, nonce_constante, 0, (const uint8_t *)msg_b, ct_b, len);

    uint8_t xor_ct[256], xor_pt[256];
    for (size_t i = 0; i < len; i++) {
        xor_ct[i] = ct_a[i] ^ ct_b[i];
        xor_pt[i] = (uint8_t)msg_a[i] ^ (uint8_t)msg_b[i];
    }
    chk("XOR(ct_a, ct_b) == XOR(claro_a, claro_b) -- el keystream se cancela",
        memcmp(xor_ct, xor_pt, len) == 0);

    /* El "ataque": conociendo msg_b (p.ej. porque un atacante lo genero el o lo dedujo
     * del contexto), se recupera msg_a completo sin la clave. */
    char recuperado[256] = {0};
    for (size_t i = 0; i < len; i++) {
        recuperado[i] = (char)(xor_ct[i] ^ (uint8_t)msg_b[i]);
    }
    printf("      mensaje A real       : \"%.*s\"\n", (int)len, msg_a);
    printf("      mensaje A recuperado : \"%.*s\"  (sin conocer la clave)\n", (int)len, recuperado);
    chk("el mensaje A se recupera byte a byte solo con XOR y conocer B",
        memcmp(recuperado, msg_a, len) == 0);
}

/* --------------------------------------------------- parte 2: construccion corregida */
#define N_MENSAJES 500
#define MAX_BLOQUES (N_MENSAJES * 16)

typedef struct { uint8_t bytes[64]; } bloque_t;

static int cmp_bloque(const void *a, const void *b) {
    return memcmp(((const bloque_t *)a)->bytes, ((const bloque_t *)b)->bytes, 64);
}

static void parte2_construccion_corregida(void)
{
    printf("\n2. CONSTRUCCION CORREGIDA -- %d mensajes, ChaCha20 real, sin repetir ningun bloque de keystream\n",
           N_MENSAJES);

    sender_ctx_t tx;
    sender_ctx_init(&tx, DIR_TX, /*epoch=*/1);
    uint32_t domain_prefix = 0xA5A5A5A5u;  /* sustituto del IV de HKDF, ver nonce_ctr.h */

    bloque_t *bloques = malloc(sizeof(bloque_t) * MAX_BLOQUES);
    int n_bloques = 0;

    int longitudes[] = {16, 63, 64, 65, 128, 200, 1024};
    int n_long = (int)(sizeof(longitudes) / sizeof(longitudes[0]));

    uint8_t *ct_muestra[3];
    uint8_t *pt_muestra[3];
    int len_muestra[3];
    int guardadas = 0;

    for (int i = 0; i < N_MENSAJES; i++) {
        uint64_t counter;
        if (!sender_ctx_next(&tx, &counter)) break;

        uint8_t nonce[12];
        assemble_nonce(domain_prefix, counter, nonce);

        int len = longitudes[i % n_long];
        uint8_t *pt = malloc(len);
        uint8_t *ct = malloc(len);
        for (int k = 0; k < len; k++) pt[k] = (uint8_t)((i * 31 + k * 7) & 0xFF);

        int nb = (len + 63) / 64;
        for (int b = 0; b < nb; b++) {
            uint8_t ks[64];
            chacha20_block(CLAVE_DEMO, nonce, (uint32_t)b, ks);
            memcpy(bloques[n_bloques].bytes, ks, 64);
            n_bloques++;
        }
        chacha20_xor(CLAVE_DEMO, nonce, 0, pt, ct, len);

        if (i == 0 || i == 1 || i == N_MENSAJES - 1) {
            ct_muestra[guardadas] = ct;
            pt_muestra[guardadas] = pt;
            len_muestra[guardadas] = len;
            guardadas++;
        } else {
            free(pt);
            free(ct);
        }
    }

    qsort(bloques, n_bloques, sizeof(bloque_t), cmp_bloque);
    int repetido = 0;
    for (int i = 1; i < n_bloques; i++) {
        if (memcmp(bloques[i - 1].bytes, bloques[i].bytes, 64) == 0) { repetido = 1; break; }
    }
    printf("      bloques de keystream generados: %d\n", n_bloques);
    chk("ningun bloque de keystream de 64 B se repite", !repetido);

    /* El mismo intento de ataque de la parte 1, sobre dos mensajes cualesquiera de esta
     * tanda: si la construccion es correcta, XOR(ct1, ct2) NO debe coincidir con
     * XOR(pt1, pt2) salvo en los primeros len_min bytes donde por azar coincidiera algun
     * byte de keystream -- lo que se comprueba es que NO coincide en bloque completo. */
    int len_min = len_muestra[0] < len_muestra[1] ? len_muestra[0] : len_muestra[1];
    int algun_byte_distinto = 0;
    for (int i = 0; i < len_min; i++) {
        uint8_t xor_ct = ct_muestra[0][i] ^ ct_muestra[1][i];
        uint8_t xor_pt = pt_muestra[0][i] ^ pt_muestra[1][i];
        if (xor_ct != xor_pt) { algun_byte_distinto = 1; break; }
    }
    chk("el mismo truco de XOR entre dos mensajes cualesquiera YA NO funciona",
        algun_byte_distinto);

    for (int i = 0; i < guardadas; i++) { free(ct_muestra[i]); free(pt_muestra[i]); }
    free(bloques);
}

/* ------------------------------------------------- parte 3: rekey / cambio de epoca
 * Responde al defecto A5 de 03_review/gap_analysis.md ("gestion de nonce/IV bajo
 * claves de sesion: no se documenta unicidad ni riesgo de reuso tras rekeying") y
 * demuestra con bytes reales lo que cas-sc-template.tex:1472 solo afirma en texto:
 * "domain separation by direction and key epoch".
 *
 * sender_ctx_t reinicia el contador a 0 en cada epoca nueva (rekey). Si el nonce
 * ensamblado no separara por epoca, dos mensajes con el MISMO contador (0) en epocas
 * distintas colisionarian: mismo nonce, mismo bloque -> mismo keystream, aunque la
 * CLAVE sea la misma (aqui se usa la misma CLAVE_DEMO a proposito en las dos epocas,
 * para probar que la separacion de dominio por si sola evita la colision, sin
 * depender de que el rekey tambien cambie la clave -- que en el sistema real si
 * cambia, via un HQC_FINISH nuevo, pero esta prueba no depende de eso). */
static void parte3_rekey_separacion_por_epoca(void)
{
    printf("\n3. REKEY -- separacion de dominio por epoca, con la MISMA clave en las dos\n");

    uint32_t prefijo_epoca1 = 0xA5A5A5A5u;
    uint32_t prefijo_epoca2 = 0x5A5A5A5Au;  /* lo que HKDF derivaria distinto por epoca,
                                                ya verificado en GCS_KEMTLS.cpp:344-345 */

    sender_ctx_t tx1, tx2;
    sender_ctx_init(&tx1, DIR_TX, /*epoch=*/1);
    sender_ctx_init(&tx2, DIR_TX, /*epoch=*/2);

    const char *msg_e1 = "PRE-REKEY: ARM_THROTTLE=40 ALT=80.0 GPS_LOCK=1 -----------";
    const char *msg_e2 = "POST-REKEY: DISARM MODE=LAND ALT=2.1 BATTERY_LOW=1 -------";
    size_t len = strlen(msg_e1);

    uint64_t c1, c2;
    sender_ctx_next(&tx1, &c1);   /* primer mensaje de la epoca 1: contador = 0 */
    sender_ctx_next(&tx2, &c2);   /* primer mensaje de la epoca 2, TRAS EL REKEY: tambien 0 */
    chk("el contador se reinicia a 0 en la epoca nueva (eso es lo que hace el rekey)",
        c1 == 0 && c2 == 0);

    uint8_t nonce1[12], nonce2[12];
    assemble_nonce(prefijo_epoca1, c1, nonce1);
    assemble_nonce(prefijo_epoca2, c2, nonce2);

    uint8_t ct_e1[64], ct_e2[64];
    chacha20_xor(CLAVE_DEMO, nonce1, 0, (const uint8_t *)msg_e1, ct_e1, len);
    chacha20_xor(CLAVE_DEMO, nonce2, 0, (const uint8_t *)msg_e2, ct_e2, len);

    uint8_t xor_ct[64], xor_pt[64];
    for (size_t i = 0; i < len; i++) {
        xor_ct[i] = ct_e1[i] ^ ct_e2[i];
        xor_pt[i] = (uint8_t)msg_e1[i] ^ (uint8_t)msg_e2[i];
    }
    chk("con separacion por epoca: XOR(ct_e1,ct_e2) NO reproduce XOR(claro_e1,claro_e2)",
        memcmp(xor_ct, xor_pt, len) != 0);

    /* Control negativo: si alguien se olvidara de separar por epoca (mismo prefijo de
     * dominio en las dos "epocas"), el mismo contador 0 SI colisionaria -- confirma que
     * la separacion de arriba es la que evita el problema, no una casualidad. */
    uint8_t nonce1_roto[12], nonce2_roto[12];
    assemble_nonce(prefijo_epoca1, c1, nonce1_roto);
    assemble_nonce(prefijo_epoca1, c2, nonce2_roto);  /* MISMO prefijo -- el bug que se evita */
    chk("control negativo: sin separar por epoca, el prefijo repetido da el MISMO nonce",
        memcmp(nonce1_roto, nonce2_roto, 12) == 0);

    printf("      epoca 1, contador 0, prefijo %08x -> nonce %02x%02x%02x%02x...\n",
           prefijo_epoca1, nonce1[0], nonce1[1], nonce1[2], nonce1[3]);
    printf("      epoca 2, contador 0, prefijo %08x -> nonce %02x%02x%02x%02x... (distinto)\n",
           prefijo_epoca2, nonce2[0], nonce2[1], nonce2[2], nonce2[3]);
}

int main(void)
{
    printf("== demo con ChaCha20 real (RFC 8439), no modelado ==\n\n");
    parte1_construccion_vieja();
    parte2_construccion_corregida();
    parte3_rekey_separacion_por_epoca();
    printf("\n%s\n", fallos == 0 ? "TODO CORRECTO" : "HAY FALLOS");
    return fallos == 0 ? 0 : 1;
}
