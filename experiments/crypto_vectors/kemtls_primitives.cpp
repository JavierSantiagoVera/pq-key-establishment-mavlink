// kemtls_primitives.cpp -- copia textual e inalterada (salvo quitar 'static') de
// GCS_KEMTLS.cpp:153-209. Ver kemtls_primitives.h y README.md.
#include "kemtls_primitives.h"
#include <cstring>
#include <memory>

void hmac_sha256(const uint8_t *key, size_t klen,
                  const uint8_t *msg, size_t mlen,
                  uint8_t out[32])
{
    uint8_t k0[64] = {0};
    if (klen > 64) { sha256(k0, key, klen); memset(k0+32, 0, 32); }
    else { memcpy(k0, key, klen); }

    uint8_t ipad[64], opad[64];
    for (size_t i=0;i<64;i++){ ipad[i]=k0[i]^0x36; opad[i]=k0[i]^0x5c; }

    uint8_t ihash[32];
    {   // inner = H(ipad || msg)
        uint8_t buf[64 + (mlen>0?mlen:0)];
        memcpy(buf, ipad, 64);
        if (mlen) memcpy(buf+64, msg, mlen);
        sha256(ihash, buf, 64+mlen);
    }
    {   // outer = H(opad || ihash)
        uint8_t buf[64+32];
        memcpy(buf, opad, 64);
        memcpy(buf+64, ihash, 32);
        sha256(out, buf, sizeof(buf));
    }
}

void hkdf_extract(const uint8_t salt[32], const uint8_t *ikm, size_t ikm_len,
                   uint8_t prk_out[32])
{
    hmac_sha256(salt, 32, ikm, ikm_len, prk_out);
}

void hkdf_expand_label(const uint8_t prk[32],
                        const char *label, const uint8_t *context, size_t ctx_len,
                        uint8_t *out, size_t L)
{
    if (L > 32) L = 32;

    static constexpr char prefix[] = "ardupilot-hqc-v1:";
    const size_t lp = sizeof(prefix) - 1;
    const size_t ll = strlen(label);
    const size_t info_len = lp + ll + ctx_len;

    std::unique_ptr<uint8_t[]> info(new uint8_t[info_len + 1]);
    size_t off = 0;
    memcpy(info.get()+off, prefix, lp); off += lp;
    memcpy(info.get()+off, label,  ll); off += ll;
    if (ctx_len) { memcpy(info.get()+off, context, ctx_len); off += ctx_len; }
    info.get()[off++] = 0x01;

    uint8_t T[32];
    hmac_sha256(prk, 32, info.get(), off, T);
    memcpy(out, T, L);
    memset(T, 0, sizeof(T));
}
