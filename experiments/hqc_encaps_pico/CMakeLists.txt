cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(hqc_encaps_pico C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

# Ruta al HQC-128 "clean" (referencia PQClean) tal como vive en el extracto del fork,
# la misma fuente que usa experiments/energy_cpu_bound/ y crypto_vectors/ -- no se
# copia ni se modifica, se referencia directo para no duplicar la fuente de verdad.
set(PQCLEAN_VENDOR
    "${CMAKE_CURRENT_SOURCE_DIR}/../../firmware-fork/libraries/AP_KEM/vendor/pqclean")
set(HQC128_CLEAN "${PQCLEAN_VENDOR}/crypto_kem/hqc-128/clean")

add_executable(hqc_encaps_pico
    main.c
    randombytes_pico.c
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
)

target_include_directories(hqc_encaps_pico PRIVATE
    "${PQCLEAN_VENDOR}/common"
    "${HQC128_CLEAN}"
)

target_link_libraries(hqc_encaps_pico
    pico_stdlib
    pico_rand
)

pico_enable_stdio_usb(hqc_encaps_pico 1)
pico_enable_stdio_uart(hqc_encaps_pico 0)

pico_add_extra_outputs(hqc_encaps_pico)
