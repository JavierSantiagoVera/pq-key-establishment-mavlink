# Trazabilidad — tabla de estrés de batería (R1..R5)

Cada fila del manuscrito contrastada contra la captura que cita.

| Run | Captura | Dur. paper | Dur. captura | SoC ini paper | SoC ini dato | SoC fin paper | SoC fin dato | Lecturas | Veredicto |
|---|---|---|---|---|---|---|---|---|---|
| R1 | `gcs_20251113_180441.pcapng` | 222.856 | 275.95 | 53 | 53 | 48 | 49 | 8 | **fin no coincide** (dato: 49; valores vistos: [49, 50, 53]) |
| R2 | `gcs_20251113_182734.pcapng` | 266.554 | 280.999 | 75 | 75 | 71 | 73 | 6 | **fin no coincide** (dato: 73; valores vistos: [73, 74, 75]) |
| R3 | `gcs_20251113_184155.pcapng` | 298.175 | 333.929 | 67 | 68 | 63 | 68 | 6 | **no coincide** (valores vistos: [68]) |
| R4 | `gcs_20251113_190020.pcapng` | 363.837 | 377.127 | 82 | 82 | 76 | 76 | 12 | trazable |
| R5 | `gcs_20251113_191218.pcapng` | 503.046 | 525.001 | 73 | 73 | 67 | 68 | 14 | **fin no coincide** (dato: 68; valores vistos: [68, 69, 73, 74]) |

## Detalle de las series (t_rel en s, SoC en %)

- **R1** (`gcs_20251113_180441.pcapng`, dur 275.95s, 8 lecturas): 0.0s→53%, 0.028s→53%, 54.885s→50%, 54.894s→50%, 127.078s→49%, 127.087s→49%, 142.13s→49%, 142.139s→49%
- **R2** (`gcs_20251113_182734.pcapng`, dur 280.999s, 6 lecturas): 0.0s→75%, 0.009s→75%, 41.167s→74%, 41.176s→74%, 148.7s→73%, 148.73s→73%
- **R3** (`gcs_20251113_184155.pcapng`, dur 333.929s, 6 lecturas): 30.033s→68%, 30.04s→68%, 39.963s→68%, 39.97s→68%, 65.444s→68%, 65.462s→68%
- **R4** (`gcs_20251113_190020.pcapng`, dur 377.127s, 12 lecturas): 0.0s→82%, 0.009s→82%, 52.942s→81%, 52.95s→81%, 207.685s→79%, 207.694s→79%, 327.776s→77%, 327.782s→77%, 332.797s→77%, 332.809s→77%, 363.218s→76%, 363.25s→76%
- **R5** (`gcs_20251113_191218.pcapng`, dur 525.001s, 14 lecturas): 0.0s→73%, 0.011s→73%, 50.804s→74%, 50.813s→74%, 83.576s→73%, 83.587s→73%, 384.32s→69%, 384.322s→69%, 389.343s→69%, 389.36s→69%, 398.273s→69%, 398.292s→69%, 431.761s→68%, 431.77s→68%
