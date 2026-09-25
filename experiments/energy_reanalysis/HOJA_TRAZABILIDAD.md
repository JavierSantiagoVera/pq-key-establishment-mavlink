# Hoja de trazabilidad de cifras — artículo de Carlos (TAES-2026-2045)

**Acción #1 ordenada por el consejo.** Regla fijada de antemano:
**el número que no se traza a un archivo y un comando se borra, no se suaviza.**

**Método:** parseo independiente de las capturas archivadas con `scapy` + `pymavlink`
(dialecto `ardupilotmega` v2). Scripts: `extract_battery.py`, `verify_battery_runs.py`.

> **Salvedad de justicia.** El manuscrito menciona "a dedicated offline analyzer" para procesar
> los logs. **Ese analizador no está en el repositorio** (los únicos scripts de batería
> presentes — `Tools/scripts/battery_fit.py`, `Tools/scripts/mavlink_parse.py` — son de
> ArduPilot upstream, no del proyecto). Es posible que Carlos lo tenga en local y que su lógica
> de extracción difiera de la mía. **Primera petición a Carlos: entregar ese analizador y los
> archivos exactos de entrada.** Mientras no exista, las cifras no son regenerables por nadie
> —incluidos los autores— a partir del repositorio publicado.

---

## Bloque 1 — Tabla de estrés de batería (R1–R5)

| Run | Captura citada | Dur. paper | Dur. captura | SoC ini (paper → dato) | SoC fin (paper → dato) | Lecturas | Veredicto |
|---|---|---|---|---|---|---|---|
| R1 | `gcs_20251113_180441.pcapng` | 222.856 s | 275.95 s | 53 → **53** ✓ | 48 → **49** ✗ | 8 | fin no coincide |
| R2 | `gcs_20251113_182734.pcapng` | 266.554 s | 281.00 s | 75 → **75** ✓ | 71 → **73** ✗ | 6 | fin no coincide |
| R3 | `gcs_20251113_184155.pcapng` | 298.175 s | 333.93 s | 67 → **68** ✗ | 63 → **68** ✗ | 6 | **ninguno de los dos valores aparece** (solo hay 68) |
| R4 | `gcs_20251113_190020.pcapng` | 363.837 s | 377.13 s | 82 → **82** ✓ | 76 → **76** ✓ | 12 | **trazable** |
| R5 | `gcs_20251113_191218.pcapng` | 503.046 s | 525.00 s | 73 → **73** ✓ | 67 → **68** ✗ | 14 | fin no coincide |

**Lectura:** 1 de 5 filas reproduce por completo. Los valores **iniciales** coinciden en 4 de 5
(señal de que las capturas citadas son las correctas), pero los **finales** no reproducen en 4
de 5. En R3 no aparece ninguno de los dos valores: las seis lecturas de la captura son 68 %.

En R4, además, la duración reportada (363.837 s) coincide casi exactamente con el intervalo
entre la primera y la última lectura de batería que extraigo (363.25 s), lo que sugiere que ese
**es** el criterio de duración usado. Pero ese criterio no reproduce las duraciones de R1
(142 s medidos frente a 222.856 s reportados) ni de R5 (432 s frente a 503.046 s).

### Series completas extraídas

- **R1** (8 lecturas): 0 s→53 %, 54.9 s→50 %, 127.1 s→49 %, 142.1 s→49 %
- **R2** (6): 0 s→75 %, 41.2 s→74 %, 148.7 s→73 %
- **R3** (6): 30.0 s→68 %, 40.0 s→68 %, 65.4 s→68 % *(sin variación)*
- **R4** (12): 0 s→82 %, 52.9 s→81 %, 207.7 s→79 %, 327.8 s→77 %, 363.2 s→76 %
- **R5** (14): 0 s→73 %, 50.8 s→**74 %**, 83.6 s→73 %, 384.3 s→69 %, 431.8 s→68 %

Nota sobre R5: el SoC **sube** de 73 % a 74 % a los 50 s. Es comportamiento normal de un
estimador de carga, y es exactamente por lo que un gauge de 1 % no sirve para medir un efecto
de segundo orden como el sobrecoste del cifrado.

---

## Bloque 2 — Tabla de reposo cifrado vs claro

Ya documentado en `FORENSICS_energia.md`. Resumen:

| Fila del paper | Captura citada | Estado |
|---|---|---|
| Baseline (34 → 24) | `gcs_clear20251114_191527.pcapng` | **archivo vacío (0 paquetes)** — irreproducible |
| AES-CTR (69 → 61) | `gcs_aesctr20251114_183415.pcapng` | solo existe el 69; el 61 no está en el dato |
| ChaCha20 (81 → 72) | `gcs_chacha20251114_182011.pcapng` | solo existe el 81; el 72 no está en el dato |

Causa estructural: 97–99 % de los mensajes son `BAD_DATA` porque el payload viaja cifrado.
**La telemetría de batería es ilegible por diseño desde el lado GCS.**

---

## Bloque 2-bis — El pipeline original apareció, y explica todo

En `captures/previous_pcaps/` están las salidas del analizador que menciona el manuscrito.
Eran exportaciones de **tshark** (`frame.time_epoch`, `mavlink_proto.SYS_STATUS_voltage_battery`,
`..._current_battery`, `..._battery_remaining`). Tres hechos que cierran el caso:

