from django.test import TestCase
import json
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from asistente_ia import fechas_comerciales as fc
from asistente_ia import heuristica
from asistente_ia import views as vistas
from asistente_ia.holt import holt_pronostico, serie_anual_evento
from asistente_ia.models import HistorialVentas
from inventario.models import CategoriaInventario, ItemInventario


# ===========================================================================
# Helpers
# ===========================================================================

@contextmanager
def hoy_congelado(modulo, fecha):
    """Reemplaza `date` dentro de `modulo` para que date.today() devuelva
    `fecha`, pero date(a, m, d) siga construyendo fechas reales."""
    with patch.object(modulo, 'date') as falso_date:
        falso_date.today.return_value = fecha
        falso_date.side_effect = lambda *a, **k: date(*a, **k)
        yield


def crear_venta(producto, inicio, cantidad, comercial=None):
    return HistorialVentas.objects.create(
        producto=producto,
        fecha_inicio=inicio,
        fecha_fin=inicio + timedelta(days=7),
        cantidad=cantidad,
        fecha_comercial=comercial,
    )


def cargar_semanas(valores, inicio=date(2026, 1, 3), producto='rosas unidad'):
    """Crea una venta normal por semana (sábado a sábado). Devuelve el
    inicio de la última semana creada."""
    semana = inicio
    for v in valores:
        crear_venta(producto, semana, v)
        semana += timedelta(days=7)
    return semana - timedelta(days=7)


def cargar_evento(nombre_evento, valores_por_anio, producto='rosas unidad', mes_dia=(2, 10)):
    """valores_por_anio: {2024: 100, 2025: 120}. Una fila por año."""
    for anio, cantidad in valores_por_anio.items():
        crear_venta(producto, date(anio, *mes_dia), cantidad, comercial=nombre_evento)


def crear_stock(nombre_categoria, cantidad, nombre_item=None):
    categoria, _ = CategoriaInventario.objects.get_or_create(nombre=nombre_categoria, tipo='INSUMO')
    return ItemInventario.objects.create(
        categoria=categoria,
        nombre=nombre_item or f'item {nombre_categoria}',
        stock_actual=Decimal(cantidad),
    )


def escenario_rosas_con_san_valentin():
    """6 semanas normales (10 rosas c/u) + San Valentín 2024=100 y 2025=120.
    Holt([100, 120]) => 136 rosas necesarias para San Valentín."""
    cargar_semanas([10] * 6, inicio=date(2025, 11, 29))
    cargar_evento('San Valentín', {2024: 100, 2025: 120})


# TODO: ajusta esto a cómo `admin_requerido` decide quién es admin.
def crear_admin():
    User = get_user_model()
    usuario = User.objects.create_user(username='admin_test', password='clave-segura-123')
    for campo, valor in (('is_staff', True), ('is_superuser', True), ('rol', 'admin'), ('es_admin', True)):
        if hasattr(usuario, campo):
            setattr(usuario, campo, valor)
    usuario.save()
    return usuario


# ===========================================================================
# holt.py — holt_pronostico
# ===========================================================================

class HoltPronosticoTests(SimpleTestCase):

    def test_menos_de_dos_valores_devuelve_none(self):
        self.assertIsNone(holt_pronostico([]))
        self.assertIsNone(holt_pronostico([Decimal('100')]))

    def test_dos_valores_se_degrada_a_recta(self):
        res = holt_pronostico([Decimal('100'), Decimal('120')])
        self.assertEqual(res['nivel'], Decimal('120'))
        self.assertEqual(res['tendencia'], Decimal('20'))
        self.assertEqual(res['pronostico'], Decimal('136'))   # 120 + 0.8 * 20
        self.assertEqual(res['n_observaciones'], 2)
        self.assertTrue(res['degradado_a_lineal'])

    def test_tres_valores_calculo_a_mano(self):
        res = holt_pronostico([Decimal('100'), Decimal('120'), Decimal('150')])
        self.assertEqual(res['nivel'], Decimal('147'))
        self.assertEqual(res['tendencia'], Decimal('22.1'))
        self.assertEqual(res['pronostico'], Decimal('164.68'))
        self.assertEqual(res['n_observaciones'], 3)
        self.assertFalse(res['degradado_a_lineal'])

    def test_serie_constante_pronostica_el_mismo_valor(self):
        res = holt_pronostico([Decimal('50')] * 4)
        self.assertEqual(res['tendencia'], Decimal('0'))
        self.assertEqual(res['pronostico'], Decimal('50'))

    def test_tendencia_decreciente_amortiguada(self):
        res = holt_pronostico([Decimal('100'), Decimal('90')])
        self.assertEqual(res['pronostico'], Decimal('82'))    # 90 + 0.8 * (-10)

    def test_pronostico_nunca_es_negativo(self):
        res = holt_pronostico([Decimal('100'), Decimal('10')])  # daría 10 - 72 = -62
        self.assertEqual(res['pronostico'], Decimal('0'))

    def test_phi_cero_elimina_la_tendencia(self):
        res = holt_pronostico([Decimal('100'), Decimal('120')], phi=Decimal('0'))
        self.assertEqual(res['pronostico'], Decimal('120'))

    def test_resultado_redondeado_a_dos_decimales(self):
        res = holt_pronostico([Decimal('100'), Decimal('120'), Decimal('150')])
        for clave in ('nivel', 'tendencia', 'pronostico'):
            self.assertGreaterEqual(res[clave].as_tuple().exponent, -2)


