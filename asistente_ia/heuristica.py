from decimal import Decimal, ROUND_CEILING
from django.db.models import Sum
from inventario.models import ItemInventario
from .models import HistorialVentas
from datetime import timedelta, date

# ---------------------------------------------------------------------------
# Mapeo: cuántas unidades de cada flor trae un producto vendido.
# ---------------------------------------------------------------------------

CONTENIDO_ROSAS = {
    'rosas unidad': 1, 'rosas unidad decoradas': 1, 'ramo de tres rosas': 3,
    'ramo de 4 rosas': 4, 'ramo peluche mediano y 4 rosas': 4,
    'ramo 6 rosas y dulces esfera': 6, 'ramo 6 rosas y peluche esfera': 6,
    'lotso pequeño y 6 rosas': 6, 'ramo de 7 rosas': 7, 'ramo con 20 rosas': 20,
    'ramo de peluche mediano y 20 rosas': 20, 'ramo peluche grande y 20 rosas': 20,
    'ramo de 7 girasoles, 6 rosas y 6 plumerias': 6,
    'ramo de 7 con nutella': 7,
    'ramo con espejo': 9,
    'ramo con chocolates corazon': 7,
    'ramo 7 flores y llavero': 7,
    'ramo de 6 flores y peluche': 6,
    'cajita hombre reloj': 1,
    'cajita hombre manilla': 1,
    'caja con billetera': 1,
}

CONTENIDO_GIRASOLES = {
    'unidad girasol': 1,
    'ramo de 7 girasoles, 6 rosas y 6 plumerias': 7,
}

CONTENIDO_LIRIOS = {
    'ramo de 6 lirios': 6,
}

CATEGORIA_INVENTARIO_POR_FLOR = {
    'rosas': 'Rosas',
    'girasoles': 'girasoles',
    'lirios': 'Lirios',
}

METROS_CINTA_POR_ROSA = Decimal('1.10')

MINIMO_SEMANAS_DEFAULT = 5

def inicio_semana(fecha):
    """Devuelve el sábado (fecha_inicio) de la semana a la que pertenece
    `fecha`, consistente con cómo están armadas las semanas en
    HistorialVentas (sábado a sábado). Función compartida — pedidosadmin
    también la usa al registrar ventas presenciales."""
    dias_desde_sabado = (fecha.weekday() - 5) % 7
    return fecha - timedelta(days=dias_desde_sabado)


# ---------------------------------------------------------------------------
# Carga única del historial — llamar UNA vez por request y pasar el resultado
# a todas las demás funciones vía el parámetro `historial`.
# ---------------------------------------------------------------------------

def cargar_historial():
    """Trae TODO el historial de ventas en una sola query, como lista en
    memoria. Pásalo como `historial=` a las demás funciones para evitar que
    cada una vuelva a consultar la base por separado."""
    return list(HistorialVentas.objects.all())


def cargar_stock_por_categoria():
    """Trae el stock actual de Inventario agrupado por categoría, en una
    sola query. Devuelve un dict {nombre_categoria_lower: Decimal}."""
    filas = (
        ItemInventario.objects
        .values('categoria__nombre')
        .annotate(total=Sum('stock_actual'))
    )
    return {
        (f['categoria__nombre'] or '').lower(): (f['total'] or Decimal('0'))
        for f in filas
    }


def _obtener_historial(historial):
    return historial if historial is not None else cargar_historial()


# ---------------------------------------------------------------------------
# Consumo agregado por FLOR (rosas / girasoles / lirios).
# ---------------------------------------------------------------------------

def total_flor_por_semana(mapeo_contenido, fecha_inicio_semana, historial=None):
    """Suma la cantidad total de una flor vendida en una semana específica,
    sumando entre TODOS los productos que la contienen."""
    registros = _obtener_historial(historial)
    total = Decimal('0')
    for r in registros:
        if r.fecha_inicio != fecha_inicio_semana:
            continue
        factor = mapeo_contenido.get(r.producto.strip().lower())
        if factor:
            total += Decimal(r.cantidad) * Decimal(factor)
    return total


