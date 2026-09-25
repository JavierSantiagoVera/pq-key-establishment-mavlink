# B4 — resultados del experimento sobre la opción 1

**Fecha:** 2026-09-09. Complementa [`B4_formato_nonce.md`](B4_formato_nonce.md), §5, opción 1.

```bash
py -3 experiments/nonce_collision/B4_experimento_firma.py
```

Sin dependencias. Mide **lo que hubo en el cable** en las 30 capturas archivadas, no lo que el
código pretendía. 71 240 tramas MAVLink 2, de las cuales 9 239 firmadas.

---

## Resumen

Los dos `NO VERIFICADO` de la opción 1 quedan resueltos, y aparece un tercer hecho que no estaba
previsto y que **mejora** la opción en vez de hundirla.

| Pregunta | Respuesta |
|---|---|
| ¿La firma está activa de verdad? | **Sí**, y con cobertura del 99,5–100 % en el lado FC con sesión activa |
| ¿Es correcto el layout de 13 B? | **Sí**, confirmado empíricamente |
| ¿El timestamp es monótono y único? | **Sí dentro de la sesión.** Pero **no es un reloj** — ver §3 |

---

## 1. La firma está activa, y la cobertura depende de dónde se mire

El 13 % global engaña: está diluido por los fragmentos del handshake, que son cleartext **por
diseño** (`mavlink_is_cleartext_msg`). Excluyendo el dialecto HQC y contando solo desde la primera
trama firmada de cada captura:

| Grupo de capturas | Cobertura | Lectura |
|---|---|---|
| `fc_20251114_164939`, `fc_20251114_171039` | **100,0 %** | sesión activa de principio a fin |
| `clear_fc_20251114_*` | **99,5 %** | ídem |
| `fc_20251113_*` (corridas de estrés R1–R5) | **45–53 %** | alternan rachas firmadas y sin firmar, una pareja por sesión; mecanismo sin identificar (ver [`../signing_policy/HALLAZGO_firma_no_exigida.md`](../signing_policy/HALLAZGO_firma_no_exigida.md) §7) |
| `gcs_*` (loopback) | **0,2–3,5 %** | ver §5: en el sentido GCS→FC la falta de firma es real |

**Lectura para B4:** en régimen permanente — que es exactamente cuando aplica el cifrado del plano
de datos — la firma cubre prácticamente todas las tramas **del lado FC**. En el sentido GCS→FC no
hay firma y el FC no la exige (§5), así que ahí la opción 1 no tiene material hasta que se exija.

## 2. El layout de 13 B es correcto

Se contrastaron dos hipótesis que fallan de forma parecida y hay que distinguir:

| Hipótesis | Resultado |
|---|---|
| **H1** · época 1-ene-2015 (especificación MAVLink 2) | **0 de 9 239** |
| **H2** · contador que arranca en 0 al abrir sesión | **9 239 de 9 239** |

Los seis bytes se decodifican a un valor coherente y acotado, así que **el layout
`link_id(1) + timestamp(6) + firma(6)` es el correcto**. Lo que no se cumple es la semántica de
época. Esto era `NO VERIFICADO` en `B4_formato_nonce.md` §5 y queda cerrado.

## 3. Hallazgo no previsto: **no es un reloj, es un contador por mensaje**

En `fc_20251114_164939.pcapng`, valores en crudo:

```
primeros 8:  6000000, 6000001, 6000002, 6000003, 6000004, 6000005, 6000006, 6000007
últimos  8:  6001092, 6001093, ..., 6001099
n = 1100     distintos = 1100
```

| Observable | Valor |
|---|---|
| Tiempo de pared entre la 1.ª y la última trama firmada | **958,4 s** |
| Avance del campo traducido a segundos | **0,011 s** |
| Capturas donde el campo avanza < 10 % del tiempo de pared | **20 de 20** |

El campo **no sigue el tiempo real**. Avanza exactamente **+1 por trama firmada**, y arranca en la
constante **6 000 000** en todas las sesiones.

### Por qué esto es una buena noticia

Un reloj tiene un problema como nonce: dos mensajes emitidos dentro del mismo tick comparten valor.
Con un tick de 10 µs es improbable, pero «improbable» no es la garantía que necesita un nonce —
necesita ser **imposible**. Un contador por mensaje **no tiene ese problema por construcción**:
1100 valores distintos en 1100 tramas, medido.

### Por qué a la vez obliga a decir algo en el manuscrito

