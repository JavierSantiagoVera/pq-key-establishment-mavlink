#include "ap_kem.h"
#include "randombytes_status.h"

/*
 * PARCHEADO (hallazgo A8): toda operacion que consuma aleatoriedad comprueba
 * primero si la fuente de entropia fallo en este arranque. Si fallo, la operacion
 * devuelve false y la maquina de estados de la sesion transita a FAIL, en vez de
 * seguir adelante con material de clave no justificable.
 */

extern "C" bool ap_kem_keypair(uint8_t *pk, uint8_t *sk) {
    if (ap_kem_entropy_failed()) { return false; }
    if (PQCLEAN_HQC128_CLEAN_crypto_kem_keypair(pk, sk) != 0) { return false; }
    return !ap_kem_entropy_failed();   /* pudo fallar DURANTE la generacion */
}

extern "C" bool ap_kem_enc(uint8_t *ct, uint8_t *ss, const uint8_t *pk) {
    if (ap_kem_entropy_failed()) { return false; }
    if (PQCLEAN_HQC128_CLEAN_crypto_kem_enc(ct, ss, pk) != 0) { return false; }
    return !ap_kem_entropy_failed();
}

extern "C" bool ap_kem_dec(uint8_t *ss, const uint8_t *ct, const uint8_t *sk) {
    /* La decapsulacion no consume entropia nueva, pero si la clave se genero con
     * entropia fallida el resultado no es confiable. */
    if (ap_kem_entropy_failed()) { return false; }
    return PQCLEAN_HQC128_CLEAN_crypto_kem_dec(ss, ct, sk) == 0;
}