# ===========================================================================
# holt.py — serie_anual_evento (consulta directa a la BD)
# ===========================================================================

class SerieAnualEventoHoltTests(TestCase):

    def test_usa_max_por_anio_y_ordena(self):
        crear_venta('Rosas Unidad', date(2025, 2, 8), 30, 'San Valentín')
        crear_venta('Rosas Unidad', date(2025, 2, 15), 50, 'San Valentín')
        crear_venta('Rosas Unidad', date(2024, 2, 10), 20, 'San Valentín')
        self.assertEqual(
            serie_anual_evento('rosas unidad', 'San Valentín'),
            [(2024, Decimal('20')), (2025, Decimal('50'))],
        )

    def test_filtra_por_producto_y_evento(self):
        crear_venta('rosas unidad', date(2025, 2, 8), 30, 'San Valentín')
        crear_venta('otro producto', date(2025, 2, 8), 99, 'San Valentín')
        crear_venta('rosas unidad', date(2025, 5, 10), 77, 'Día de la Madre')
        self.assertEqual(serie_anual_evento('rosas unidad', 'San Valentín'), [(2025, Decimal('30'))])

    def test_sin_datos_devuelve_lista_vacia(self):
        self.assertEqual(serie_anual_evento('rosas unidad', 'San Valentín'), [])


# ===========================================================================
# fechas_comerciales.py
# ===========================================================================

class FechasComercialesTests(SimpleTestCase):

    def test_segundo_domingo_de_mayo(self):
        for anio in range(2020, 2031):
            with self.subTest(anio=anio):
                d = fc.segundo_domingo_mayo(anio)
                self.assertEqual(d.weekday(), 6)
                self.assertEqual(d.month, 5)
                self.assertTrue(8 <= d.day <= 14)

    def test_tercer_sabado_de_septiembre(self):
        for anio in range(2020, 2031):
            with self.subTest(anio=anio):
                d = fc.tercer_sabado_septiembre(anio)
                self.assertEqual(d.weekday(), 5)
                self.assertEqual(d.month, 9)
                self.assertTrue(15 <= d.day <= 21)

    def test_fechas_comerciales_tiene_los_siete_eventos(self):
        eventos = fc.fechas_comerciales(2026)
        self.assertEqual(len(eventos), 7)
        self.assertEqual(set(eventos.values()), set(fc.ORDEN_EVENTOS))
        self.assertEqual(eventos[date(2026, 2, 14)], 'San Valentín')
        self.assertEqual(eventos[date(2026, 12, 24)], 'Navidad')

    # --- detectar_fecha_comercial -----------------------------------------

    def test_detectar_semana_con_evento(self):
        self.assertEqual(fc.detectar_fecha_comercial(date(2026, 2, 7), date(2026, 2, 14)), 'San Valentín')

    def test_detectar_semana_sin_evento(self):
        self.assertIsNone(fc.detectar_fecha_comercial(date(2026, 4, 4), date(2026, 4, 11)))

    def test_detectar_semana_que_cruza_de_anio(self):
        self.assertEqual(fc.detectar_fecha_comercial(date(2025, 12, 20), date(2026, 1, 3)), 'Navidad')
        self.assertIsNone(fc.detectar_fecha_comercial(date(2025, 12, 27), date(2026, 1, 3)))

    def test_detectar_evento_en_el_anio_de_fecha_fin(self):
        self.assertEqual(fc.detectar_fecha_comercial(date(2024, 12, 30), date(2025, 2, 20)), 'San Valentín')

    def test_evento_en_sabado_limite_coincide_con_ambas_semanas(self):
        """Documenta el comportamiento ACTUAL: el rango es inclusivo en ambos
        extremos, así que el Día del Amor y la Amistad (siempre sábado)
        marca la semana que termina ese sábado Y la que empieza ese sábado.
        El docstring dice que debería priorizarse la semana que venía
        corriendo; si quieres ese comportamiento, este test debe cambiar."""
        sabado = fc.tercer_sabado_septiembre(2026)
        semana_previa = fc.detectar_fecha_comercial(sabado - timedelta(days=7), sabado)
        semana_nueva = fc.detectar_fecha_comercial(sabado, sabado + timedelta(days=7))
        self.assertEqual(semana_previa, 'Día del Amor y la Amistad')
        self.assertEqual(semana_nueva, 'Día del Amor y la Amistad')

    # --- es_dia_comercial -------------------------------------------------

    def test_es_dia_comercial(self):
        self.assertEqual(fc.es_dia_comercial(date(2026, 2, 14)), 'San Valentín')
        self.assertEqual(fc.es_dia_comercial(date(2026, 10, 31)), 'Halloween')
        self.assertIsNone(fc.es_dia_comercial(date(2026, 2, 15)))

    # --- proxima_fecha_comercial -----------------------------------------

    def test_proxima_fecha_comercial_normal(self):
        self.assertEqual(fc.proxima_fecha_comercial(date(2026, 11, 3)), (date(2026, 12, 7), 'Día de las Velitas'))

    def test_proxima_fecha_incluye_el_mismo_dia(self):
        self.assertEqual(fc.proxima_fecha_comercial(date(2026, 2, 14)), (date(2026, 2, 14), 'San Valentín'))

    def test_proxima_fecha_salta_al_anio_siguiente(self):
        self.assertEqual(fc.proxima_fecha_comercial(date(2026, 12, 25)), (date(2027, 2, 14), 'San Valentín'))

    def test_proxima_fecha_sin_argumento_usa_hoy(self):
        with hoy_congelado(fc, date(2026, 11, 3)):
            self.assertEqual(fc.proxima_fecha_comercial()[1], 'Día de las Velitas')

    # --- fecha_evento_en_anio / secuencia_eventos ------------------------

    def test_fecha_evento_en_anio(self):
        self.assertEqual(fc.fecha_evento_en_anio('Navidad', 2026), date(2026, 12, 24))
        self.assertIsNone(fc.fecha_evento_en_anio('Evento inventado', 2026))

    def test_secuencia_eventos_orden_cronologico(self):
        seq = fc.secuencia_eventos(date(2026, 6, 1))
        self.assertEqual(len(seq), 7)
        self.assertEqual([n for _, n in seq], fc.ORDEN_EVENTOS)
        fechas = [f for f, _ in seq]
        self.assertEqual(fechas, sorted(fechas))
        self.assertTrue(all(f.year == 2026 for f in fechas))


