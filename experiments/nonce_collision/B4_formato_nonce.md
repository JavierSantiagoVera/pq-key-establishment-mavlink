# B4 — Formato de cable del nonce corregido

**Estado:** análisis cerrado, **decisión pendiente de Javier**.
**Fecha:** 2026-09-09. **Bloquea:** B5 (implementación), B6 (coste), C9 (proxy), D13 (carta).

Todo lo que sigue está verificado contra archivos del repositorio. Lo que no, va marcado
`NO VERIFICADO`.

> **Actualización del mismo día.** Los dos `NO VERIFICADO` que afectaban a la opción 1 se han
> resuelto midiendo sobre las capturas: ver [`B4_RESULTADOS_firma.md`](B4_RESULTADOS_firma.md).
> La firma **está activa** (99,5–100 % de cobertura en el lado FC con sesión activa), el layout de
> 13 B **es correcto**, y el timestamp resulta ser **un contador por mensaje, no un reloj** — lo
> que para un nonce es mejor. La recomendación no cambia; gana tres condiciones que hay que
> declarar.
>
> **Actualización del 2026-09-10.** La incógnita que quedaba, la cobertura GCS→FC, se cerró **en
> contra**: el GCS no firma y el FC no lo exige — ver [`../signing_policy/HALLAZGO_firma_no_exigida.md`](../signing_policy/HALLAZGO_firma_no_exigida.md). La opción 1 sigue
> siendo la recomendada, pero ahora con una condición previa: exigir la firma en los dos sentidos,
> que hace falta de todos modos para la afirmación de integridad.

---

## 1. Qué se decide aquí, y por qué no es un cambio de tipo

La tentación es pensar que esto se arregla ensanchando un `uint8_t` a `uint64_t`. No es así,
y conviene entender por qué antes de mirar las opciones.

El nonce lo tiene que reconstruir **el receptor**, y el receptor solo dispone de lo que viaja
en el cable. El campo `seq` de MAVLink es de 8 bits **en el propio formato de trama**: aunque
el emisor lleve internamente un contador de 64 bits, el receptor sigue recibiendo 8 bits y no
puede adivinar los otros 56 tras una pérdida de paquetes.

Por eso B4 es una decisión de **formato de cable**, no de código: hay que elegir qué información
adicional viaja, o de qué campo ya existente se saca. Esa elección es la que no se deshace barato.

---

## 2. El defecto, verificado hoy contra el código

| Archivo:línea | Qué dice | Consecuencia |
|---|---|---|
| `GCS_KEMTLS.cpp:248` | `mavlink_get_crypt_config(uint8_t chan, bool is_tx, uint8_t seq, ...)` | **`seq` es `uint8_t` en la frontera de la API.** Ésta es la causa raíz |
| `GCS_KEMTLS.cpp:269-270` | ChaCha20: `memcpy(nonce_out, iv, 12)` ; `*counter0 = (uint32_t)seq` | nonce **constante** toda la sesión; lo único que varía es el contador de bloques |
| `GCS_KEMTLS.cpp:280-283` | AES-CTR: `nonce_out[12..15] = seq >> 24/16/8/0` | sobre un `uint8_t`, los tres primeros desplazamientos dan **0**. Solo varía `nonce_out[15]` → periodo 256 |
| `GCS.h:291` + `GCS_KEMTLS.cpp:258` | `uint8_t aead_alg = 1;` y `// 0=no enc, 1=ChaCha20, 2=AES-CTR` | **el camino por defecto es el peor de los dos** |
| `GCS_KEMTLS.cpp:240` | `fill_nonce_seq(..., uint32_t seq)` | acepta 32 bits, pero nadie le pasa más de 8. Código muerto respecto al defecto |
| `GCS_KEMTLS.cpp:343-344` | `hkdf_expand_label(prk, "iv:tx" / "iv:rx", ...)` | **esto sí está bien.** Ver §3 |

De paso, dos cosas que **no** son defectos y conviene no confundir con éste, porque un revisor
puede señalarlas:

