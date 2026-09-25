# Vectores de prueba de las primitivas (experimento #1 de `08_cierre/README.md` §B-bis)

**Qué es:** prueba las funciones de hash/derivación de clave que usa
[`GCS_KEMTLS.cpp`](../../firmware-fork/libraries/GCS_MAVLink/GCS_KEMTLS.cpp)
contra vectores oficiales (FIPS 180-2, RFC 4231, RFC 5869), para que dejen de ser una
caja negra — hoy no hay ni un vector de prueba de estas primitivas en el repo. Es T1 de
[`../proxy_c9/DISENO.md`](../proxy_c9/DISENO.md) §6, adelantado sin esperar el fork.

**No depende del fork:** las primitivas se validan solas, con el código que ya está en
el snapshot de `02_repo/`.

## Qué se prueba contra código REAL, qué contra una copia, y qué no se prueba

| Función | Origen de lo probado | Vector | Traza |
|---|---|---|---|
| `sha256()` | **Real y enlazado**, sin modificar: `libraries/AP_KEM/vendor/pqclean/common/sha2.c` | FIPS 180-2 (`""`, `"abc"`, mensaje de 448 bits) | verificado también con `hashlib.sha256` de Python (stdlib) antes de escribirlo, ver historial |
| `hmac_sha256()` | Copia textual de `GCS_KEMTLS.cpp:153-177` (solo se quitó `static`), llamando al `sha256()` real de arriba | RFC 4231 casos 1 y 2 | ídem, verificado con `hmac`/`hashlib` de Python |
| `hkdf_extract()` | Copia textual de `GCS_KEMTLS.cpp:180-184` | RFC 5869 Apéndice A.3 ("sin salt") | la función **solo acepta salt de 32 B** (`klen=32` fijo en la llamada interna) — por diseño, el salt del protocolo siempre sale de un `sha256` anterior. Por eso el caso que aplica es A.3 (32 B de ceros), no A.1/A.2 (13 B/80 B), que no calzan con esta firma |
| `hkdf_expand_label()` | Copia textual de `GCS_KEMTLS.cpp:187-209` | **No hay vector oficial**: es una construcción propia del proyecto (prefijo de dominio `"ardupilot-hqc-v1:"` + etiqueta + contexto, una sola ronda porque `L ≤ 32` cabe en un bloque de SHA-256) — RFC 5869 no define esta variante | comparación cruzada contra [`referencia_hkdf_expand_label.py`](referencia_hkdf_expand_label.py), una segunda implementación independiente (stdlib `hmac`/`hashlib`, no reutiliza nada de este repo) |
| ChaCha20 (RFC 8439) | Implementación **nueva**, escrita para esta carpeta (`chacha20.c`) — no es una copia de nada del proyecto, porque `mavlink_cipher.h`, de donde saldría la implementación real, **no está en el snapshot de `02_repo/`** (`grep -r mavlink_cipher` no encuentra el archivo) | 36/36, por comparación diferencial contra el ChaCha20 de la librería `cryptography` de Python (`referencia_chacha20.py`), no contra vectores de la RFC copiados a mano — ver "ChaCha20" abajo | Da un cifrador real para enlazar a [`../nonce_correction/demo_chacha20_real.c`](../nonce_correction/demo_chacha20_real.c) y al microbenchmark de energía. **No es** el cifrador del firmware — eso sigue bloqueado por el fork |

**Por qué copiar y no enlazar el `.cpp` original:** `GCS_KEMTLS.cpp` incluye
`GCS.h`/`AP_HAL.h`/etc. (el HAL completo de ArduPilot) y no compila fuera del árbol de
`waf`. Copiar las tres funciones estáticas (sin tocar una línea, solo quitando `static`)
es la única manera de probarlas sueltas hoy. Si `GCS_KEMTLS.cpp` cambia esas líneas en el
futuro, hay que repetir la copia — no hay ningún mecanismo automático que las mantenga
sincronizadas.

**Medido / inferido:** el resultado de `sha256()` es medido contra código real y
enlazado. `hmac_sha256`/`hkdf_extract`/`hkdf_expand_label` son medidos contra una copia
textual — la garantía de que valen para el firmware depende de que la copia sea fiel
(se puede reverificar con un `diff` contra `GCS_KEMTLS.cpp:153-209` en cualquier momento).
ChaCha20 queda **inferido/pendiente**, no hay nada que medir todavía.

## Compilar y correr

```bash
cd experiments/crypto_vectors

# 1. sha2.c es C real de ArduPilot: se compila con gcc, no con g++
#    (g++ trata los .c como C++ y falla por conversiones implicitas void* -> T*)
gcc -std=c11 -Wall -Wextra -O2 -c \
    ../../firmware-fork/libraries/AP_KEM/vendor/pqclean/common/sha2.c \
    -o sha2.o

g++ -std=c++17 -Wall -Wextra -O2 -c kemtls_primitives.cpp -o kemtls_primitives.o
g++ -std=c++17 -Wall -Wextra -O2 -c test_vectores_primitivas.cpp -o test_vectores_primitivas.o
g++ -o test_vectores_primitivas sha2.o kemtls_primitives.o test_vectores_primitivas.o
./test_vectores_primitivas
```

## Resultado de la corrida del 2026-09-16

```
7/7 OK
```

(Los binarios `*.o` y el ejecutable no se versionan, ver `.gitignore`; se reproducen con
el comando de arriba.)

## ChaCha20

`chacha20.h`/`chacha20.c` es una implementación nueva de ChaCha20 (RFC 8439) — no existía
ninguna en el repositorio. Se validó por **comparación diferencial** contra el ChaCha20 de
la librería `cryptography` de Python, no contra vectores de la RFC tecleados a mano (el
error de transcripción de arriba fue motivo suficiente para no repetir el método).

```bash
python3 referencia_chacha20.py > vectores_chacha20.txt   # 36 casos: fijos + aleatorios
gcc -std=c11 -Wall -Wextra -O2 -c chacha20.c -o chacha20.o
gcc -std=c11 -Wall -Wextra -O2 -c test_chacha20.c -o test_chacha20.o
gcc -o test_chacha20 chacha20.o test_chacha20.o
./test_chacha20 vectores_chacha20.txt
```

Resultado de la corrida del 2026-09-17: **36/36 OK**. Antes de confiar en la convención de
`cryptography` para el contador de bloque (4 B little-endian + nonce de 12 B), se verificó
que coincide con RFC 8439 #2.4.2 en los primeros 60 B (los que se recordaban de memoria; el
resto del vector tecleado tenía error) y, de forma independiente de cualquier texto, que
`bloque(counter=1) == bytes[64:128]` de `bloque(counter=0)` — la semántica de contador de
bloque de RFC 7539/8439 que asume `nonce_ctr.h`.

## Lo que faltó al escribir el primer vector

Los siete vectores hex se transcribieron primero **truncados en un dígito** (63 en vez
de 64 caracteres = 32 B), y las primeras corridas fallaron 0/7. Se detectó comparando la
longitud de cada literal con Python (`len(...)`) antes de aceptar cualquier fallo como
real. Vale como recordatorio del propio criterio del proyecto: un fallo de test no es un
hallazgo hasta que se descarta que el vector de comparación esté mal escrito.