# ===========================================================================
# heuristica.py — inicio_semana
# ===========================================================================

class InicioSemanaTests(SimpleTestCase):

    def test_cada_dia_cae_en_su_sabado(self):
        sabado = date(2026, 1, 3)
        self.assertEqual(sabado.weekday(), 5)  # sanity check
        for offset in range(7):  # sábado .. viernes
            with self.subTest(offset=offset):
                self.assertEqual(heuristica.inicio_semana(sabado + timedelta(days=offset)), sabado)

    def test_el_siguiente_sabado_inicia_nueva_semana(self):
        self.assertEqual(heuristica.inicio_semana(date(2026, 1, 10)), date(2026, 1, 10))


# ===========================================================================
# heuristica.py — cargas y series
# ===========================================================================

class CargasTests(TestCase):

    def test_cargar_historial_devuelve_lista(self):
        crear_venta('rosas unidad', date(2026, 1, 3), 1)
        crear_venta('rosas unidad', date(2026, 1, 10), 2)
        resultado = heuristica.cargar_historial()
        self.assertIsInstance(resultado, list)
        self.assertEqual(len(resultado), 2)

    def test_cargar_stock_agrupa_suma_y_pone_minusculas(self):
        crear_stock('Rosas', '60', 'rosa roja')
        crear_stock('Rosas', '80', 'rosa blanca')
        crear_stock('Cintas', '25.50', 'cinta roja')
        stock = heuristica.cargar_stock_por_categoria()
        self.assertEqual(stock['rosas'], Decimal('140'))
        self.assertEqual(stock['cintas'], Decimal('25.50'))

    def test_cargar_stock_sin_items_devuelve_dict_vacio(self):
        self.assertEqual(heuristica.cargar_stock_por_categoria(), {})


class TotalFlorPorSemanaTests(TestCase):

    def test_suma_productos_con_factor_y_normaliza_nombre(self):
        semana = date(2026, 1, 3)
        crear_venta('  Ramo De Tres Rosas ', semana, 2)   # 2 * 3 = 6
        crear_venta('rosas unidad', semana, 5)            # 5
        crear_venta('producto desconocido', semana, 99)   # ignorado
        crear_venta('rosas unidad', date(2026, 1, 10), 40)  # otra semana
        total = heuristica.total_flor_por_semana(heuristica.CONTENIDO_ROSAS, semana)
        self.assertEqual(total, Decimal('11'))

    def test_producto_mixto_cuenta_en_cada_flor(self):
        semana = date(2026, 1, 3)
        crear_venta('ramo de 7 girasoles, 6 rosas y 6 plumerias', semana, 2)
        self.assertEqual(heuristica.total_flor_por_semana(heuristica.CONTENIDO_ROSAS, semana), Decimal('12'))
        self.assertEqual(heuristica.total_flor_por_semana(heuristica.CONTENIDO_GIRASOLES, semana), Decimal('14'))

    def test_acepta_historial_precargado_sin_consultar_bd(self):
        semana = date(2026, 1, 3)
        crear_venta('rosas unidad', semana, 3)
        historial = heuristica.cargar_historial()
        with self.assertNumQueries(0):
            total = heuristica.total_flor_por_semana(heuristica.CONTENIDO_ROSAS, semana, historial=historial)
        self.assertEqual(total, Decimal('3'))


class SerieSemanalNormalTests(TestCase):

    def test_excluye_filas_comerciales_y_conserva_semanas_sin_flor(self):
        crear_venta('rosas unidad', date(2026, 1, 3), 3)
        crear_venta('producto desconocido', date(2026, 1, 10), 7)               # semana sin rosas -> 0
        crear_venta('rosas unidad', date(2026, 1, 17), 50, comercial='Navidad')  # excluida
        crear_venta('rosas unidad', date(2026, 1, 24), 4, comercial='')          # '' cuenta como normal
        serie = heuristica.serie_semanal_flor_normal(heuristica.CONTENIDO_ROSAS)
        self.assertEqual(serie, [
            (date(2026, 1, 3), Decimal('3')),
            (date(2026, 1, 10), Decimal('0')),
            (date(2026, 1, 24), Decimal('4')),
        ])

    def test_sin_historial(self):
        self.assertEqual(heuristica.serie_semanal_flor_normal(heuristica.CONTENIDO_ROSAS), [])