def serie_semanal_flor_normal(mapeo_contenido, historial=None):
    """Serie semana a semana, EXCLUYENDO fechas comerciales, para la
    tendencia normal de consumo."""
    registros = _obtener_historial(historial)
    semanas = set()
    acumulado = {}
    for r in registros:
        if r.fecha_comercial not in (None, ''):
            continue
        semanas.add(r.fecha_inicio)
        factor = mapeo_contenido.get(r.producto.strip().lower())
        if factor:
            acumulado[r.fecha_inicio] = acumulado.get(r.fecha_inicio, Decimal('0')) + Decimal(r.cantidad) * Decimal(factor)
    return [(s, acumulado.get(s, Decimal('0'))) for s in sorted(semanas)]


def serie_anual_evento_agregada(mapeo_contenido, nombre_fecha_comercial, historial=None):
    """Como serie_anual_evento, pero sumando TODOS los productos que
    contienen esa flor, y usando MAX cuando dos fecha_inicio distintas
    caen en el mismo año para el mismo evento."""
    registros = _obtener_historial(historial)

    # total por fecha_inicio, solo para este evento
    totales_por_fecha = {}
    for r in registros:
        if (r.fecha_comercial or '').lower() != nombre_fecha_comercial.lower():
            continue
        factor = mapeo_contenido.get(r.producto.strip().lower())
        if not factor:
            continue
        totales_por_fecha[r.fecha_inicio] = totales_por_fecha.get(r.fecha_inicio, Decimal('0')) + Decimal(r.cantidad) * Decimal(factor)

    # colapsar por año con MAX
    totales_por_año = {}
    for fecha, total in totales_por_fecha.items():
        año = fecha.year
        if año not in totales_por_año or total > totales_por_año[año]:
            totales_por_año[año] = total

    return sorted(totales_por_año.items())


def semanas_con_venta_de_flor(mapeo_contenido, minimo=MINIMO_SEMANAS_DEFAULT, historial=None):
    """Cuenta en cuántas semanas distintas se vendió algo de esta flor,
    sin importar la fecha."""
    registros = _obtener_historial(historial)
    semanas = set()
    for r in registros:
        factor = mapeo_contenido.get(r.producto.strip().lower())
        if factor and r.cantidad > 0:
            semanas.add(r.fecha_inicio)
    return len(semanas)


def factor_crecimiento_otras_fechas_flor(mapeo_contenido, excluir_evento=None, historial=None):
    """Promedio del crecimiento año-a-año en OTROS eventos comerciales,
    para estimar un evento que todavía solo tiene 1 año de historia."""
    registros = _obtener_historial(historial)

    eventos = set()
    for r in registros:
        if r.fecha_comercial:
            eventos.add(r.fecha_comercial)

    factores = []
    for evento in eventos:
        if evento == excluir_evento:
            continue
        serie = serie_anual_evento_agregada(mapeo_contenido, evento, historial=registros)
        if len(serie) >= 2:
            valores = [total for _, total in serie]
            if valores[0] and valores[0] != 0:
                factores.append(valores[-1] / valores[0])

    if not factores:
        return None

    promedio = sum(factores) / Decimal(len(factores))
    return max(Decimal('0.8'), min(Decimal('1.8'), promedio))


def necesidad_flor_fecha_comercial(mapeo_contenido, nombre_fecha_comercial, historial=None):
    """Proyecta cuántas unidades de una flor se van a necesitar para la
    próxima ocurrencia de una fecha comercial."""
    from .holt import holt_pronostico  # import local para evitar ciclo si holt.py cambia

    registros = _obtener_historial(historial)
    serie = serie_anual_evento_agregada(mapeo_contenido, nombre_fecha_comercial, historial=registros)
    valores = [total for _, total in serie]

    if len(valores) >= 2:
        resultado = holt_pronostico(valores)
        return resultado['pronostico'].to_integral_value(rounding=ROUND_CEILING)

    if len(valores) == 1:
        factor = factor_crecimiento_otras_fechas_flor(mapeo_contenido, excluir_evento=nombre_fecha_comercial, historial=registros)
        if factor:
            return (valores[0] * factor).to_integral_value(rounding=ROUND_CEILING)
        return valores[0].to_integral_value(rounding=ROUND_CEILING)

    return None


