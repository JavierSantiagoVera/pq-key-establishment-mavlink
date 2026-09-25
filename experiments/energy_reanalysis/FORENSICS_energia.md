# Forense de los datos energéticos — causa C4

**Fecha:** 2026-07-28
**Método:** parseo directo de las capturas `.pcapng` archivadas en el repositorio
(`scapy` + `pymavlink`, dialecto `ardupilotmega` v2), contando mensajes
`SYS_STATUS` / `BATTERY_STATUS` legibles y sus valores de `battery_remaining`.
Script reproducible: `extract_battery.py`.

## Pregunta que se quería resolver

El panel de TAES objetó que las tablas de energía reportan **consumo adicional negativo**
por cifrar ("simply impossible") y exigió intervalos de confianza. La discusión interna se
planteó como: ¿se puede **rescatar** el resultado calculando pendientes de descarga con
intervalos de confianza sobre las series temporales crudas, o hay que **retirarlo**?

La respuesta no es de opinión: depende de qué contienen realmente las capturas.

## Qué dice el paper

Tabla de reposo (10 min por condición), citando tres capturas:

| Modo | Captura citada | Cifrado | Duración | SoC inicio → fin | Pérdida |
|---|---|---|---|---|---|
| Baseline | `run_clear` | ninguno | 600.641 s | 34 → 24 | 0.999 pp/min |
| Cifrado | `run_aesctr` | AES-CTR | 600.644 s | 69 → 61 | 0.799 pp/min |
| Cifrado | `run_chacha` | ChaCha20 | 600.641 s | 81 → 72 | 0.899 pp/min |

## Qué contienen realmente las capturas archivadas

| Captura | Paquetes | Duración real | `BATTERY_STATUS` | `SYS_STATUS` | `BAD_DATA` | Valores de SoC legibles |
|---|---|---|---|---|---|---|
| `gcs_clear20251114_191527.pcapng` | **0** | 0 s | 0 | 0 | 0 | **ninguno** |
| `gcs_aesctr20251114_183415.pcapng` | 1410 | **1244.3 s** | 1 | 1 | 1392 (98.7 %) | **[69]** |
| `gcs_chacha20251114_182011.pcapng` | 729 | **615.0 s** | 1 | 1 | 710 (97.4 %) | **[81]** |

## Conclusiones (verificables)

1. **La captura del baseline está vacía.** `gcs_clear20251114_191527.pcapng` contiene
   **cero paquetes**. La fila "Baseline / 34 → 24 / 0.999 pp/min" **no puede reproducirse**
   a partir del archivo citado.

2. **En las condiciones cifradas solo existe un valor de SoC legible por captura.**
   Aparece el valor inicial (69 para AES-CTR, 81 para ChaCha20), pero **no el final**
   (61 y 72 respectivamente). Es decir, el "delta" reportado no es recuperable del dato
   archivado.

3. **La causa es estructural, no un descuido de archivo.** El 97–99 % de los mensajes son
   `BAD_DATA`: la captura es del lado GCS y los payloads viajan **cifrados**, de modo que la
   telemetría de batería es ilegible por diseño. Esto **confirma que el cifrado funciona**,
   pero implica que **la instrumentación elegida es incapaz de medir la condición cifrada**.

4. **Las duraciones no coinciden** con las reportadas (1244.3 s y 615.0 s frente a 600.6 s).

5. **Sí existen series temporales, pero solo en claro.** Las capturas del lado del
   controlador de vuelo en claro (`clear_fc_20251114_153259.pcapng`, 1325 `SYS_STATUS`;
   `clear_fc_20251113_204008.pcapng`, 414) contienen decenas de lecturas con varios niveles
   de SoC. No existe su equivalente cifrado: las capturas cifradas del lado FC
   (`fc_20251114_164939`, `fc_20251114_171039`) también son ~97 % `BAD_DATA`.

## Consecuencia para el manuscrito

**El resultado energético no es rescatable con estadística.** No se trata de que falten
intervalos de confianza sobre una muestra pequeña: es que **no existe la muestra** para la
condición cifrada, y la referencia baseline está vacía. Aplicar regresión aquí produciría
un número con apariencia de rigor sobre datos inexistentes, que es peor que el error actual.

**Acción obligatoria:** retirar del manuscrito la tabla comparativa de energía en reposo y
toda afirmación derivada de ella. Sustituir por:

1. Una declaración explícita de **límite de resolución**: el indicador de SoC del Bebop 1
   reporta en pasos enteros de 1 %, sin registro de corriente ni voltaje calibrado, por lo
   que no puede resolver el sobrecoste energético del cifrado en escalas de 10 minutos.
2. Una **cota superior analítica** derivada de conteo de ciclos de CPU por operación
   (medible por microbenchmark, sin hardware de vuelo), en lugar de una medición de sistema.
3. Reconocimiento de que la medición energética calibrada queda como trabajo futuro.

**Regla dura:** ninguna versión futura del manuscrito puede presentar el cifrado como
neutro o beneficioso en energía apoyándose en estos datos.

## Nota sobre integridad

Este hallazgo debe comunicarse a los coautores antes del reenvío. Si un revisor hubiera
solicitado los datos, la tabla se habría caído. Retirarla no es solo metodológicamente
correcto: es necesario para la integridad del artículo.