- `GCS.h:292-293` fija `negotiated_mtu = 220` y `negotiated_window = 8`. Es la traza directa a
  archivo de la fila «MTU / ventana» del artículo.
- `GCS_KEMTLS.cpp:346` reusa el **mismo** `iv_tx` para ChaCha20 y para AES-CTR. Parece sospechoso,
  pero no lo es: las claves se derivan con etiquetas distintas (`key:tx` frente a
  `chacha:key:tx`, líneas 341 y 347), así que los keystreams son independientes. La terna que
  importa incluye la clave.

Reproducible con:

```bash
py -3 experiments/nonce_collision/test_colision_nonce.py
```

| Camino | Primera colisión (msg de 200 B) | Plazo real a 50–100 Hz |
|---|---|---|
| **ChaCha20** (por defecto) | mensajes **0 y 1** | **el segundo mensaje** |
| AES-CTR | mensajes 0 y 256 | 2,6 – 5,1 s |

---

## 3. Por qué esto es un defecto — la criptografía

Un **cifrador de flujo** (ChaCha20, AES-CTR) no cifra el mensaje directamente. Genera un
*keystream* — una secuencia pseudoaleatoria de bytes — a partir de la terna
**(clave, nonce, contador de bloque)**, y hace XOR del claro con ese keystream:

```
C1 = P1 XOR KS        C2 = P2 XOR KS        <- el mismo KS en los dos
```

Si el keystream se repite, un atacante que capture los dos cifrados calcula:

```
C1 XOR C2 = (P1 XOR KS) XOR (P2 XOR KS) = P1 XOR P2
```

**El keystream se cancela y la clave desaparece de la ecuación.** Queda el XOR de dos textos
claros, que en telemetría MAVLink es trivial de separar: los mensajes tienen estructura fija,
campos conocidos y muchos ceros. No hace falta romper ChaCha20 ni AES — se rompen ellos solos
si repites la terna. Por eso la unicidad del nonce no es una buena práctica: **es la condición
de la que depende toda la confidencialidad.**

Tres términos que se confunden y aquí importan:

- **Nonce** — *number used once*. No tiene que ser secreto ni aleatorio. Solo **irrepetible**
  bajo la misma clave. Puede viajar en claro por el cable.
- **IV** — el valor base de sesión. Aquí `iv_tx` / `iv_rx`, 12 bytes derivados del handshake.
- **Contador de bloque** — dentro de un mensaje, qué bloque de 64 B (ChaCha20) o 16 B (AES) se
  está generando. Es lo que `counter0` inicializa.

El fallo de ChaCha20 aquí es que el código usa `seq` como **contador de bloque**, no como parte
del nonce. Un mensaje de 200 B consume 4 bloques. El mensaje *n* usa los bloques *n…n+3*, el
*n+1* usa *n+1…n+4*: **se solapan en tres bloques ya en el segundo mensaje.** No hay que esperar
a que `seq` dé la vuelta.

Y lo que **sí está bien**, para ser justos: `iv:tx` / `iv:rx` se derivan con etiquetas HKDF
distintas (`GCS_KEMTLS.cpp:343-344`). Eso es **separación de dominio** — garantizar que dos usos
distintos de la misma clave maestra produzcan material independiente. Aquí impide que el tráfico
FC→GCS y el GCS→FC compartan keystream. Está resuelto y no hay que tocarlo.

---

## 4. La restricción que hace esto difícil

Dos exigencias que tiran en direcciones opuestas.

**(a) El receptor tiene que recuperar el contador bajo pérdida de paquetes.**
Éste es, casi seguro, el motivo por el que se eligió `seq`: viaja en la cabecera, así que el
receptor no tiene que llevar estado ni resincronizar. Cualquier corrección que dependa de un
contador implícito **introduce un modo de fallo nuevo**: si el receptor pierde la cuenta, deja de
descifrar. En un enlace C2 de un dron eso es peor que el defecto que arregla. Es exactamente lo
que C11 del cronograma va a medir.