Arranca en la **misma constante en cada sesión**. Sesión 1 mensaje 1 y sesión 2 mensaje 1 reciben
ambos el `6 000 000`. Si la clave fuera la misma, eso es reutilización de nonce inmediata.

**Lo que lo salva** es que `iv_tx` / `k_tx` se derivan del handshake, así que cada sesión tiene
clave distinta y la terna (clave, nonce, contador) no se repite. Es correcto — pero significa que
la unicidad **no la aporta el timestamp, la aporta la frescura de la clave de sesión**. Eso hay
que escribirlo, no darlo por hecho: es precisamente el tipo de suposición implícita que produjo el
defecto original.

## 4. Validación cruzada: los retrocesos son fronteras de sesión

Si el contador se reinicia al abrir sesión, los retrocesos dentro de una captura deben ser
(handshakes − 1). Los handshakes los contó la tarea 1 por un camino **independiente** (huecos
temporales en el dialecto HQC):

| Captura | Retrocesos | Handshakes − 1 | |
|---|---|---|---|
| `fc_20251113_180441` | 17 | 17 | **OK** |
| `fc_20251113_182734` | 18 | 18 | **OK** |
| `fc_20251113_184155` | 20 | 21 | −1 |
| `fc_20251113_190020` | 21 | 22 | −1 |
| `fc_20251113_191218` | 19 | 22 | −3 |

Dos exactos y tres cortos. Los dos métodos se validan mutuamente, y la diferencia tiene una
lectura directa: **la firma se activa solo cuando el handshake completa**
(`GCS_KEMTLS.cpp:942-943`, dentro de `verify_finish_and_derive`). Una ráfaga que no llega a
activar la firma es un handshake que **no completó**.

Sesiones que sí activaron firma: 18 + 19 + 21 + 22 + 20 = **100**, sobre **105** ráfagas contadas
en la tarea 1.

> **Pista para una de las preguntas abiertas.** El artículo declara 100 intentos / 96 éxitos. La
> tarea 1 contó 105 ráfagas y 100 mensajes `61006 STATUS`. Ahora un tercer camino independiente
> —la activación de la firma— también da **100**. Que tres señales converjan en 100 sugiere que
> el «100» del artículo es el número de sesiones **completadas**, no de intentos, y que hubo 105
> intentos. No lo cierra: sigue sin explicar el 96. Pero acota dónde buscar, y conviene
> mencionárselo a Nicolás.

## 5. Riesgo cerrado en contra (2026-09-10): el GCS no firma, y el FC no lo exige

Aquí se había supuesto que la baja cobertura del lado GCS se debía a que esas capturas son
loopback. **Para el sentido GCS→FC ese supuesto era falso.** Separando la cobertura por sentido en
las dos únicas capturas bidireccionales del WiFi, **0 de 12 tramas GCS→FC van firmadas**, y el FC
procesa comandos sin firma con la sesión ya activa, porque en el canal 0 —que en el Bebop es el
WiFi— `accept_unsigned_callback` lo acepta todo.

Detalle, código y consecuencias para el manuscrito: [`../signing_policy/HALLAZGO_firma_no_exigida.md`](../signing_policy/HALLAZGO_firma_no_exigida.md).

## 6. Contraste con el campo que se usa hoy

| | |
|---|---|
| Valores distintos de `seq` observados | **256** (el campo es `uint8_t`) |
| Tramas totales | **71 240** |
| Repeticiones forzadas | **≥ 70 984** |

No es una estimación: es el principio del palomar. Con 71 240 tramas y 256 valores posibles, no
hay forma de que `seq` no se repita.

---

## 7. Qué cambia en la recomendación

**Nada en la dirección, todo en la solidez.** La opción 1 sigue siendo la recomendada, y ahora se
apoya en medidas en vez de en la especificación. Se añaden tres condiciones que antes no estaban:

1. **Declarar que la unicidad la aporta la frescura de la clave de sesión**, no el contador — que
   se reinicia en 6 000 000 en cada sesión.
2. **Exigir la firma en el sentido GCS→FC.** Medido el 2026-09-10: el GCS no firma y el FC acepta
   tramas sin firma en el canal 0. Hace falta en cualquier caso para que se sostenga la afirmación
   de integridad del artículo. Ver [`../signing_policy/HALLAZGO_firma_no_exigida.md`](../signing_policy/HALLAZGO_firma_no_exigida.md).
3. **Fail-closed explícito:** si una trama no lleva firma, no se cifra y no se acepta. Con
   cobertura del 100 % en régimen permanente el coste operativo es nulo, pero la regla tiene que
   estar en el código y en el manuscrito.