def alerta_stock_flor_fecha_comercial(nombre_flor, nombre_fecha_comercial, dias_entrega_proveedor=3,
                                        minimo_semanas=MINIMO_SEMANAS_DEFAULT, historial=None, stock_por_categoria=None):
    """Revisa si el stock actual de una flor alcanza para la próxima
    fecha comercial. nombre_flor: 'rosas' | 'girasoles' | 'lirios'."""
    mapeos = {'rosas': CONTENIDO_ROSAS, 'girasoles': CONTENIDO_GIRASOLES, 'lirios': CONTENIDO_LIRIOS}
    mapeo_contenido = mapeos.get(nombre_flor)
    categoria_inventario = CATEGORIA_INVENTARIO_POR_FLOR.get(nombre_flor)

    if not mapeo_contenido or not categoria_inventario:
        return None

    registros = _obtener_historial(historial)

    if semanas_con_venta_de_flor(mapeo_contenido, minimo_semanas, historial=registros) < minimo_semanas:
        return {
            'nivel': 'SIN_DATOS',
            'mensaje': f"Todavía no hay suficiente historial de ventas de {nombre_flor} para hacer una predicción confiable, pero es recomendable tener la menos 1",
            'necesidad': None, 'stock_actual': None, 'faltante': None,
        }

    stock_dict = stock_por_categoria if stock_por_categoria is not None else cargar_stock_por_categoria()
    stock_actual = stock_dict.get(categoria_inventario.lower(), Decimal('0'))

    necesidad = necesidad_flor_fecha_comercial(mapeo_contenido, nombre_fecha_comercial, historial=registros)
    if necesidad is None:
        return None

    faltante = necesidad - stock_actual

    if faltante > 0:
        nivel = 'ALERTA'
        mensaje = (
            f"Para {nombre_fecha_comercial} vas a necesitar ~{necesidad} {nombre_flor}, "
            f"pero solo tienes {stock_actual} en inventario. Te faltan ~{faltante}. "
            f"Pide con al menos {dias_entrega_proveedor} días de anticipación."
        )
    else:
        nivel = 'OK'
        mensaje = (
            f"Para {nombre_fecha_comercial} vas a necesitar ~{necesidad} {nombre_flor}, "
            f"y tienes {stock_actual}. Vas bien."
        )

    return {
        'nivel': nivel, 'mensaje': mensaje, 'necesidad': necesidad,
        'stock_actual': stock_actual, 'faltante': max(faltante, Decimal('0')),
    }


def alerta_stock_cinta_fecha_comercial(nombre_fecha_comercial, dias_entrega_proveedor=3,
                                         minimo_semanas=MINIMO_SEMANAS_DEFAULT, historial=None, stock_por_categoria=None):
    """Verifica si el stock de cinta (en metros) alcanza para la cantidad
    de rosas proyectada para la próxima fecha comercial."""
    registros = _obtener_historial(historial)

    if semanas_con_venta_de_flor(CONTENIDO_ROSAS, minimo_semanas, historial=registros) < minimo_semanas:
        return {
            'nivel': 'SIN_DATOS',
            'mensaje': "Todavía no hay suficiente historial de ventas de rosas para proyectar el consumo de cinta.",
            'necesidad_metros': None, 'stock_actual_metros': None, 'faltante_metros': None,
        }

    necesidad_rosas = necesidad_flor_fecha_comercial(CONTENIDO_ROSAS, nombre_fecha_comercial, historial=registros)
    if necesidad_rosas is None:
        return None

    necesidad_metros = (necesidad_rosas * METROS_CINTA_POR_ROSA).quantize(Decimal('0.01'))

    stock_dict = stock_por_categoria if stock_por_categoria is not None else cargar_stock_por_categoria()
    stock_actual = stock_dict.get('cintas', Decimal('0'))

    faltante = necesidad_metros - stock_actual

    if faltante > 0:
        nivel = 'ALERTA'
        mensaje = (
            f"Para {nombre_fecha_comercial} vas a necesitar ~{necesidad_metros} metros de cinta "
            f"({necesidad_rosas} rosas × 1.10m), pero solo tienes {stock_actual} metros. "
            f"Te faltan ~{faltante} metros. Pide con al menos {dias_entrega_proveedor} días de anticipación."
        )
    else:
        nivel = 'OK'
        mensaje = (
            f"Para {nombre_fecha_comercial} vas a necesitar ~{necesidad_metros} metros de cinta, "
            f"y tienes {stock_actual}. Vas bien."
        )

    return {
        'nivel': nivel, 'mensaje': mensaje, 'necesidad_metros': necesidad_metros,
        'stock_actual_metros': stock_actual, 'faltante_metros': max(faltante, Decimal('0')),
    }


