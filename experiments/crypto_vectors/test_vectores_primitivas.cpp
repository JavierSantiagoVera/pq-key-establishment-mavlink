// test_vectores_primitivas.cpp -- experimento #1 de 08_cierre/README.md #B-bis:
// vectores de prueba de las primitivas que usa GCS_KEMTLS.cpp, para que dejen de ser
// una caja negra. Ver README.md de esta carpeta para que se prueba contra codigo REAL
// (enlazado) y que se prueba por copia/comparacion cruzada, y por que ChaCha20 queda
// fuera (bloqueado por el fork).
//
// Compilar y correr: ver README.md de esta carpeta (dos compiladores distintos,
// gcc para sha2.c y g++ para el resto, y luego un enlazado final).
#include <cstdio>
#include <cstdint>
#include <cstring>
#include "kemtls_primitives.h"

static int g_fallos = 0;
static int g_total = 0;

static void hex_a_bytes(const char *hex, uint8_t *out, size_t n) {
    for (size_t i = 0; i < n; i++) {
        unsigned v;
        sscanf(hex + 2*i, "%2x", &v);
        out[i] = (uint8_t)v;
    }
}

static void chk_bytes(const char *nombre, const uint8_t *got, const uint8_t *want, size_t n) {
    g_total++;
    if (memcmp(got, want, n) == 0) {
        printf("[OK]   %s\n", nombre);
    } else {
        g_fallos++;
        printf("[FAIL] %s\n  got : ", nombre);
        for (size_t i=0;i<n;i++) printf("%02x", got[i]);
        printf("\n  want: ");
        for (size_t i=0;i<n;i++) printf("%02x", want[i]);
        printf("\n");
    }
}

// ---------------------------------------------------------------------------
// 1. SHA-256 -- FIPS 180-2, vectores oficiales (codigo REAL: sha2.c sin modificar)
// ---------------------------------------------------------------------------
static void test_sha256(void)
{
    uint8_t out[32], want[32];

    sha256(out, (const uint8_t*)"", 0);
    hex_a_bytes("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", want, 32);
    chk_bytes("SHA-256(\"\") [FIPS 180-2]", out, want, 32);

    sha256(out, (const uint8_t*)"abc", 3);
    hex_a_bytes("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", want, 32);
    chk_bytes("SHA-256(\"abc\") [FIPS 180-2]", out, want, 32);

    const char *msg448 = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
    sha256(out, (const uint8_t*)msg448, strlen(msg448));
    hex_a_bytes("248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1", want, 32);
    chk_bytes("SHA-256(msg de 448 bits) [FIPS 180-2]", out, want, 32);
}

// ---------------------------------------------------------------------------
// 2. HMAC-SHA256 -- RFC 4231 #4.2 y #4.3 (copia textual de GCS_KEMTLS.cpp:153-177,
//    llamando al sha256 real de arriba)
// ---------------------------------------------------------------------------
static void test_hmac_sha256(void)
{
    uint8_t out[32], want[32];

    uint8_t key1[20]; memset(key1, 0x0b, 20);
    const char *data1 = "Hi There";
    hmac_sha256(key1, 20, (const uint8_t*)data1, strlen(data1), out);
    hex_a_bytes("b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7", want, 32);
    chk_bytes("HMAC-SHA256 RFC4231 TC1 (\"Hi There\")", out, want, 32);

    const char *key2 = "Jefe";
    const char *data2 = "what do ya want for nothing?";
    hmac_sha256((const uint8_t*)key2, strlen(key2), (const uint8_t*)data2, strlen(data2), out);
    hex_a_bytes("5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843", want, 32);
    chk_bytes("HMAC-SHA256 RFC4231 TC2 (\"Jefe\")", out, want, 32);
}

// ---------------------------------------------------------------------------
// 3. HKDF-Extract -- RFC 5869 #A.3 (caso 3: "sin salt"), con SHA-256 (copia textual
//    de GCS_KEMTLS.cpp:180-184). Este hkdf_extract() del proyecto solo acepta salt de
//    32 B (klen=32 esta fijo en la llamada a hmac_sha256 dentro de la funcion) -- por
//    diseno, porque en el protocolo el salt siempre sale de un sha256 anterior. Los
//    casos A.1/A.2 de la RFC usan salt de 13 B y 80 B y NO aplican a esta firma; el
//    caso A.3 es el unico de los tres que usa salt de exactamente 32 B (la RFC lo
//    rellena con HashLen=32 ceros cuando no se da salt), asi que es el que corresponde.
//    Solo se compara el PRK: el Expand del proyecto no es el generico de la RFC (ver #4).
// ---------------------------------------------------------------------------
static void test_hkdf_extract(void)
{
    uint8_t ikm[22]; memset(ikm, 0x0b, 22);
    uint8_t salt[32]; memset(salt, 0x00, 32);   // RFC5869 A.3: sin salt -> 32 ceros

    uint8_t prk[32], want[32];
    hkdf_extract(salt, ikm, 22, prk);
    hex_a_bytes("19ef24a32c717b167f33a91d6f648bdf96596776afdb6377ac434c1c293ccb04", want, 32);
    chk_bytes("HKDF-Extract RFC5869 A.3 (PRK, sin salt)", prk, want, 32);
}

// ---------------------------------------------------------------------------
// 4. hkdf_expand_label -- construccion propia del proyecto (prefijo de dominio +
//    etiqueta + contexto, una sola ronda). NO hay vector oficial: RFC 5869 no define
//    esta variante. Se prueba por COMPARACION CRUZADA contra una segunda
//    implementacion independiente en Python (referencia_hkdf_expand_label.py, stdlib
//    hmac/hashlib), reproducible con ese script. Esto detecta un bug en la copia de
//    aqui, o en el original de GCS_KEMTLS.cpp si algun dia diverge -- no "certifica"
//    la construccion en si, que es criterio de diseno, no de correccion aritmetica.
// ---------------------------------------------------------------------------
static void test_hkdf_expand_label_cruzado(void)
{
    uint8_t prk[32];
    for (int i = 0; i < 32; i++) prk[i] = (uint8_t)i;

    const char *label = "test-label";
    uint8_t context[4] = {0x01, 0x02, 0x03, 0x04};

    uint8_t out[32], want[32];
    hkdf_expand_label(prk, label, context, 4, out, 32);
    hex_a_bytes("b7b1662969a538e2495fb95a3aff9ba69e6595c561ee3ee4bd37871c7ebb4916", want, 32);
    chk_bytes("hkdf_expand_label vs referencia Python independiente", out, want, 32);
}

int main(void)
{
    printf("== vectores de prueba de las primitivas de GCS_KEMTLS.cpp ==\n");
    printf("(ChaCha20 RFC 8439 queda fuera: mavlink_cipher.h no esta en el repo -- ver README.md)\n\n");

    test_sha256();
    test_hmac_sha256();
    test_hkdf_extract();
    test_hkdf_expand_label_cruzado();

    printf("\n%d/%d OK\n", g_total - g_fallos, g_total);
    return g_fallos == 0 ? 0 : 1;
}