class SerieSemanalCompletaTests(TestCase):

    def test_sin_historial_devuelve_lista_vacia(self):
        self.assertEqual(heuristica.serie_semanal_flor_completa(heuristica.CONTENIDO_ROSAS), [])

    def test_rellena_huecos_y_se_extiende_hasta_la_semana_actual(self):
        crear_venta('rosas unidad', date(2026, 1, 3), 4)
        crear_venta('rosas unidad', date(2026, 1, 10), 10, comercial='Evento')  # fila excluida
        with hoy_congelado(heuristica, date(2026, 1, 20)):  # martes; semana actual = sáb 17 ene
            serie = heuristica.serie_semanal_flor_completa(heuristica.CONTENIDO_ROSAS)
        self.assertEqual(serie, [
            (date(2026, 1, 3), Decimal('4')),
            (date(2026, 1, 10), Decimal('0')),
            (date(2026, 1, 17), Decimal('0')),
        ])

    def test_semana_con_venta_normal_y_comercial_suma_solo_lo_normal(self):
        crear_venta('rosas unidad', date(2026, 1, 3), 4)
        crear_venta('rosas unidad', date(2026, 1, 3), 100, comercial='Evento')
        with hoy_congelado(heuristica, date(2026, 1, 4)):
            serie = heuristica.serie_semanal_flor_completa(heuristica.CONTENIDO_ROSAS)
        self.assertEqual(serie, [(date(2026, 1, 3), Decimal('4'))])

    def test_no_recorta_si_el_historial_llega_mas_alla_de_hoy(self):
        crear_venta('rosas unidad', date(2026, 1, 3), 1)
        crear_venta('rosas unidad', date(2026, 1, 17), 2)
        with hoy_congelado(heuristica, date(2026, 1, 5)):
            serie = heuristica.serie_semanal_flor_completa(heuristica.CONTENIDO_ROSAS)
        self.assertEqual([f for f, _ in serie], [date(2026, 1, 3), date(2026, 1, 10), date(2026, 1, 17)])

    def test_hueco_intermedio_queda_en_cero(self):
        crear_venta('rosas unidad', date(2026, 1, 3), 1)
        crear_venta('rosas unidad', date(2026, 1, 24), 2)
        with hoy_congelado(heuristica, date(2026, 1, 24)):
            serie = heuristica.serie_semanal_flor_completa(heuristica.CONTENIDO_ROSAS)
        self.assertEqual([v for _, v in serie], [Decimal('1'), Decimal('0'), Decimal('0'), Decimal('2')])


class SerieAnualEventoAgregadaTests(TestCase):

    def test_suma_productos_y_usa_max_por_anio(self):
        crear_venta('rosas unidad', date(2024, 2, 10), 10, 'San Valentín')       # 10
        crear_venta('ramo de tres rosas', date(2024, 2, 10), 2, 'San Valentín')  # 6 -> 16 ese año
        crear_venta('rosas unidad', date(2025, 2, 8), 30, 'San Valentín')
        crear_venta('rosas unidad', date(2025, 2, 15), 20, 'San Valentín')       # MAX(30, 20) = 30
        crear_venta('rosas unidad', date(2025, 5, 10), 500, 'Día de la Madre')   # otro evento
        crear_venta('producto desconocido', date(2025, 2, 8), 500, 'San Valentín')
        serie = heuristica.serie_anual_evento_agregada(heuristica.CONTENIDO_ROSAS, 'San Valentín')
        self.assertEqual(serie, [(2024, Decimal('16')), (2025, Decimal('30'))])

    def test_nombre_de_evento_insensible_a_mayusculas(self):
        crear_venta('rosas unidad', date(2025, 2, 8), 30, 'San Valentín')
        serie = heuristica.serie_anual_evento_agregada(heuristica.CONTENIDO_ROSAS, 'SAN VALENTÍN')
        self.assertEqual(serie, [(2025, Decimal('30'))])

    def test_sin_datos(self):
        self.assertEqual(heuristica.serie_anual_evento_agregada(heuristica.CONTENIDO_ROSAS, 'Navidad'), [])


class SemanasConVentaTests(TestCase):

    def test_cuenta_semanas_distintas_con_cantidad_positiva(self):
        crear_venta('rosas unidad', date(2026, 1, 3), 2)
        crear_venta('ramo de tres rosas', date(2026, 1, 3), 1)    # misma semana, cuenta una vez
        crear_venta('rosas unidad', date(2026, 1, 10), 0)         # cantidad 0, no cuenta
        crear_venta('producto desconocido', date(2026, 1, 17), 5)  # no es rosa
        crear_venta('rosas unidad', date(2026, 1, 24), 1)
        self.assertEqual(heuristica.semanas_con_venta_de_flor(heuristica.CONTENIDO_ROSAS), 2)

    def test_sin_ventas(self):
        self.assertEqual(heuristica.semanas_con_venta_de_flor(heuristica.CONTENIDO_LIRIOS), 0)


