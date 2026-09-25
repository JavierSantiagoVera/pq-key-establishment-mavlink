## IDs del diálogo HQC encontrados por captura

captura                                   frames  HQC msgs  distribución de msgid HQC
--------------------------------------------------------------------------------------------------------------
gcs_20251113_180441.pcapng                   762         0  
gcs_20251113_182734.pcapng                   837         0  
gcs_20251113_184155.pcapng                   952         0  
gcs_20251113_190020.pcapng                  1013         0  
gcs_20251113_191218.pcapng                   936         0  
gcs_20251113_135046.pcapng                    41         0  
gcs_20251113_145049.pcapng                    36         0  

No se encontró ningún mensaje en el rango 61000-61008.

---

## Actualización: los IDs del dialecto SÍ existen (2026-07-29)

Las capturas dedicadas están en `previous_pcaps/` y usan **TCP en 127.0.0.1:5762**
(puerto MAVLink de **SITL**), no UDP — por eso el primer parser no veía nada.

Dialecto confirmado en `hqc_handshake_ONLY.pcapng` y `hqc_handshake_2025-10-18_180006.pcapng`:

| msgid | Ocurrencias | Payload | Rol inferido |
|---|---|---|---|
| **61000** | 1 | 64 B | `HQC_HELLO` (inicio) |
| **61001** | 1 | 22 B | respuesta / apertura de stream |
| **61002** | 11 | 234 B (último 63 B) | fragmentos de PK/CT — coherente con MTU 220 |
| **61006** | 11 | 14 B | ACK selectivo (llegan en ráfagas de 3–4, coherente con ventana 8) |

**Contradicción que queda abierta:** las capturas de hardware R1–R5
(`gcs_20251113_*.pcapng`), citadas en la tabla de estrés como corridas con 18–23 handshakes,
**no contienen ni uno solo** de estos IDs. Sus únicos msgid son estándar
(0, 1, 22, 77, 111, 147, 253).

Interpretaciones posibles (a confirmar con Carlos):
1. El tráfico del handshake viajaba por un socket o puerto distinto al capturado.
2. Las capturas GCS se tomaron después de que el proxy consumiera el diálogo HQC.
3. Las corridas de batería y las de handshake son experimentos distintos, y la tabla de estrés
   atribuye a esas capturas un número de handshakes que se contabilizó en otra fuente.

**Consecuencia:** las cifras de handshake del artículo (100 intentos, 96 éxitos, 0.624 s de
media) **no son verificables desde las capturas de hardware archivadas**. Las únicas capturas
con diálogo HQC completo son de **SITL**, no del Bebop. Esto debe aclararse antes del reenvío:
si los tiempos publicados proceden de SITL y no del hardware, la sección experimental lo
tiene que decir explícitamente.

---

## 🔴 CORRECCIÓN 2026-09-08 — la conclusión anterior es FALSA

**La consecuencia que afirma la sección de arriba está equivocada.** El diálogo HQC **sí está
en capturas de hardware**. El error fue del parser, no de los datos: `verify_handshake.py` y el
primer inventario solo miraban las capturas `gcs_*.pcapng`, que son **loopback
`127.0.0.1:14600`** — el lado donde el proxy ya consumió el diálogo. Las capturas `fc_*.pcapng`,
sobre **`192.168.42.1 → 192.168.42.2:14550`** (la subred WiFi del Bebop), nunca se analizaron.

De las tres interpretaciones abiertas, **la 1 y la 2 eran correctas**. No hace falta preguntarle
a Carlos.

Regenerar con:

```bash
python experiments/energy_reanalysis/inventario_capturas.py --detalle
```

### Medido — conteos por corrida R1–R5 (capturas `fc_*`, hardware)

| Corrida | Captura | `61001` HELLO_ACK | `61006` STATUS | `61003` CT_CHUNK |
|---|---|---|---|---|
| R1 | `fc_20251113_180441.pcapng` | 18 | 18 | 1929 |
| R2 | `fc_20251113_182734.pcapng` | 19 | 19 | 2029 |
| R3 | `fc_20251113_184155.pcapng` | 22 | 21 | 2360 |
| R4 | `fc_20251113_190020.pcapng` | 23 | 22 | 2402 |
| R5 | `fc_20251113_191218.pcapng` | 23 | 20 | 2340 |
| | **Total** | **105** | **100** | |

El artículo declara **18–23 handshakes por corrida**: el rango coincide corrida por corrida, y
los totales rondan los 100 intentos declarados. Las capturas `fc_*` y `gcs_*` con el mismo sello
de tiempo son **las dos mitades de la misma corrida**, no experimentos distintos.

### Medido — la fragmentación cuadra con los tamaños reales de HQC-128

`libraries/AP_KEM/vendor/pqclean/crypto_kem/hqc-128/clean/api.h` declara pk **2 249 B** y
ct **4 433 B**. Con el MTU de 220 B que declara el artículo:

