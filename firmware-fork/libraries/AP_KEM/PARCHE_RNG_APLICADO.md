# Parche de RNG aplicado — 2026-09-08

`randombytes_linux.c`, `ap_kem.cpp` y `randombytes_status.h` de esta carpeta **ya no son
el codigo original de Carlos**. Llevan aplicado el parche del hallazgo A8.

- Fuente del parche: `experiments/rng_patch/`
- Original preservado en: `experiments/rng_patch/original_randombytes_linux.c`
  (y en el historial de git, antes de este commit)
- Prueba: `experiments/rng_patch/test_rng_patch.c` — 12 asertos, incluido un caso
  de contraste que ejercita el codigo original y demuestra el defecto.

```bash
cd experiments/rng_patch
gcc -std=c11 -Wall -Wextra -o test_rng_patch test_rng_patch.c && ./test_rng_patch
```

El defecto: `randombytes()` devuelve `void`, sin canal de error. Ante fallo hacia `break`
y retornaba dejando el bufer **sin inicializar**, en silencio. Ese bufer alimenta la
generacion de claves del KEM.

## Compatibilidad con el shim

`pqclean_randombytes_shim.c` declara que este archivo se compila con
`-Drandombytes=PQCLEAN_HQC128_CLEAN_randombytes`. El parche **no rompe eso**: solo
`randombytes` lleva el macro; `ap_kem_entropy_failed()` y `ap_kem_entropy_reset_for_test()`
son simbolos nuevos y no colisionan.

## Observacion aparte, NO corregida por este parche

El shim declara `void PQCLEAN_HQC128_CLEAN_randombytes(uint8_t*, size_t)`, mientras que la
definicion real toma `unsigned long long`. En x86-64 coinciden; en el **Cortex-A9 de 32 bits
del Bebop** no: `size_t` son 4 bytes y `unsigned long long` son 8. Es un desajuste de
prototipo preexistente en el codigo original, ajeno al hallazgo A8, y no se toca aqui.
Merece revision antes de cualquier compilacion real para la plataforma.