def resumen_rosas_y_cinta(nombre_fecha_comercial, dias_entrega_proveedor=3, historial=None, stock_por_categoria=None):
    """Junta en un solo resultado la proyección de rosas y si la cinta
    alcanza, reutilizando el mismo historial/stock ya cargados."""
    registros = _obtener_historial(historial)
    stock_dict = stock_por_categoria if stock_por_categoria is not None else cargar_stock_por_categoria()

    rosas = alerta_stock_flor_fecha_comercial('rosas', nombre_fecha_comercial, dias_entrega_proveedor,
                                                historial=registros, stock_por_categoria=stock_dict)
    cinta = alerta_stock_cinta_fecha_comercial(nombre_fecha_comercial, dias_entrega_proveedor,
                                                 historial=registros, stock_por_categoria=stock_dict)

    return {'fecha_comercial': nombre_fecha_comercial, 'rosas': rosas, 'cinta': cinta}


def necesidad_flor_semana_siguiente(mapeo_contenido, historial=None, semanas_promedio=8):
    """Proyecta cuánto se necesitará la próxima semana normal.
    Usa el promedio de las últimas `semanas_promedio` como nivel base
    (robusto al ruido semana a semana), ajustado por un factor de
    crecimiento de largo plazo (mitad más antigua vs. mitad más reciente
    de todo el historial) — porque el negocio sí muestra crecimiento
    real mes a mes, aunque semana a semana la demanda sea aleatoria."""
    registros = _obtener_historial(historial)
    serie = serie_semanal_flor_completa(mapeo_contenido, historial=registros)
    valores = [total for _, total in serie]

    if len(valores) < 4:
        return None

    # nivel base: promedio de las semanas más recientes
    ultimas = valores[-semanas_promedio:] if len(valores) >= semanas_promedio else valores
    nivel_base = sum(ultimas) / Decimal(len(ultimas))

    # factor de crecimiento de largo plazo: mitad antigua vs. mitad reciente
    mitad = len(valores) // 2
    primera_mitad = valores[:mitad]
    segunda_mitad = valores[mitad:]
    promedio_primera = sum(primera_mitad) / Decimal(len(primera_mitad))
    promedio_segunda = sum(segunda_mitad) / Decimal(len(segunda_mitad))

    if promedio_primera and promedio_primera != 0:
        factor_crecimiento = promedio_segunda / promedio_primera
        factor_crecimiento = max(Decimal('1.0'), min(Decimal('1.5'), factor_crecimiento))
    else:
        factor_crecimiento = Decimal('1.0')

    proyeccion = nivel_base * factor_crecimiento
    return proyeccion.to_integral_value(rounding=ROUND_CEILING)



def serie_semanal_flor_completa(mapeo_contenido, historial=None):
    """Serie semana a semana SIN huecos de calendario: genera cada semana
    (sábado a sábado, paso de 7 días) desde la primera hasta la última
    fecha_inicio del historial, INCLUYENDO las semanas de fecha comercial
    (para no perder la continuidad del eje) pero SIN tomar su historial
    real — esas semanas se muestran con 0, porque esas ventas fueron
    "especiales" y no reflejan la tendencia normal. Si una semana no tiene
    NINGUNA venta registrada (de nada), igual aparece en la serie con
    valor 0 — se conserva la línea de tiempo real del negocio, sin
    saltos."""
    registros = _obtener_historial(historial)
    if not registros:
        return []

    todas_fechas = sorted(set(r.fecha_inicio for r in registros))
    primera = todas_fechas[0]
    semana_actual = inicio_semana(date.today())
    ultima = max(todas_fechas[-1], semana_actual)

    fechas_comerciales = {r.fecha_inicio for r in registros if r.fecha_comercial not in (None, '')}

    acumulado = {}
    for r in registros:
        if r.fecha_inicio in fechas_comerciales:
            continue
        factor = mapeo_contenido.get(r.producto.strip().lower())
        if factor:
            acumulado[r.fecha_inicio] = acumulado.get(r.fecha_inicio, Decimal('0')) + Decimal(r.cantidad) * Decimal(factor)

    serie = []
    actual = primera
    while actual <= ultima:
        # Antes esto se saltaba por completo cuando `actual` era una
        # semana de fecha comercial, y la barra desaparecía del gráfico.
        # Ahora se conserva la semana en el eje, solo que con 0 (porque
        # `acumulado` nunca tiene esa fecha: se excluyó arriba).
        serie.append((actual, acumulado.get(actual, Decimal('0'))))
        actual += timedelta(days=7)

    return serie