class EventoTieneHistorialTests(TestCase):

    def test_true_si_alguna_flor_tiene_ventas_del_evento(self):
        crear_venta('unidad girasol', date(2025, 2, 8), 5, 'San Valentín')
        mapeos = [heuristica.CONTENIDO_ROSAS, heuristica.CONTENIDO_GIRASOLES, heuristica.CONTENIDO_LIRIOS]
        self.assertTrue(heuristica.evento_tiene_historial(mapeos, 'San Valentín'))

    def test_false_sin_ventas_o_con_productos_no_mapeados(self):
        crear_venta('producto desconocido', date(2025, 10, 31), 5, 'Halloween')
        mapeos = [heuristica.CONTENIDO_ROSAS, heuristica.CONTENIDO_GIRASOLES, heuristica.CONTENIDO_LIRIOS]
        self.assertFalse(heuristica.evento_tiene_historial(mapeos, 'Halloween'))
        self.assertFalse(heuristica.evento_tiene_historial(mapeos, 'Navidad'))


# ===========================================================================
# heuristica.py — factor de crecimiento y proyecciones por evento
# ===========================================================================

class FactorCrecimientoTests(TestCase):

    def factor(self, **kw):
        return heuristica.factor_crecimiento_otras_fechas_flor(heuristica.CONTENIDO_ROSAS, **kw)

    def test_sin_eventos_devuelve_none(self):
        self.assertIsNone(self.factor())

    def test_eventos_con_un_solo_anio_devuelven_none(self):
        cargar_evento('Navidad', {2025: 50})
        self.assertIsNone(self.factor())

    def test_calcula_ultimo_sobre_primero(self):
        cargar_evento('Navidad', {2024: 10, 2025: 15})
        self.assertEqual(self.factor(), Decimal('1.5'))

    def test_promedia_varios_eventos(self):
        cargar_evento('Navidad', {2024: 10, 2025: 15})     # 1.5
        cargar_evento('Halloween', {2024: 10, 2025: 10})   # 1.0
        self.assertEqual(self.factor(), Decimal('1.25'))

    def test_tope_superior_1_8(self):
        cargar_evento('Navidad', {2024: 10, 2025: 100})
        self.assertEqual(self.factor(), Decimal('1.8'))

    def test_tope_inferior_0_8(self):
        cargar_evento('Navidad', {2024: 100, 2025: 10})
        self.assertEqual(self.factor(), Decimal('0.8'))

    def test_excluye_el_evento_indicado(self):
        cargar_evento('San Valentín', {2024: 10, 2025: 100})  # excluido
        cargar_evento('Navidad', {2024: 10, 2025: 15})
        self.assertEqual(self.factor(excluir_evento='San Valentín'), Decimal('1.5'))

    def test_ignora_eventos_cuyo_primer_anio_es_cero(self):
        cargar_evento('Navidad', {2024: 0, 2025: 15})
        self.assertIsNone(self.factor())


class NecesidadFechaComercialTests(TestCase):

    def necesidad(self, evento='San Valentín'):
        return heuristica.necesidad_flor_fecha_comercial(heuristica.CONTENIDO_ROSAS, evento)

    def test_sin_historia_devuelve_none(self):
        self.assertIsNone(self.necesidad())

    def test_un_anio_sin_otros_eventos_repite_el_valor(self):
        cargar_evento('San Valentín', {2025: 16})
        self.assertEqual(self.necesidad(), Decimal('16'))

    def test_un_anio_con_otros_eventos_aplica_factor(self):
        cargar_evento('San Valentín', {2025: 10})
        cargar_evento('Navidad', {2023: 10, 2024: 15})  # factor 1.5
        self.assertEqual(self.necesidad(), Decimal('15'))

    def test_dos_anios_usa_holt(self):
        cargar_evento('San Valentín', {2024: 100, 2025: 120})
        self.assertEqual(self.necesidad(), Decimal('136'))

    def test_redondea_hacia_arriba(self):
        cargar_evento('San Valentín', {2024: 100, 2025: 121})  # Holt = 137.8
        self.assertEqual(self.necesidad(), Decimal('138'))


class PrediccionEventoEnAnioTests(TestCase):

    def prediccion(self, anio):
        return heuristica.prediccion_evento_en_anio(heuristica.CONTENIDO_ROSAS, 'San Valentín', anio)

    def setUp(self):
        cargar_evento('San Valentín', {2023: 100, 2024: 120, 2025: 200})

    def test_no_usa_el_dato_real_del_anio_objetivo(self):
        # Para 2025 solo ve 2023 y 2024 -> Holt([100, 120]) = 136, no influye el 200 real.
        self.assertEqual(self.prediccion(2025), Decimal('136'))

    def test_un_solo_anio_previo_repite_valor(self):
        self.assertEqual(self.prediccion(2024), Decimal('100'))

    def test_sin_anios_previos_devuelve_none(self):
        self.assertIsNone(self.prediccion(2023))

    def test_anio_futuro_usa_todos_los_datos(self):
        # Holt([100, 120, 200]) = 208.08 -> 209
        self.assertEqual(self.prediccion(2026), Decimal('209'))


# ===========================================================================
# heuristica.py — necesidad semana siguiente
# ===========================================================================