**(b) El nonce no debería derivarse de una cantidad que el atacante elige.**
Ya lo dice el manuscrito (`cas-sc-template.tex:998`, verbatim):

> *«the value is carried in the frame header, so it is visible and selectable by an on-path
> adversary, and a nonce should not be derived from a received quantity»*

Ésta es la objeción **más fuerte de las dos** y es independiente del ancho del campo. Un `seq` de
64 bits en claro seguiría siendo elegible por un atacante en la ruta.

**Matiz que la rescata parcialmente:** el manuscrito declara que en RX la firma MAVLink 2 se
verifica sobre la imagen de cable, que ya contiene el payload cifrado
(`cas-sc-template.tex:1320-1324`). Si el descifrado ocurre **después** de verificar la firma, el
campo del que se deriva el nonce está **autenticado** y deja de ser elegible por el atacante.

> `NO VERIFICADO` — que el orden en RX sea *verificar firma → descifrar* está declarado en el
> texto pero no lo he confirmado contra el código: `mavlink_get_crypt_config` **no tiene ningún
> llamante en este repositorio** (`grep -rn mavlink_get_crypt_config` → solo su definición). Del lado del
> FC, el llamante es casi seguro la librería C de MAVLink modificada, que se genera al compilar y
> no está en el snapshot; el comentario de `GCS_KEMTLS.cpp:279` (*«to match your proxy/tap»*)
> apunta a la contraparte del lado GCS. **Esto hay que confirmarlo antes de cerrar la opción
> 1**, y es una razón más para pedirle a Nicolás ese componente.

---

## 5. Las tres opciones

### Opción 1 — reusar el *timestamp* de la firma MAVLink 2

La firma MAVLink 2 son 13 bytes: `link_id` (1 B) + `timestamp` (6 B, unidades de 10 µs desde
2015) + firma truncada (6 B). El timestamp es de **48 bits y monótono por construcción**.

> `NO VERIFICADO` — este layout es el de la especificación MAVLink 2; no lo he verificado contra
> un archivo de este repositorio, porque las cabeceras `mavlink_types.h` se generan en tiempo de
> compilación y no están vendorizadas. B5 debe confirmarlo contra las cabeceras generadas.

| | |
|---|---|
| **Coste de cable** | **0 B.** Ya viaja, si la firma está activa |
| **Rango** | 2⁴⁸ × 10 µs ≈ **89 años** desde 2015 |
| **Unicidad** | a 100 Hz los mensajes van a 10 ms = 1000 ticks. Colisión solo si dos salen en menos de 10 µs |
| **Recuperación tras pérdida** | **trivial** — viaja explícito, sin estado en el receptor |
| **Atacante** | queda autenticado por la firma, *si* el orden en RX es verificar→descifrar |
| **Riesgo** | **depende de que la firma esté siempre activa.** El repo la activa al terminar el handshake (`GCS_KEMTLS.cpp:943`, `enable_signing_with_key(k_sign, 0, false)`) pero bajo `#if AP_MAVLINK_SIGNING_ENABLED` (`:942`). Si esa macro está apagada, **no hay nonce** |

### Opción 2 — época + ventana, estilo DTLS

Añadir 2 B de «época» que se incrementa cada vez que `seq` da la vuelta. Total efectivo
16 + 8 = **24 bits** → 16,7 M tramas → a 100 Hz, **unas 46 horas** de sesión.

| | |
|---|---|
| **Coste de cable** | **+2 B/trama** = 1,6 kbps a 100 Hz |
| **Recuperación tras pérdida** | buena: la época va explícita, la ventana absorbe el reordenamiento |
| **Riesgo** | hay que definir **política de rekey** al agotar la época, y **fail-closed**: al llegar al final se corta la sesión, no se envuelve. Envolver silenciosamente reintroduce el defecto |
| **Complejidad** | la más alta de las tres. La ventana de repetición es lógica nueva que hay que probar |

