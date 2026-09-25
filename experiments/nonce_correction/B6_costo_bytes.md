# B6 — coste en bytes de la construcción corregida (2026-09-17)

**Qué es:** la mitad de B6 que se puede cerrar sin el Bebop — cuántos bytes de más pesa
cada trama con la construcción corregida (B4 opción 3, `nonce_correction/`). La otra
mitad de B6 (throughput real medido en el enlace) necesita la campaña real, ver
`08_cierre/PLAN_CAMPANA.md` §3, M6.

**Por qué se recalcula:** `experiments/nonce_collision/B4_formato_nonce.md` §6 daba
"6,4 kbps" para la opción 3 como *plan B*, cuando la recomendada era la opción 1 (coste
cero). El criterio de fidelidad al artículo del 2026-09-16 invirtió esa decisión: la
opción 3 es la que se implementó (`nonce_correction/nonce_ctr.h`), así que este cálculo
dejó de ser un plan B y pasa a ser el costo real de lo que hoy es la única construcción
implementada.

## El cálculo — aritmética, no medición

La especificación del artículo (`cas-sc-template.tex:1470-1473`) exige un contador
**"carried explicitly rather than inferred from a received field"**. En
`nonce_ctr.h`/`nonce_ctr.c`:

- `sender_ctx_t.next_counter` es `uint64_t` — **8 bytes**, por definición del tipo en C
  (`uint64_t` es exactamente 64 bits; no es algo que haga falta medir, es una garantía
  del estándar).
- `assemble_nonce(domain_prefix, counter, out[12])` arma un nonce de 12 B: 4 B de
  prefijo de dominio (dirección + época) + **8 B del contador**. El prefijo de dominio
  **no viaja por trama** — sale de HKDF una vez por sesión/época
  (`GCS_KEMTLS.cpp:344-345`, ya verificado), así que no es coste recurrente.
- La ventana de repetición (`replay_window_t`) es estado del **receptor**, no viaja por
  el cable — coste cero en tránsito.

**Coste por trama del plano de datos: exactamente 8 bytes**, ni uno más — el contador
explícito de ≥64 bits que pide la especificación, y nada del resto de la construcción
tiene coste recurrente.

## Contexto: cuánto es eso en throughput

No hay un ancho de banda único; depende de a qué tasa se manden tramas del plano de
datos. Dos referencias, las dos aritmética sobre cifras que sí trazan a un archivo:

| Referencia | Tasa | Cálculo | Overhead |
|---|---|---|---|
| El artículo mide el enlace a | 0,177 Mbps (goodput, `08_cierre/README.md` §3.4) | — | — |
| `B4_formato_nonce.md` (opción 3, con la tasa que asumía ese documento) | 100 Hz | 8 B × 100 Hz × 8 bit/B | 6,4 kbps → **3,6 %** de 0,177 Mbps |
| Este portátil, medido hoy contra SITL (`baseline_harness/README.md`, rehearsal 2026-09-17) | M1/M2 a 10 Hz, M3 (`ATTITUDE`) a 50 Hz | 8 B × 60 Hz combinado × 8 bit/B | 3,84 kbps → **2,2 %** de 0,177 Mbps |

**Ninguna de las dos filas es una medición de throughput real** — son bytes/trama (un
hecho de la construcción) multiplicados por una tasa de mensajes (elegida o medida en
SITL, no en el Bebop). El overhead real en el enlace WiFi del Bebop puede diferir por
efectos de capa MAC, fragmentación, retransmisión (el artículo ya reporta 2,31× de
retransmisión del plano de handshake, `08_cierre/README.md` §3.5) que esta cuenta no
incluye. **Eso es lo que le queda a B6 real, en la campaña con el Bebop.**

## Qué declarar en el manuscrito (para cuando se redacte, no ahora)

Reemplaza la cifra "6,4 kbps" heredada de la opción 1-vs-3 en suspenso:
*"the corrected construction adds exactly 8 bytes per data-plane frame — the ≥64-bit
explicit counter required by the specification — with no other recurring per-frame
cost; at the manuscript's reported command/telemetry rates this is on the order of a
few percent of the measured link throughput, though the real-link overhead (MAC
retransmission, fragmentation) requires on-hardware measurement, identified as B6/M6
future work."*