class NecesidadSemanaSiguienteTests(TestCase):

    def necesidad(self, valores, **kw):
        ultima = cargar_semanas(valores)
        with hoy_congelado(heuristica, ultima):
            return heuristica.necesidad_flor_semana_siguiente(heuristica.CONTENIDO_ROSAS, **kw)

    def test_menos_de_cuatro_semanas_devuelve_none(self):
        self.assertIsNone(self.necesidad([10, 10, 10]))

    def test_serie_constante(self):
        self.assertEqual(self.necesidad([10] * 8), Decimal('10'))

    def test_crecimiento_moderado(self):
        # base = 11, factor = 12/10 = 1.2 -> 13.2 -> 14
        self.assertEqual(self.necesidad([10, 10, 12, 12]), Decimal('14'))

    def test_factor_de_crecimiento_tope_1_5(self):
        # base = 15, factor = 2 -> tope 1.5 -> 22.5 -> 23
        self.assertEqual(self.necesidad([10, 10, 20, 20]), Decimal('23'))

    def test_factor_nunca_baja_de_1(self):
        # base = 15, factor 0.5 -> piso 1.0 -> 15
        self.assertEqual(self.necesidad([20, 20, 10, 10]), Decimal('15'))

    def test_primera_mitad_en_cero_no_aplica_crecimiento(self):
        self.assertEqual(self.necesidad([0, 0, 10, 10]), Decimal('5'))

    def test_semanas_promedio_define_el_nivel_base(self):
        valores = [1, 1, 1, 1, 10, 10, 10, 10]
        # últimas 4 -> base 10; factor 10 -> tope 1.5 -> 15
        self.assertEqual(self.necesidad(valores, semanas_promedio=4), Decimal('15'))


# ===========================================================================
# heuristica.py — alertas de stock
# ===========================================================================

class AlertaStockFlorFechaComercialTests(TestCase):

    def alerta(self, flor='rosas', evento='San Valentín', **kw):
        return heuristica.alerta_stock_flor_fecha_comercial(flor, evento, **kw)

    def test_flor_invalida_devuelve_none(self):
        self.assertIsNone(self.alerta(flor='orquideas'))

    def test_sin_datos_si_hay_pocas_semanas(self):
        cargar_semanas([10, 10, 10])
        res = self.alerta()
        self.assertEqual(res['nivel'], 'SIN_DATOS')
        self.assertIsNone(res['necesidad'])
        self.assertIsNone(res['stock_actual'])
        self.assertIsNone(res['faltante'])

    def test_none_si_no_hay_historia_del_evento(self):
        escenario_rosas_con_san_valentin()
        self.assertIsNone(self.alerta(evento='Halloween'))

    def test_alerta_cuando_falta_stock(self):
        escenario_rosas_con_san_valentin()
        crear_stock('Rosas', '100')
        res = self.alerta()
        self.assertEqual(res['nivel'], 'ALERTA')
        self.assertEqual(res['necesidad'], Decimal('136'))
        self.assertEqual(res['stock_actual'], Decimal('100'))
        self.assertEqual(res['faltante'], Decimal('36'))
        self.assertIn('San Valentín', res['mensaje'])

    def test_ok_cuando_sobra_stock(self):
        escenario_rosas_con_san_valentin()
        crear_stock('Rosas', '200')
        res = self.alerta()
        self.assertEqual(res['nivel'], 'OK')
        self.assertEqual(res['faltante'], Decimal('0'))

    def test_stock_exacto_es_ok(self):
        escenario_rosas_con_san_valentin()
        crear_stock('Rosas', '136')
        self.assertEqual(self.alerta()['nivel'], 'OK')

    def test_sin_inventario_cuenta_stock_cero(self):
        escenario_rosas_con_san_valentin()
        res = self.alerta()
        self.assertEqual(res['stock_actual'], Decimal('0'))
        self.assertEqual(res['faltante'], Decimal('136'))

    def test_suma_varios_items_de_la_misma_categoria(self):
        escenario_rosas_con_san_valentin()
        crear_stock('Rosas', '60', 'rosa roja')
        crear_stock('Rosas', '80', 'rosa blanca')
        self.assertEqual(self.alerta()['nivel'], 'OK')

    def test_usa_stock_y_historial_inyectados(self):
        escenario_rosas_con_san_valentin()
        historial = heuristica.cargar_historial()
        res = self.alerta(historial=historial, stock_por_categoria={'rosas': Decimal('10')})
        self.assertEqual(res['stock_actual'], Decimal('10'))
        self.assertEqual(res['faltante'], Decimal('126'))

    def test_dias_de_entrega_aparece_en_el_mensaje_de_alerta(self):
        escenario_rosas_con_san_valentin()
        res = self.alerta(dias_entrega_proveedor=5)
        self.assertIn('5 días', res['mensaje'])

    def test_minimo_semanas_configurable(self):
        escenario_rosas_con_san_valentin()  # 8 semanas con venta
        self.assertEqual(self.alerta(minimo_semanas=50)['nivel'], 'SIN_DATOS')