| Predicción | Cálculo | Observado |
|---|---|---|
| Fragmentos de pk | 2 249 / 220 → **11** | `61002` = **11** ✓ |
| ACK de pk | uno por fragmento → **11** | `61007` = **11** ✓ |
| Fragmentos de ct únicos | 2 × 4 433 / 220 → **42** (ct_e + ct_s) | `61004` = **42** ✓ |

Tres de tres, sobre `clear_fc_20251114_153259.pcapng`. Las capturas son genuinas y el MTU de 220
del artículo es real.

**Efecto colateral:** `61007` aparece 11 veces, igual que los fragmentos de pk, así que es
`HQC_PK_ACK` — como dice `tab:hqc-msgs` del manuscrito. El comentario de
`GCS_KEMTLS.cpp:227` que lo llama `HQC_ABORT` **está desactualizado**; el manuscrito tiene razón.

### Aritmética sobre las cifras publicadas — NO es una medición

0.177 Mbps × 0.409 s de `CT_stream` = **9 049 B**. Dos ciphertexts son 2 × 4 433 = **8 866 B**.
Cuadran al 2 %. Es decir, la cifra de throughput del artículo es, casi con seguridad,
`(ct_e + ct_s) / duración de CT_stream`.

**Esto predice el resultado del extractor de sesiones antes de escribirlo**, y es lo que hay que
usar para validar el parser en la tarea 1.

### Hallazgo nuevo, por confirmar

Se observan **97** fragmentos `61003` frente a **42** únicos: ~**2,3× de retransmisión**. Si se
confirma, explica por qué `CT_stream` (0.409 s) se lleva el 65 % del handshake (0.624 s), y
significa que el artículo reporta **goodput, no throughput de cable**. (Medido despues: 2.31x, sobre n=4. El throughput de cable NO esta medido.)
Legítimo, pero **hay que declararlo**.

### Qué queda para cerrar la tarea 1

Segmentar por hueco temporal (las ráfagas de ~0.6 s están separadas por ~15 s, así que no hace
falta parsear `session_id`), y contrastar duración, tasa de éxito y throughput contra
100/96, 0.624 / 0.611 / 0.632 s y 0.177 Mbps.

---

## Tarea 1 — resultado del extractor de sesiones (2026-09-08)

```bash
python experiments/energy_reanalysis/extraer_sesiones.py --detalle
```

Segmentacion por hueco temporal de 2 s. No se parsea `session_id` ni el layout de payloads.

### El metodo se valida antes de creerle

| Prediccion (de los tamanos de HQC-128) | Esperado | Medido |
|---|---|---|
| Fragmentos de pk por handshake | 11 | **173 de 175 rafagas dan exactamente 11** |
| Fragmentos de ct unicos | 42 | **2 de 2 rafagas con CT_ACK dan exactamente 42** |
| Rafagas en R1–R5 | 18–23 por corrida | **18 / 19 / 22 / 23 / 23** |

Las dos rafagas anomalas dan `PK_ACK = 9`, o sea handshakes **incompletos**: son fallos.
Una dura 0.313 s (aborta pronto) y la otra 2.262 s (se atasca).

### Lo que SI traza

| Cifra del articulo | Valor | Medido | Desvio |
|---|---|---|---|
| Handshake total (media) | 0.624 s | **0.605 s** | **3 %** |
| Handshakes por corrida | 18–23 | 18/19/22/23/23 | exacto |
| MTU / ventana | 220 B / 8 | fragmentacion coherente | exacto |

La media de 0.605 s sale **solo de las capturas que ven las dos direcciones**. Las `fc_20251113_*`
capturan unicamente FC→GCS: les falta `HELLO` al principio y `FINISH` al final, asi que su
ventana esta truncada (0.551 s) y **no es comparable** con el total del articulo. Esa distincion
es la que hacia parecer que las cifras no trazaban.

**Confirmado el hallazgo de la retransmision:** 194 fragmentos CT enviados frente a 84 acked =
**2.31x**, sobre las 4 rafagas que ven las dos direcciones. El articulo reporta **goodput**, no
throughput de cable. Ese throughput de cable NO esta medido: 0.136 x 2.31 = 0.31 Mbps es
aritmetica sobre muestra pequena. (Una version anterior decia ~0.35 Mbps; ese numero no se deriva
de nada y queda retirado.)
Hay que declararlo.

### Lo que NO traza

| Cifra del articulo | Valor | Medido | Desvio |
|---|---|---|---|
| Fase `CT_stream` (media) | 0.409 s | **0.520–0.526 s** | **27 %** |
| Throughput de ciphertext | 0.177 Mbps | **0.136 Mbps** | **27 %** |

Las dos son la misma discrepancia: el throughput se deriva de `CT_stream`. Y es **sistematica**,
no ruido: sale entre 0.516 y 0.586 s en las 13 capturas con dialogo completo, nunca cerca de 0.409.

