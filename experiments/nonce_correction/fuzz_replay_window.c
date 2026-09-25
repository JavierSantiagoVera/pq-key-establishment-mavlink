/*
 * fuzz_replay_window.c -- experimento #4 de 08_cierre/README.md #B-bis, adaptado: la
 * idea original era usar `tc netem` para simular perdida/reordenamiento de red sobre
 * replay_window_t. Se confirmo el 2026-09-17 que el kernel de este portatil (CachyOS
 * 7.1.6-1-cachyos) NO TIENE netem -- ni como modulo ni compilado adentro
 * (`tc qdisc add ... netem` da "Specified qdisc kind is unknown"). Decision de Javier:
 * no cambiar de kernel por esto, fuzzear en proceso en su lugar.
 *
 * POR QUE ESTO SIRVE IGUAL
 *   replay_window_t es un modulo C puro, sin E/S de red -- lo unico que le importa de
 *   la red es EN QUE ORDEN y CUANTAS VECES le llegan los contadores. Eso se puede
 *   simular en el mismo proceso, sin tocar el kernel: se genera la secuencia que
 *   manda el emisor (monotona, sender_ctx_t) y se la reordena/duplica/descarta antes
 *   de entregarsela al receptor -- exactamente el efecto de la red, sin la red.
 *
 * METODO: diferencial contra un oraculo independiente
 *   No se compara contra "lo que ya sabemos que hace el codigo" (séria circular). Se
 *   escribe una segunda implementacion de la misma especificacion (nonce_ctr.h, el
 *   bitmap deslizante de 64), con una estructura de datos DISTINTA (un arreglo de
 *   "visto alguna vez" en vez de un bitmap), y se compara veredicto por veredicto
 *   contra replay_window_check_and_update() real, sobre miles de entregas fuzzeadas.
 *
 * CONTROL POSITIVO (misma disciplina que test_nonce_correction.c y crypto_vectors/)
 *   Antes de confiar en "0 discrepancias", se corre el mismo oraculo contra una
 *   variante DELIBERADAMENTE ROTA (off-by-one en el limite de la ventana) para
 *   confirmar que el fuzzer SI detecta una discrepancia cuando la hay.
 *
 * Compilar y correr: ver README.md ("Fuzzing sin tc netem").
 */
#define _POSIX_C_SOURCE 200809L   /* rand_r() es POSIX, no C11 puro */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>

#include "nonce_ctr.h"

/* ------------------------------------------------------- variante deliberadamente rota
 * Copia de replay_window_check_and_update con un off-by-one: acepta un contador con
 * diff == 64 (deberia rechazarlo, la ventana es de 64: diff 0..63). Sirve solo para el
 * control positivo de abajo. */
static bool replay_window_check_and_update_ROTO(replay_window_t *w, uint64_t counter) {
    if (!w->initialized) {
        w->initialized = true;
        w->highest_seen = counter;
        w->seen_bitmap = 1ULL;
        return true;
    }
    if (counter > w->highest_seen) {
        uint64_t shift = counter - w->highest_seen;
        w->seen_bitmap = (shift >= 64) ? 0ULL : (w->seen_bitmap << shift);
        w->seen_bitmap |= 1ULL;
        w->highest_seen = counter;
        return true;
    }
    uint64_t diff = w->highest_seen - counter;
    if (diff > 64) { return false; }              /* BUG: deberia ser >= 64 */
    if (diff == 64) { return true; }               /* BUG: acepta uno de mas */
    uint64_t bit = 1ULL << diff;
    if (w->seen_bitmap & bit) { return false; }
    w->seen_bitmap |= bit;
    return true;
}

/* --------------------------------------------------------------------------- oraculo
 * Estructura de datos DISTINTA (arreglo de "visto", no bitmap) para la misma
 * especificacion. rango debe cubrir todos los valores de counter que se van a probar. */
typedef struct {
    bool *visto;
    size_t rango;
    uint64_t highest_seen;
    bool initialized;
} oraculo_t;

static void oraculo_init(oraculo_t *o, size_t rango) {
    o->visto = calloc(rango, sizeof(bool));
    o->rango = rango;
    o->highest_seen = 0;
    o->initialized = false;
}

static void oraculo_free(oraculo_t *o) { free(o->visto); }

static bool oraculo_check(oraculo_t *o, uint64_t counter) {
    if (!o->initialized) {
        o->initialized = true;
        o->highest_seen = counter;
        o->visto[counter] = true;
        return true;
    }
    if (o->visto[counter] && counter <= o->highest_seen) {
        /* ya visto Y no es un maximo nuevo -> replay, salvo que ya haya caido fuera
         * de la ventana, en cuyo caso tambien se rechaza (mismo resultado). */
        if (o->highest_seen - counter < 64) return false;   /* replay dentro de ventana */
        return false;                                        /* demasiado viejo */
    }
    if (counter > o->highest_seen) {
        o->highest_seen = counter;
        o->visto[counter] = true;
        return true;
    }
    /* counter <= highest_seen, no visto antes */
    if (o->highest_seen - counter >= 64) return false;   /* demasiado viejo */
    o->visto[counter] = true;
    return true;
}

/* ------------------------------------------------------------------- fuzz: red simulada
 * Genera la secuencia monotona del emisor (0..n-1) y la entrega en un orden fuzzeado:
 * bufferiza rafagas de hasta BUFFER, las baraja, y de vez en cuando duplica una entrega
 * ya hecha. Devuelve cuantos items se entregaron (<= n, por las perdidas). */
#define BUFFER 12