class AlertaStockCintaTests(TestCase):

    def test_sin_datos_si_hay_pocas_semanas(self):
        cargar_semanas([10, 10])
        res = heuristica.alerta_stock_cinta_fecha_comercial('San Valentín')
        self.assertEqual(res['nivel'], 'SIN_DATOS')
        self.assertIsNone(res['necesidad_metros'])

    def test_none_si_no_hay_historia_del_evento(self):
        escenario_rosas_con_san_valentin()
        self.assertIsNone(heuristica.alerta_stock_cinta_fecha_comercial('Halloween'))

    def test_alerta_cuando_faltan_metros(self):
        escenario_rosas_con_san_valentin()
        crear_stock('Cintas', '100')
        res = heuristica.alerta_stock_cinta_fecha_comercial('San Valentín')
        self.assertEqual(res['nivel'], 'ALERTA')
        self.assertEqual(res['necesidad_metros'], Decimal('149.60'))   # 136 * 1.10
        self.assertEqual(res['faltante_metros'], Decimal('49.60'))

    def test_ok_cuando_alcanza(self):
        escenario_rosas_con_san_valentin()
        crear_stock('Cintas', '200')
        res = heuristica.alerta_stock_cinta_fecha_comercial('San Valentín')
        self.assertEqual(res['nivel'], 'OK')
        self.assertEqual(res['faltante_metros'], Decimal('0'))

    def test_sin_cintas_en_inventario_stock_cero(self):
        escenario_rosas_con_san_valentin()
        res = heuristica.alerta_stock_cinta_fecha_comercial('San Valentín')
        self.assertEqual(res['stock_actual_metros'], Decimal('0'))
        self.assertEqual(res['faltante_metros'], Decimal('149.60'))


class ResumenRosasYCintaTests(TestCase):

    def test_combina_rosas_y_cinta(self):
        escenario_rosas_con_san_valentin()
        crear_stock('Rosas', '200')
        crear_stock('Cintas', '10')
        res = heuristica.resumen_rosas_y_cinta('San Valentín')
        self.assertEqual(res['fecha_comercial'], 'San Valentín')
        self.assertEqual(res['rosas']['nivel'], 'OK')
        self.assertEqual(res['cinta']['nivel'], 'ALERTA')

    def test_reutiliza_historial_y_stock_cargados(self):
        escenario_rosas_con_san_valentin()
        historial = heuristica.cargar_historial()
        stock = {'rosas': Decimal('0'), 'cintas': Decimal('0')}
        with self.assertNumQueries(0):
            res = heuristica.resumen_rosas_y_cinta('San Valentín', historial=historial, stock_por_categoria=stock)
        self.assertEqual(res['rosas']['nivel'], 'ALERTA')


class AlertaStockSemanaSiguienteTests(TestCase):

    def alerta(self, ultima_semana, flor='rosas', **kw):
        with hoy_congelado(heuristica, ultima_semana):
            return heuristica.alerta_stock_flor_semana_siguiente(flor, **kw)

    def test_flor_invalida_devuelve_none(self):
        ultima = cargar_semanas([10] * 8)
        self.assertIsNone(self.alerta(ultima, flor='orquideas'))

    def test_sin_datos_si_hay_pocas_semanas(self):
        ultima = cargar_semanas([10, 10, 10])
        res = self.alerta(ultima)
        self.assertEqual(res['nivel'], 'SIN_DATOS')
        self.assertIsNone(res['necesidad'])

    def test_alerta_cuando_falta_stock(self):
        ultima = cargar_semanas([10] * 8)
        crear_stock('Rosas', '5')
        res = self.alerta(ultima)
        self.assertEqual(res['nivel'], 'ALERTA')
        self.assertEqual(res['necesidad'], Decimal('10'))
        self.assertEqual(res['faltante'], Decimal('5'))

    def test_ok_cuando_alcanza(self):
        ultima = cargar_semanas([10] * 8)
        crear_stock('Rosas', '20')
        res = self.alerta(ultima)
        self.assertEqual(res['nivel'], 'OK')
        self.assertEqual(res['faltante'], Decimal('0'))

    def test_none_si_hay_menos_de_cuatro_semanas_con_minimo_bajo(self):
        ultima = cargar_semanas([10, 10, 10])
        self.assertIsNone(self.alerta(ultima, minimo_semanas=1))


# ===========================================================================
# views.py — helpers internos
# ===========================================================================