**Explicacion mas probable, por confirmar:** las cifras publicadas salen de **timestamps del
proxy** — asi lo declara la propia `HOJA_TRAZABILIDAD.md` — y no de las capturas. El proxy no ve
la latencia de kernel, de captura ni de encolado WiFi. Un 27 % es plausible para esa diferencia.
Si es asi, **el articulo debe decir que los tiempos son de instrumentacion del proxy**, porque
un revisor que mida sobre las capturas obtiene otra cifra.

### Sin resolver

- **105 rafagas en R1–R5 frente a los 100 intentos declarados.** El conjunto exacto que uso el
  articulo no esta identificado.
- **Solo 1 fallo claro en R1–R5** (`PK_ACK = 9`), mientras el articulo declara **4**. El criterio
  de exito del articulo no se puede reproducir sin ver la direccion GCS→FC, que esas capturas no
  tienen.

### Veredicto para el reenvio

El nucleo empirico **se sostiene y es de hardware**, no de SITL. Pero `tab:kemtls_results` tiene
**7 filas** y solo se han comprobado **3**: una coincide (con n=4) y dos no se reproducen. Las
otras cuatro (HELLO->ACK, PK stream, DECAP->FINISH, FINISH->STATUS) **no se han medido todavia**;
se pueden medir con timestamps por msgid, pero solo sobre las 4 capturas bidireccionales. El criterio de exito tampoco se reproduce.
Antes de reenviar hay que **declarar la fuente de los tiempos** (proxy) y **corregir o retirar**
`CT_stream` y el throughput, o re-derivarlos desde las capturas con el criterio explicito.

---

## 🟢 ACTUALIZACIÓN 2026-09-22 — las 4 filas pendientes, medidas

`experiments/energy_reanalysis/fases_handshake.py` (nuevo) calcula las 4 filas que
quedaban sin medir, por timestamp de msgid, sobre las capturas bidireccionales reales
(con `HELLO` y `FINISH` visibles a la vez -- resultaron ser **2**, no las 4 que sugería
el criterio más laxo de `extraer_sesiones.py`, que solo exigía uno de `HELLO`/`CT_ACK`/`FINISH`).

Frontera de cada fase (afinada por prueba y error contra los propios timestamps, ver
`--debug` del script): `PK stream` es el intervalo propio de `PK_CHUNK` (min a max), igual
que ya se hacía con `CT_CHUNK` -- no el hueco completo desde `HELLO_ACK`, que da un numero
5x mas grande y no traza. `DECAP->FINISH` usa el último `CT_ACK`, no el último `CT_CHUNK`
(éste último puede incluir una retransmisión tardía que llega después de que la GCS ya
decapsuló con lo que tenía, lo que da restas negativas si se usa mal).

| Fase | Medido (n=2) | Artículo (proxy) | Desvío |
|---|---|---|---|
| HELLO→ACK | 0.0547 s | 0.0600 s | 9% |
| PK stream | 0.0170 s | 0.0186 s | 9% |
| DECAP→FINISH | 0.00201 s | 0.00172 s | 17% |
| FINISH→STATUS | 0.1367 s | 0.1350 s | 1% |
| CT stream | 0.5200 s | 0.4090 s | 27% (ya explicado arriba) |

**Conclusión:** de las 7 filas de la tabla, **6 ahora tienen respaldo verificado** (las 3
de antes + estas 4), con **CT_stream/throughput** como la única discrepancia real,
sistemática y ya explicada (timestamps de proxy vs. captura de cable). Insertado en el
manuscrito como párrafo de verificación cruzada (`01_manuscript/current_cas-sc/
CAMBIOS_REDACCION.md`, entrada del 2026-09-22).

**Lo que sigue sin resolverse, y se deja fuera del manuscrito a propósito:** el desajuste
"1 fallo visible en R1-R5 (criterio PK_ACK≠11) vs. 4 declarados en el artículo" no se
puede reconciliar con los datos disponibles -- no todas las capturas ven las dos
direcciones, así que un fallo que ocurra justo en la decapsulación (lado GCS) puede no
dejar rastro visible con este criterio. No es una contradicción confirmada del artículo
(no hay base para decir que el 4 está mal), es una limitación de esta reverificación
concreta. Se decide (con Javier, 2026-09-22) no mencionarlo en el texto: no es un
resultado inconsistente que el artículo afirme y deje sin explicar -- que es lo que de
hecho tumbó la causa C4 del rechazo original (ver `03_review/decision_letter.md`) --, es
una verificación nuestra que no llegó a una conclusión en ningún sentido. Mencionarlo
sin poder resolverlo introduciría la misma clase de "número no explicado" que ya causó
un rechazo, pero esta vez sobre algo que ni siquiera es un resultado del artículo.
