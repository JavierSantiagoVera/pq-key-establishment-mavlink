# Ruta al HQC-128 "clean" (referencia PQClean) tal como vive en el extracto del fork --
# la misma fuente que usa energy_cpu_bound/ y hqc_encaps_pico/, referenciada directo,
# sin copiar ni modificar, para no duplicar la fuente de verdad.
set(PQCLEAN_VENDOR
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../firmware-fork/libraries/AP_KEM/vendor/pqclean")
set(HQC128_CLEAN "${PQCLEAN_VENDOR}/crypto_kem/hqc-128/clean")

idf_component_register(
    SRCS
        "main.c"
        "randombytes_esp32.c"
        "${PQCLEAN_VENDOR}/common/fips202.c"
        "${HQC128_CLEAN}/code.c"
        "${HQC128_CLEAN}/fft.c"
        "${HQC128_CLEAN}/gf2x.c"
        "${HQC128_CLEAN}/gf2x_sparse.c"
        "${HQC128_CLEAN}/gf.c"
        "${HQC128_CLEAN}/hqc.c"
        "${HQC128_CLEAN}/kem.c"
        "${HQC128_CLEAN}/parsing.c"
        "${HQC128_CLEAN}/reed_muller.c"
        "${HQC128_CLEAN}/reed_solomon.c"
        "${HQC128_CLEAN}/shake_ds.c"
        "${HQC128_CLEAN}/shake_prng.c"
        "${HQC128_CLEAN}/vector.c"
        "${HQC128_CLEAN}/vector_sparse.c"
    INCLUDE_DIRS
        "${PQCLEAN_VENDOR}/common"
        "${HQC128_CLEAN}"
)