static size_t simular_red(uint64_t *entregados, size_t max_entregas, size_t n,
                           unsigned *seed, double p_perdida, double p_duplicado)
{
    size_t n_ent = 0;
    uint64_t buf[BUFFER];
    uint64_t ya_entregados[4096];
    size_t n_ya = 0;

    size_t i = 0;
    while (i < n) {
        int nb = 1 + (rand_r(seed) % BUFFER);
        int llenado = 0;
        for (int k = 0; k < nb && i < n; k++, i++) {
            if ((double)rand_r(seed) / RAND_MAX < p_perdida) continue;  /* se pierde */
            buf[llenado++] = i;
        }
        /* barajar el buffer (Fisher-Yates) -- simula reordenamiento de red */
        for (int k = llenado - 1; k > 0; k--) {
            int j = rand_r(seed) % (k + 1);
            uint64_t tmp = buf[k]; buf[k] = buf[j]; buf[j] = tmp;
        }
        for (int k = 0; k < llenado && n_ent < max_entregas; k++) {
            entregados[n_ent++] = buf[k];
            if (n_ya < 4096) ya_entregados[n_ya++] = buf[k];
            if ((double)rand_r(seed) / RAND_MAX < p_duplicado && n_ya > 0 &&
                n_ent < max_entregas) {
                entregados[n_ent++] = ya_entregados[rand_r(seed) % n_ya];
            }
        }
    }
    return n_ent;
}

static int fallos = 0;
static void chk(const char *nombre, int cond) {
    printf("  [%s] %s\n", cond ? "OK  " : "FALLA", nombre);
    if (!cond) fallos++;
}

/* Corre la comparacion diferencial. real_fn permite inyectar la variante rota para el
 * control positivo. Devuelve el numero de discrepancias encontradas. */
typedef bool (*replay_fn_t)(replay_window_t *, uint64_t);

static int correr_diferencial(replay_fn_t real_fn, const uint64_t *entregas, size_t n,
                               size_t rango_oraculo, long *aceptados_out)
{
    replay_window_t w;
    replay_window_init(&w, DIR_RX, 1);
    oraculo_t o;
    oraculo_init(&o, rango_oraculo);

    int discrepancias = 0;
    long aceptados = 0;
    for (size_t i = 0; i < n; i++) {
        bool r_real = real_fn(&w, entregas[i]);
        bool r_oraculo = oraculo_check(&o, entregas[i]);
        if (r_real != r_oraculo) {
            discrepancias++;
            if (discrepancias <= 5) {
                printf("      discrepancia #%d: contador=%lu real=%s oraculo=%s (highest_seen real=%lu)\n",
                       discrepancias, (unsigned long)entregas[i],
                       r_real ? "acepta" : "rechaza", r_oraculo ? "acepta" : "rechaza",
                       (unsigned long)w.highest_seen);
            }
        }
        if (r_real) aceptados++;
    }
    oraculo_free(&o);
    if (aceptados_out) *aceptados_out = aceptados;
    return discrepancias;
}

int main(int argc, char **argv) {
    int n_mensajes = (argc > 1) ? atoi(argv[1]) : 3000;
    unsigned seed_base = (argc > 2) ? (unsigned)atoi(argv[2]) : 20260917u;

    printf("== fuzzing de replay_window_t sin tc netem (kernel sin soporte, ver README.md) ==\n\n");

    printf("0. CONTROL POSITIVO -- el fuzzer debe detectar una variante rota\n");
    {
        unsigned seed = seed_base;
        static uint64_t entregas[200000];
        size_t n = simular_red(entregas, 200000, (size_t)n_mensajes, &seed, 0.05, 0.03);
        long aceptados;
        int disc = correr_diferencial(replay_window_check_and_update_ROTO, entregas, n,
                                       (size_t)n_mensajes + 200, &aceptados);
        chk("la variante ROTA (off-by-one) produce discrepancias detectadas", disc > 0);
        printf("      (%d discrepancias en %zu entregas -- si fuera 0, el fuzzer no serviria)\n",
               disc, n);
    }

    printf("\n1. FUZZING REAL -- replay_window_check_and_update() contra el oraculo\n");
    {
        double escenarios[][2] = {
            {0.00, 0.00},   /* sin perdida ni duplicado: solo reordenamiento por rafaga */
            {0.10, 0.00},   /* 10% de perdida */
            {0.00, 0.10},   /* 10% de duplicado (replay) */
            {0.15, 0.10},   /* los dos a la vez, mas agresivo */
        };
        int n_escenarios = (int)(sizeof(escenarios) / sizeof(escenarios[0]));
        long total_procesado = 0, total_aceptado = 0;
        int total_discrepancias = 0;

        for (int e = 0; e < n_escenarios; e++) {
            unsigned seed = seed_base + (unsigned)e * 7919u;
            static uint64_t entregas[200000];
            size_t n = simular_red(entregas, 200000, (size_t)n_mensajes, &seed,
                                    escenarios[e][0], escenarios[e][1]);
            long aceptados;
            int disc = correr_diferencial(replay_window_check_and_update, entregas, n,
                                           (size_t)n_mensajes + 200, &aceptados);
            printf("   escenario perdida=%.0f%% duplicado=%.0f%%: %zu entregas, %ld aceptadas, %d discrepancias\n",
                   escenarios[e][0] * 100, escenarios[e][1] * 100, n, aceptados, disc);
            total_procesado += (long)n;
            total_aceptado += aceptados;
            total_discrepancias += disc;
        }
        chk("cero discrepancias entre replay_window_t y el oraculo, en todos los escenarios",
            total_discrepancias == 0);
        printf("      total: %ld entregas simuladas, %ld aceptadas\n", total_procesado, total_aceptado);
    }

    printf("\n%s\n", fallos == 0 ? "TODO CORRECTO" : "HAY FALLOS");
    return fallos == 0 ? 0 : 1;
}