class LineaDeTiempoYEventoActualTests(TestCase):

    def test_linea_de_tiempo_solo_incluye_eventos_con_historial(self):
        cargar_evento('San Valentín', {2025: 100})
        cargar_evento('Navidad', {2025: 50}, mes_dia=(12, 20))
        historial = heuristica.cargar_historial()
        nodos = vistas._linea_de_tiempo_eventos(historial, hoy=date(2026, 11, 3))
        self.assertEqual(
            [(n['nombre'], n['anio']) for n in nodos],
            [('San Valentín', 2026), ('Navidad', 2026), ('San Valentín', 2027), ('Navidad', 2027)],
        )
        fechas = [n['fecha'] for n in nodos]
        self.assertEqual(fechas, sorted(fechas))

    def test_linea_de_tiempo_vacia_sin_historial(self):
        self.assertEqual(vistas._linea_de_tiempo_eventos([], hoy=date(2026, 11, 3)), [])

    def test_idx_default_es_el_proximo_evento(self):
        nodos = [
            {'fecha': date(2026, 2, 14), 'nombre': 'a', 'anio': 2026},
            {'fecha': date(2026, 12, 24), 'nombre': 'b', 'anio': 2026},
        ]
        self.assertEqual(vistas._idx_default(nodos, date(2026, 11, 3)), 1)
        self.assertEqual(vistas._idx_default(nodos, date(2026, 12, 24)), 1)  # el mismo día cuenta

    def test_idx_default_si_todos_pasaron_es_el_ultimo(self):
        nodos = [
            {'fecha': date(2026, 2, 14), 'nombre': 'a', 'anio': 2026},
            {'fecha': date(2026, 3, 8), 'nombre': 'b', 'anio': 2026},
        ]
        self.assertEqual(vistas._idx_default(nodos, date(2027, 1, 1)), 1)

    def _nodos(self):
        return [
            {'fecha': date(2025, 2, 14), 'nombre': 'San Valentín', 'anio': 2025},
            {'fecha': date(2025, 12, 24), 'nombre': 'Navidad', 'anio': 2025},
            {'fecha': date(2026, 2, 14), 'nombre': 'San Valentín', 'anio': 2026},
        ]

    def test_evento_futuro_incluye_barra_estimada(self):
        cargar_evento('San Valentín', {2024: 100, 2025: 120})
        historial = heuristica.cargar_historial()
        res = vistas._armar_evento_actual(self._nodos(), 2, historial, date(2026, 1, 10))
        self.assertTrue(res['es_futuro'])
        self.assertEqual(len(res['flores']), 1)  # solo rosas tiene datos
        rosas = res['flores'][0]
        self.assertEqual(rosas['clave'], 'rosas')
        self.assertEqual(json.loads(rosas['labels']), ['2024', '2025', '2026 (est.)'])
        self.assertEqual(json.loads(rosas['valores']), [100.0, 120.0, 136.0])
        self.assertEqual(rosas['indice_prediccion'], 2)

    def test_evento_antiguo_no_reconstruye_prediccion(self):
        cargar_evento('San Valentín', {2024: 100, 2025: 120})
        historial = heuristica.cargar_historial()
        res = vistas._armar_evento_actual(self._nodos(), 0, historial, date(2026, 1, 10))
        self.assertFalse(res['es_futuro'])
        rosas = res['flores'][0]
        self.assertEqual(json.loads(rosas['labels']), ['2024', '2025'])
        self.assertIsNone(rosas['indice_prediccion'])

    def test_evento_recien_pasado_si_reconstruye_prediccion(self):
        cargar_evento('San Valentín', {2024: 100, 2025: 120})
        cargar_evento('Navidad', {2024: 50}, mes_dia=(12, 20))
        historial = heuristica.cargar_historial()
        # Navidad 2025: un año previo (50) * factor de otros eventos (120/100 = 1.2) = 60
        res = vistas._armar_evento_actual(self._nodos(), 1, historial, date(2026, 1, 10))
        self.assertFalse(res['es_futuro'])
        rosas = res['flores'][0]
        self.assertEqual(json.loads(rosas['labels']), ['2024', '2025 (est.)'])
        self.assertEqual(json.loads(rosas['valores']), [50.0, 60.0])
        self.assertEqual(rosas['indice_prediccion'], 1)


# ===========================================================================
# views.py — dashboard
# ===========================================================================

class DashboardViewTests(TestCase):
    HOY = date(2026, 1, 20)

    def setUp(self):
        self.url = reverse('asistente_ia:dashboard')

    def get(self, params=None, proxima=(None, None)):
        """GET al dashboard como admin, con fecha congelada."""
        self.client.force_login(crear_admin())
        with hoy_congelado(vistas, self.HOY), hoy_congelado(heuristica, self.HOY), \
                patch.object(vistas, 'proxima_fecha_comercial', return_value=proxima):
            return self.client.get(self.url, params or {})

    def test_usuario_anonimo_no_ve_el_dashboard(self):
        respuesta = self.client.get(self.url)
        self.assertNotEqual(respuesta.status_code, 200)

    def test_admin_sin_datos_responde_200(self):
        respuesta = self.get()
        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(respuesta.context['evento_actual'])
        self.assertIsNone(respuesta.context['cinta'])
        self.assertEqual(respuesta.context['nav'], {'anterior': None, 'siguiente': None})
        self.assertEqual([s['clave'] for s in respuesta.context['secciones']], ['rosas', 'girasoles', 'lirios'])

    def test_con_datos_arma_alertas_cinta_y_graficas(self):
        escenario_rosas_con_san_valentin()
        # semanas normales hasta el 17 ene 2026 (semana actual para HOY)
        respuesta = self.get(proxima=(date(2026, 2, 14), 'San Valentín'))
        self.assertEqual(respuesta.status_code, 200)

        rosas = respuesta.context['secciones'][0]
        self.assertEqual(rosas['alerta']['nivel'], 'ALERTA')
        self.assertEqual(rosas['alerta']['necesidad'], Decimal('136'))
        self.assertEqual(respuesta.context['cinta']['necesidad_metros'], Decimal('149.60'))
        self.assertEqual(respuesta.context['nombre_fecha_proxima'], 'San Valentín')

        labels = json.loads(rosas['chart_labels'])
        valores = json.loads(rosas['chart_valores'])
        self.assertEqual(len(labels), len(valores))
        self.assertEqual(labels[-1], 'Próx. semana')
        self.assertEqual(len(labels), 9)  # 8 semanas + proyección

        girasoles = respuesta.context['secciones'][1]
        self.assertEqual(girasoles['alerta']['nivel'], 'SIN_DATOS')
        self.assertEqual(len(json.loads(girasoles['chart_labels'])), 8)  # sin barra de proyección


    def test_parametros_de_evento_invalidos_caen_al_default(self):
        escenario_rosas_con_san_valentin()
        respuesta = self.get({'evento': 'Inventado', 'anio': '1999'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['evento_actual']['anio'], 2026)
