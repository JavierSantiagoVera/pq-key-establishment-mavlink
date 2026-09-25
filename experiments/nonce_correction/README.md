# Núcleo de la construcción de nonce corregida (S2 del portátil)

**Qué es:** el contador monótono de ≥64 bits, la separación de dominio por dirección/época,
la ventana de repetición y el fail-closed que ya especifica el artículo
(`cas-sc-template.tex:1470-1473`), implementados como núcleo C aislado y probado. Es la
tarea **S2** de [`../../08_cierre/HANDOFF_PORTATIL.md`](../../08_cierre/HANDOFF_PORTATIL.md).

**Qué NO es:** no enlaza `GCS_KEMTLS.cpp` — `mavlink_cipher.h`, el cifrador del firmware
real, no está en este repositorio y no se espera que llegue (ver `HANDOFF_JAVIER.md`).
Tampoco decide la arquitectura firmware-vs-proxy: sirve igual para las dos, que es la razón
por la que el handoff la puso primero. La versión completa de este test bajo el diseño de
proxy (con las 70 000 tramas y las primitivas reales) es **T4** en
[`../proxy_c9/DISENO.md`](../proxy_c9/DISENO.md) §6 — hoy en suspenso junto con el resto de
esa arquitectura.

**Actualización 2026-09-17 — `demo_chacha20_real.c`:** enlaza esta construcción a un
ChaCha20 real (RFC 8439), implementado desde cero en
[`../crypto_vectors/chacha20.c`](../crypto_vectors/chacha20.c) porque tampoco existía ahí.
**Esto no resuelve la inferencia de `NOTAS_ONBOARDING.txt` §2.2** (si el firmware ausente
trata `counter0` como contador de bloque de RFC 7539) — sigue sin poder verificarse sin
`mavlink_cipher.h`. Lo que sí aporta: pasa de "los índices (nonce, bloque) no se repiten"
(aritmética) a un ataque de XOR **con bytes reales** — la construcción vieja recupera un
mensaje completo conociendo el otro, la corregida no. Ver "Demo con ChaCha20 real" abajo.

## Archivos

- `nonce_ctr.h` / `nonce_ctr.c` — contador de emisor, ventana de repetición del receptor,
  ensamblado de nonce de 12 B.
- `test_nonce_correction.c` — la suite. Compilar y correr:
  ```bash
  gcc -std=c11 -Wall -Wextra -Wpedantic -O2 -o test_nonce_correction \
      test_nonce_correction.c nonce_ctr.c && ./test_nonce_correction
  ```

## Qué prueba, y por qué alcanza

| # | Prueba | Por qué importa |
|---|---|---|
| 1 | **Control positivo:** el modelo de la construcción vieja (seq de 8 bits) colisiona antes de 256 mensajes | Sin esto, no hay garantía de que la suite sepa detectar una colisión real — es la misma disciplina que T4 de `DISENO.md` |
| 2 | La construcción corregida no repite (nonce, bloque) en miles de mensajes de tamaño variable | La prueba obligatoria del handoff (>256 mensajes) |
| 3 | Ventana de repetición: replay exacto se rechaza; reordenado dentro de la ventana se acepta; reordenado fuera se rechaza | Punto 4 de la especificación del artículo |
| 4 | Agotamiento del contador de 64 bits: la llamada siguiente falla, no da la vuelta a 0 | Punto 5 (fail-closed), el defecto original era exactamente envolver en silencio |
| 5 | Mismo contador en TX/RX o en épocas distintas da nonces distintos; las ventanas de replay son independientes entre sí | Punto 3 (separación de dominio) |

17 chequeos, `TODO CORRECTO` en la última corrida (2026-09-16).

## Demo con ChaCha20 real

`demo_chacha20_real.c` — compilar y correr:
```bash
gcc -std=c11 -Wall -Wextra -O2 -o demo_chacha20_real \
    demo_chacha20_real.c nonce_ctr.c ../crypto_vectors/chacha20.c && ./demo_chacha20_real
```