def alerta_stock_flor_semana_siguiente(nombre_flor, dias_entrega_proveedor=3,
                                         minimo_semanas=MINIMO_SEMANAS_DEFAULT,
                                         historial=None, stock_por_categoria=None):
    """Igual que alerta_stock_flor_fecha_comercial, pero para la semana
    normal siguiente, no una fecha comercial."""
    mapeos = {'rosas': CONTENIDO_ROSAS, 'girasoles': CONTENIDO_GIRASOLES, 'lirios': CONTENIDO_LIRIOS}
    mapeo_contenido = mapeos.get(nombre_flor)
    categoria_inventario = CATEGORIA_INVENTARIO_POR_FLOR.get(nombre_flor)

    if not mapeo_contenido or not categoria_inventario:
        return None

    registros = _obtener_historial(historial)

    if semanas_con_venta_de_flor(mapeo_contenido, minimo_semanas, historial=registros) < minimo_semanas:
        return {
            'nivel': 'SIN_DATOS',
            'mensaje': f"Todavía no hay suficiente historial semanal de {nombre_flor} para proyectar la próxima semana.",
            'necesidad': None, 'stock_actual': None, 'faltante': None,
        }

    stock_dict = stock_por_categoria if stock_por_categoria is not None else cargar_stock_por_categoria()
    stock_actual = stock_dict.get(categoria_inventario.lower(), Decimal('0'))

    necesidad = necesidad_flor_semana_siguiente(mapeo_contenido, historial=registros)
    if necesidad is None:
        return None

    faltante = necesidad - stock_actual

    if faltante > 0:
        nivel = 'ALERTA'
        mensaje = (
            f"Para la próxima semana vas a necesitar ~{necesidad} {nombre_flor}, "
            f"pero solo tienes {stock_actual}. Te faltan ~{faltante}. "
            f"Pide con al menos {dias_entrega_proveedor} días de anticipación."
        )
    else:
        nivel = 'OK'
        mensaje = f"Para la próxima semana necesitas ~{necesidad} {nombre_flor}, y tienes {stock_actual}. Vas bien."

    return {
        'nivel': nivel, 'mensaje': mensaje, 'necesidad': necesidad,
        'stock_actual': stock_actual, 'faltante': max(faltante, Decimal('0')),
    }


# ---------------------------------------------------------------------------
# NUEVO: para la vista de fechas especiales con flechas.
# ---------------------------------------------------------------------------

def evento_tiene_historial(mapeos_flores, nombre_fecha_comercial, historial=None):
    """True si ALGUNA de las flores (rosas/girasoles/lirios) tiene al menos
    un año de ventas registradas para este evento. Sirve para que un evento
    sin ninguna venta (p. ej. Halloween) no aparezca al navegar."""
    registros = _obtener_historial(historial)
    for mapeo in mapeos_flores:
        if serie_anual_evento_agregada(mapeo, nombre_fecha_comercial, historial=registros):
            return True
    return False


def prediccion_evento_en_anio(mapeo_contenido, nombre_fecha_comercial, anio_objetivo, historial=None):
    """Reconstruye la predicción que el modelo habría dado para
    `anio_objetivo`, usando SOLO los años anteriores a ese año (nunca el
    dato real de ese mismo año). Así se puede comparar predicho vs. real
    incluso después de que la fecha ya pasó, sin haber guardado nada antes."""
    from .holt import holt_pronostico

    registros = _obtener_historial(historial)
    serie = serie_anual_evento_agregada(mapeo_contenido, nombre_fecha_comercial, historial=registros)
    valores_previos = [total for anio, total in serie if anio < anio_objetivo]

    if len(valores_previos) >= 2:
        resultado = holt_pronostico(valores_previos)
        return resultado['pronostico'].to_integral_value(rounding=ROUND_CEILING)

    if len(valores_previos) == 1:
        factor = factor_crecimiento_otras_fechas_flor(mapeo_contenido, excluir_evento=nombre_fecha_comercial, historial=registros)
        if factor:
            return (valores_previos[0] * factor).to_integral_value(rounding=ROUND_CEILING)
        return valores_previos[0].to_integral_value(rounding=ROUND_CEILING)

    return None