1. **`gcs_batt.json` está vacío: `[]`.** La propia extracción de batería del lado GCS de los
   autores no devolvió nada. Coincide exactamente con mi hallazgo independiente.
2. **Las tablas del paper dicen "GCS-side logs" y "GCS-side captures", pero el dato utilizable
   solo existe del lado FC.** Los encabezados atribuyen la fuente equivocada.
3. En `fc_batt.csv` conviven lecturas válidas con valores centinela evidentes
   (`voltage=2779, current=-26632, battery_remaining=-26`). El filtrado de esos valores es
   correcto, pero **no está documentado ni versionado**, y cambia el resultado.

### Por qué el cálculo energético es imposible con estos datos

| Observable | Disponibilidad real | Consecuencia |
|---|---|---|
| **Corriente** (`current_battery`) | **0 en el 100 % de las muestras** (1325/1325 y 414/414) | El Bebop 1 no reporta corriente por MAVLink → **el conteo de culombios es imposible** |
| **SoC** (`battery_remaining`) | cuantizado a pasos de 1 % | no resuelve un efecto de segundo orden |
| **Voltaje** (`voltage_battery`) | **resolución de milivoltio** (11799, 11648, 11647…) con **n = 1325** | el único observable con resolución útil |

**Conclusión reforzada:** no hay forma de estimar energía desde esta telemetría. Se confirma el
retiro de la tabla.

**Recomendación constructiva para trabajo futuro** (esto sí es publicable como método): el
observable correcto no es el SoC sino la **caída de voltaje a resolución de milivoltio, medida
del lado del controlador de vuelo y con captura antes del cifrado** (o registro a bordo). Con
n≈1300 muestras por condición se puede ajustar una pendiente con intervalos de confianza reales.
Es exactamente lo que el panel pidió, y no requiere medidor externo — solo capturar del lado
correcto.

---

## Bloque 3 — Cifras de handshake (verificación iniciada, no concluida)

> 🔴 **CORREGIDO EL 2026-09-08. Lo que sigue en este bloque es falso.** El diálogo HQC **sí está
> en capturas de hardware**: las `fc_*.pcapng`, sobre la subred del Bebop
> (`192.168.42.1 → 192.168.42.2:14550`), que este bloque nunca miró. El parser solo analizaba las
> `gcs_*.pcapng`, que son loopback y están tomadas después de que el proxy consumiera el diálogo.
> El número de handshakes por corrida **sí es verificable**, y coincide con el 18–23 declarado.
> Ver `TRAZABILIDAD_handshake.md`, sección «CORRECCIÓN 2026-09-08». **No hay nada que cerrar con
> Carlos aquí.**

**Hallazgo parcial:** las capturas R1–R5 citadas para la tabla de estrés **no contienen ningún
mensaje del diálogo HQC**. Los únicos msgid presentes son estándar: 0 (HEARTBEAT), 1 (SYS_STATUS),
22 (PARAM_VALUE), 77 (COMMAND_ACK), 111 (TIMESYNC), 147 (BATTERY_STATUS), 253 (STATUSTEXT).

Es decir: el número de handshakes por corrida (18–23) **no es verificable desde esas capturas**.
Existen capturas dedicadas (`previous_pcaps/hqc_handshake_*.pcapng`), pendientes de analizar, y
es posible que el diálogo use IDs fuera del rango 61000–61008 que asumí, o que viaje por un
socket no capturado. **Pendiente de cerrar con Carlos.**

## Bloque 3-b — Cifras de handshake por trazar

No verificadas todavía. Requieren parsear el diálogo HQC (IDs 61000–61008) en las capturas de
handshake. Cifras a trazar:

| Cifra reportada | Valor | Fuente declarada |
|---|---|---|
| Intentos / éxitos | 100 / 96 (96 %) | logs del proxy |
| Handshake total (media / p50 / p95) | 0.624 / 0.611 / 0.632 s | timestamps del proxy |
| Fase `CT_stream` (media) | 0.409 s | ídem |
| Throughput de ciphertext | 0.177 Mbps | ídem |
| MTU / ventana | 220 B / 8 | configuración |
| Tasa de fondo MAVLink | 1.30 frames/s; 1.01 HEARTBEAT/s | captura FC sin handshake |

**Estas son las cifras que sostienen la contribución principal del artículo.** Verificarlas es
prioritario: si trazan bien, el paper conserva su núcleo empírico incluso tras retirar la
energía. Si no trazan, el problema es mucho mayor.

---

## Conclusión operativa

| Bloque | Estado | Acción |
|---|---|---|
| Tabla de reposo (energía) | **irreproducible** | **Retirar del manuscrito** |
| Tabla de estrés R1–R5 | 1 de 5 reproduce | Retirar o re-derivar con el analizador de Carlos y criterio explícito |
| Cifras de handshake | **fuente localizada** (2026-09-08) | Extractor de sesiones sobre `fc_*.pcapng` — tarea 1 |

Nada de esto implica mala fe: el patrón es coherente con un analizador que leía otra fuente
(logs del proxy, no las capturas) y con archivos que se movieron o se sobrescribieron. Pero
publicado tal cual, un revisor que pida datos encuentra lo mismo que encontré yo.