| Parte | Qué hace | Resultado (corrida 2026-09-17) |
|---|---|---|
| 1 — construcción vieja | Cifra dos mensajes MAVLink-símil distintos con `counter0=0` las dos veces (lo que pasa cuando `seq` de 8 bits da la vuelta) | `XOR(ct_a, ct_b) == XOR(claro_a, claro_b)`; el mensaje A se **recupera completo** solo con XOR y conociendo B, sin la clave |
| 2 — construcción corregida | 500 mensajes de longitud variable, contador de 64 bits real, 1920 bloques de keystream generados | Ningún bloque se repite; el mismo truco de XOR entre dos mensajes cualesquiera **ya no funciona** |
| 3 — rekey / cambio de época | Responde al defecto A5 de `gap_analysis.md` ("gestión de nonce/IV bajo rekeying no documentada"). Dos "épocas" (antes/después de un rekey), **misma clave a propósito** en las dos, contador reiniciado a 0 en la época nueva — justo el escenario que colisionaría sin separación de dominio | Con separación por época (prefijos de dominio distintos): no colisiona. **Control negativo:** con el mismo prefijo en las dos épocas (el bug que se evita), el nonce sí sale idéntico — confirma que es la separación la que salva el caso, no el azar |

## Fuzzing sin `tc netem` (experimento #4 de `08_cierre/README.md` §B-bis)

**Por qué sin `tc netem`:** el 2026-09-17 se confirmó que el kernel de este portátil
(CachyOS `7.1.6-1-cachyos`) no trae `netem` — ni módulo ni compilado adentro
(`tc qdisc add ... netem` da *"Specified qdisc kind is unknown"*, con `sudo` real, no es
un problema de permisos). Cambiar de kernel es invasivo y Javier decidió no hacerlo por
esto. Alternativa: `replay_window_t` no tiene E/S de red, así que lo único que le importa
de la red es el orden/repetición de las entregas — eso se puede fuzzear en el mismo
proceso, sin tocar el kernel.

`fuzz_replay_window.c` — compilar y correr:
```bash
gcc -std=c11 -Wall -Wextra -O2 -o fuzz_replay_window fuzz_replay_window.c nonce_ctr.c && \
    ./fuzz_replay_window
```

**Método:** comparación diferencial contra un oráculo independiente (misma
especificación, estructura de datos distinta: un arreglo de "visto" en vez de un bitmap),
sobre secuencias con pérdida/reordenamiento/duplicado simulados. **Control positivo**
(misma disciplina que el resto del repo): antes de confiar en "0 discrepancias", se corre
el mismo oráculo contra una variante deliberadamente rota (off-by-one en el límite de la
ventana) para confirmar que el fuzzer sí detecta un bug cuando lo hay.

Resultado de la corrida del 2026-09-17:

| Escenario | Entregas | Aceptadas | Discrepancias |
|---|---|---|---|
| Variante rota (control positivo) | 2927 | — | **1** (detectada, correcto) |
| Sin pérdida ni duplicado | 3000 | 3000 | 0 |
| 10% de pérdida | 2701 | 2701 | 0 |
| 10% de duplicado | 3274 | 3000 | 0 |
| 15% de pérdida + 10% de duplicado | 2819 | 2561 | 0 |

## Lo que queda fuera y por qué

- **El formato de cable exacto** (cuántos de los 8 B del contador viajan explícitos, si se
  reutiliza el timestamp de firma) es la decisión de B4/opción 3 ya tomada, pero el
  ensamblado aquí usa un prefijo de dominio simulado de 32 bits en vez del IV real de HKDF
  (`GCS_KEMTLS.cpp:344-345`, ya verificado correcto — no hay que tocarlo ni volver a probarlo
  aquí).
- **El coste en bytes** (8 B/trama, aritmética a partir de `uint64_t`) se cerró en
  [`B6_costo_bytes.md`](B6_costo_bytes.md), 2026-09-17. **El throughput real** en el
  enlace WiFi sigue siendo B6/M6 de la campaña — eso sí necesita el Bebop.
- **Enlazar el cifrador real** (T1–T3, T5–T6 de `DISENO.md`) espera al fork de Nicolás.