### Opción 3 — contador explícito de 64 bits

| | |
|---|---|
| **Coste de cable** | **+8 B/trama** = 6,4 kbps a 100 Hz. El más caro |
| **Rango** | 2⁶⁴ a 100 Hz ≈ **5,8 mil millones de años**. No se agota |
| **Recuperación tras pérdida** | trivial, explícito |
| **Complejidad** | **la mínima.** Es la que menos se puede implementar mal |

---

## 6. Recomendación

**Opción 1, con la opción 3 como plan B declarado.**

El razonamiento, en orden:

1. **Es la única con coste cero.** El artículo mide throughput en un enlace de 0,18 Mbps; +8 B por
   trama a 100 Hz es una fracción que hay que justificar, y 0 B no hay que justificarla.
2. **Es la única que además responde a la objeción (b).** El timestamp de firma está autenticado;
   un contador que añadamos nosotros en claro, no — salvo que quede cubierto por la firma, lo que
   nos devuelve a depender de la firma igual que la opción 1.
3. **No añade estado en el receptor**, así que no introduce el modo de fallo de (a). Es el
   argumento decisivo para un enlace C2.
4. Rechazo la opción 2 no por mala sino por **desproporcionada**: paga 2 B *y* añade la lógica
   más compleja de las tres. Solo tiene sentido si la firma no puede darse por activa.

**Condición que hay que verificar antes de cerrarla** — y es la razón por la que esto es una
decisión y no un cambio automático: la opción 1 **hace que la confidencialidad dependa de que la
firma esté activa**. Eso es un acoplamiento nuevo entre dos propiedades que hoy son
independientes. Hay que decidir si se acepta, y **declararlo en el manuscrito**: *«la
construcción corregida requiere firma MAVLink 2 activa; con la firma desactivada el canal no
ofrece confidencialidad y la sesión debe rechazarse»*. Eso es fail-closed y es defendible, pero
tiene que estar escrito.

Si se prefiere no acoplarlas, **la opción 3 es la respuesta correcta** y el coste es 6,4 kbps.

---

## 7. Lo que heredan B5 y B6

**B5 — implementación y test:**
- Confirmar contra las cabeceras generadas el layout de 13 B de la firma (`NO VERIFICADO` en §5).
- Confirmar el orden en RX: verificar firma → descifrar (`NO VERIFICADO` en §4).
- Test de **>256 mensajes sin repetir la terna (clave, nonce, contador)**. El umbral es 256 porque
  es donde falla hoy AES-CTR; para ChaCha20 basta con 2, pero el test debe cubrir el peor caso de
  los dos.
- Test de **fail-closed**: con la firma desactivada, la sesión no debe cifrar.

**B6 — coste:** bytes/trama y throughput medidos, no estimados. Con la opción 1 se espera 0, y hay
que demostrar el 0 igual que se demostraría un número distinto.

---

## 8. Decisión

- [x] **Opción 1** — timestamp de firma, 0 B, acopla confidencialidad a la firma
- [ ] **Opción 2** — época + ventana, +2 B
- [ ] **Opción 3** — contador de 64 bits, +8 B, sin acoplamiento

Decidido por: **Javier**  Fecha: **2026-09-15** — **en suspenso el 2026-09-16**

> El artículo ya especifica la construcción corregida (l. 1470-1473): contador monótono de **≥64 bits,
> explícito**, separado por dirección y época de clave, con **ventana de replay** y fail-closed. Eso es
> la **opción 3** (más la ventana). La opción 1 se aparta de lo escrito (48 bits, no es un contador
> propio), así que pasa a sugerencia para Nicolás. Plan fiel al artículo: opción 3.

Junto con la arquitectura de par de proxies, que hace estructural la condición de §6 (no existe
camino sin firma). Construcción concreta —nonce en el campo nonce de ChaCha20, contador de bloque a
0, claves por sentido— en [`../proxy_c9/DISENO.md`](../proxy_c9/DISENO.md) §4.
