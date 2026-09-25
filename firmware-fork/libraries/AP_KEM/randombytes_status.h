#pragma once
/* Estado de la fuente de entropia (hallazgo A8). Ver randombytes_linux.c */
#ifdef __cplusplus
extern "C" {
#endif

/* Devuelve !=0 si alguna llamada a randombytes() no pudo obtener entropia
 * suficiente en este arranque. Sticky: no se limpia solo. */
int  ap_kem_entropy_failed(void);

/* Solo para pruebas de inyeccion de fallo. */
void ap_kem_entropy_reset_for_test(void);

#ifdef __cplusplus
}
#endif
