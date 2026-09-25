# Post-Quantum Key Establishment for MAVLink

Code, firmware fork, and experiment artifacts for a MAVLink-native post-quantum
key-establishment extension: an HQC key-encapsulation mechanism (KEM) combined with a
KEMTLS pre-distributed-key (KEMTLS-PDK) handshake between a Ground Control Station (GCS)
and a UAV flight controller (FC), implemented as a fork of
[ArduPilot](https://github.com/ArduPilot/ardupilot) targeting a Parrot Bebop 1.

This repository accompanies a manuscript submitted to *IEEE Transactions on Aerospace and
Electronic Systems*. It contains the software artifacts and experimental data; it does
**not** contain the manuscript itself.

## Repository structure

```
firmware-fork/     Extract of the ArduPilot fork implementing the HQC/KEMTLS-PDK
                    handshake and MAVLink dialect on the flight-controller side.
                    Partial by design (see firmware-fork/README below) — not a full
                    ArduPilot checkout, only the modified/added files plus the packet
                    captures used for the reported handshake results.

experiments/        Independent validation experiments, each in its own directory with
                    its own README: cryptographic primitive test vectors, the corrected
                    nonce/counter construction and its evaluation against a real ChaCha20
                    implementation, the channel-0 signing-enforcement finding and patch,
                    the entropy-source hardening patch, real-hardware HQC-128
                    encapsulation benchmarks on a Raspberry Pi Pico and an ESP32, a
                    QEMU vexpress-a9 environment approximating the Bebop's Cortex-A9,
                    and the traceability analysis behind the handshake timing figures
                    reported in the manuscript.
```

Each subdirectory under `experiments/` has its own `README.md` explaining what it tests,
how to reproduce it, and what it does and does not establish. Where a result is an
inference rather than a direct measurement, the corresponding README says so explicitly.

## `firmware-fork/` is intentionally incomplete

This is an *extract* of a larger ArduPilot fork, not the full fork. It contains the files
that implement the HQC/KEMTLS-PDK extension (`libraries/AP_KEM/`,
`libraries/GCS_MAVLink/GCS_KEMTLS.cpp`, the `Tools/kemtls/` helpers) and the hardware
packet captures used for the results reported in the manuscript. It does not include a
buildable ArduPilot tree (no `waf`, no full `libraries/`, no build system) and does not
include the Ground Control Station side of the protocol, which lives in a separate,
unpublished project. Several `experiments/` READMEs document this boundary precisely,
including which specific files are absent and why that limits what can be verified from
this repository alone.

## License

GPLv3 (see `LICENSE`), consistent with ArduPilot's own license, since `firmware-fork/`
is a derivative of ArduPilot. The vendored HQC-128 reference implementation under
`firmware-fork/libraries/AP_KEM/vendor/pqclean/` is public domain (see its own `LICENSE`
file in that directory) and is included unmodified.

## Citation

See `CITATION.cff`. If you use this code, please cite the associated manuscript once
published; in the meantime, cite this repository directly.
