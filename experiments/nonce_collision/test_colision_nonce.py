# -*- coding: utf-8 -*-
r"""
Demuestra el reuso de keystream del plano de datos, y que la correccion lo elimina.

QUE ES ESTO Y QUE NO ES
  Es un modelo EXACTO de la derivacion de nonce y contador tal como esta en
  libraries/GCS_MAVLink/GCS_KEMTLS.cpp:248-286. No ejecuta ChaCha20 ni AES: no hace falta.
  El reuso de keystream se decide enteramente por si dos mensajes comparten la terna
  (clave, nonce, indice de bloque), y eso es aritmetica sobre la derivacion.

  No sustituye a un test que enlace el codigo real --- ese hay que escribirlo tambien --- pero
  se ejecuta hoy, sin hardware y sin toolchain, y basta para que un revisor vea el defecto.

LO QUE SI ESTA VERIFICADO EN EL CODIGO
  GCS_KEMTLS.cpp:248   extern "C" bool mavlink_get_crypt_config(..., uint8_t seq, ...)
  GCS_KEMTLS.cpp:269   memcpy(nonce_out, iv, 12);        // IV de sesion, constante
  GCS_KEMTLS.cpp:270   *counter0 = (uint32_t)seq;        // ChaCha20: contador de BLOQUES
  GCS_KEMTLS.cpp:280   nonce_out[12] = (seq >> 24)&0xFF; // AES-CTR: siempre 0
  GCS_KEMTLS.cpp:284   *counter0 = 0;
  GCS.h:291            uint8_t aead_alg = 1;             // 1 = ChaCha20  <- POR DEFECTO
  GCS_KEMTLS.cpp:344-345  hkdf_expand_label(prk, "iv:tx"/"iv:rx", ...)  <- direcciones BIEN separadas
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BLOQUE_CHACHA = 64      # bytes por bloque de ChaCha20
BLOQUE_AES = 16         # bytes por bloque de AES-CTR


def bloques_usados(long_msg, tam_bloque):
    return (long_msg + tam_bloque - 1) // tam_bloque


# =========================================================================================
def chacha_actual(seq, long_msg):
    """Modelo de GCS_KEMTLS.cpp:265-271. Devuelve los indices de bloque que consume."""
    inicio = seq & 0xFF                       # seq es uint8_t
    return set(range(inicio, inicio + bloques_usados(long_msg, BLOQUE_CHACHA)))


def aesctr_actual(seq, long_msg):
    """Modelo de GCS_KEMTLS.cpp:274-286. El nonce lleva seq; el contador arranca en 0."""
    nonce = (0, 0, 0, seq & 0xFF)             # los tres desplazamientos dan 0 sobre uint8_t
    return {(nonce, b) for b in range(bloques_usados(long_msg, BLOQUE_AES))}


def propuesto(contador64, long_msg, tam_bloque):
    """Correccion: contador monotono de 64 bits en el nonce, bloque reiniciado por mensaje."""
    return {(contador64, b) for b in range(bloques_usados(long_msg, tam_bloque))}


# =========================================================================================
def informe(nombre, generador, n_mensajes, long_msg, etiqueta_unidad):
    vistos = {}
    primera_colision = None
    solapes = 0
    for i in range(n_mensajes):
        for unidad in generador(i, long_msg):
            if unidad in vistos:
                solapes += 1
                if primera_colision is None:
                    primera_colision = (vistos[unidad], i)
            else:
                vistos[unidad] = i
    print("  %-42s %s" % (nombre, ""))
    print("     mensajes simulados      : %d de %d bytes" % (n_mensajes, long_msg))
    print("     %-22s: %d" % (etiqueta_unidad + " reutilizados", solapes))
    if primera_colision:
        a, b = primera_colision
        print("     PRIMERA COLISION        : entre el mensaje %d y el %d" % (a, b))
    else:
        print("     PRIMERA COLISION        : ninguna")
    print()


print("=" * 86)
print(" REUSO DE KEYSTREAM EN EL PLANO DE DATOS")
print(" modelo exacto de libraries/GCS_MAVLink/GCS_KEMTLS.cpp:248-286")
print("=" * 86)
print()

LONG = 200      # tamano tipico de un mensaje MAVLink cifrado

print(" --- CODIGO ACTUAL, camino ChaCha20 (aead_alg = 1, EL PREDETERMINADO) ---")
informe("nonce constante, counter0 = seq", chacha_actual, 300, LONG, "bloques")

print(" --- CODIGO ACTUAL, camino AES-CTR (aead_alg = 2) ---")
informe("seq en el nonce, counter0 = 0", aesctr_actual, 300, LONG, "pares (nonce,bloque)")

print(" --- CORRECCION PROPUESTA: contador monotono de 64 bits ---")
informe("contador por mensaje, bloque reiniciado",
        lambda i, L: propuesto(i, L, BLOQUE_CHACHA), 300, LONG, "pares (contador,bloque)")

# --- el mismo barrido a escala, para la carta de respuesta -----------------------------
print("=" * 86)
print(" A ESCALA: cuando aparece la primera colision, segun el tamano del mensaje")
print("=" * 86)
print()
print(" %-14s %-30s %s" % ("tamano msg", "ChaCha20 actual", "AES-CTR actual"))
print(" " + "-" * 74)
for L in (32, 64, 100, 200, 280):
    # ChaCha20
    vistos, prim_c = {}, None
    for i in range(600):
        for u in chacha_actual(i, L):
            if u in vistos and prim_c is None:
                prim_c = (vistos[u], i)
            vistos.setdefault(u, i)
    # AES-CTR
    vistos, prim_a = {}, None
    for i in range(600):
        for u in aesctr_actual(i, L):
            if u in vistos and prim_a is None:
                prim_a = (vistos[u], i)
            vistos.setdefault(u, i)
    c = "mensajes %d y %d" % prim_c if prim_c else "sin colision"
    a = "mensajes %d y %d" % prim_a if prim_a else "sin colision"
    print(" %-14d %-30s %s" % (L, c, a))

print()
print(" LECTURA")
print("   ChaCha20 es el camino POR DEFECTO y colisiona en cuanto el mensaje supera un")
print("   bloque de 64 bytes: el mensaje n y el n+1 comparten keystream de inmediato.")
print("   AES-CTR aguanta hasta que seq da la vuelta, a los 256 mensajes.")
print()
print("   A los 50-100 Hz que declara el articulo, 256 mensajes son 2,6 a 5,1 segundos.")
print("   Para ChaCha20 el plazo es de un solo mensaje.")
print()
print("   Con un contador monotono de 64 bits y el bloque reiniciado por mensaje, no hay")
print("   colision --- ni la habra: 2^64 mensajes a 100 Hz son mas de cinco mil millones de anos.")
print()
print(" LO QUE ESTE TEST NO CUBRE, y hay que escribir aparte:")
print("   - un test que ENLACE el codigo real en vez de modelarlo")
print("   - la recuperabilidad del contador en el receptor bajo perdida de paquetes, que es")
print("     probablemente la razon por la que se eligio seq y el riesgo real de la correccion")
