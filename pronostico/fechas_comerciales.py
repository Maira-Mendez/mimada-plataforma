from datetime import date, timedelta


def segundo_domingo_mayo(year):
    d = date(year, 5, 1)
    domingos = 0
    while True:
        if d.weekday() == 6:
            domingos += 1
            if domingos == 2:
                return d
        d += timedelta(days=1)


def tercer_sabado_septiembre(year):
    d = date(year, 9, 1)
    sabados = 0
    while True:
        if d.weekday() == 5:
            sabados += 1
            if sabados == 3:
                return d
        d += timedelta(days=1)


def fechas_comerciales(year):
    return {
        date(year, 2, 14): "San Valentín",
        date(year, 3, 8): "Día de la Mujer",
        segundo_domingo_mayo(year): "Día de la Madre",
        tercer_sabado_septiembre(year): "Día del Amor y la Amistad",
        date(year, 10, 31): "Halloween",
        date(year, 12, 7): "Día de las Velitas",
        date(year, 12, 24): "Navidad",
    }


def detectar_fecha_comercial(fecha_inicio, fecha_fin):
    """Dado un rango de fechas, dice si coincide con alguna fecha comercial.
    Si la fecha cae justo en el límite entre 2 semanas, se prioriza la semana
    que YA VENÍA CORRIENDO (fecha_inicio antes de la fecha comercial), no la
    que apenas empieza ese mismo día.

    Se usa para el historial importado de Excel, donde solo se conoce la
    semana agregada de la venta, no el día exacto. Para ventas registradas
    en tiempo real (donde sí se conoce el día exacto), usar
    es_dia_comercial en su lugar — así una venta de un día cualquiera de la
    semana no se marca como comercial solo porque esa semana también
    contiene un evento."""
    for year in (fecha_inicio.year, fecha_fin.year):
        for fecha, nombre in fechas_comerciales(year).items():
            if fecha_inicio <= fecha <= fecha_fin:
                return nombre
    return None


def es_dia_comercial(fecha):
    """Dice si `fecha` (un día exacto, no un rango) es EN SÍ MISMA una
    fecha comercial. A diferencia de detectar_fecha_comercial (que
    compara contra el rango completo de la semana calendario, sábado a
    sábado), esta compara el día exacto contra el día exacto del evento.

    Úsala cuando sí se conoce el día exacto de la venta (por ejemplo al
    registrar una venta en tiempo real desde el panel admin o el
    ecommerce), para que solo el día exacto del evento — no toda la
    semana que lo contiene — quede marcado como fecha_comercial en
    HistorialVentas."""
    eventos = fechas_comerciales(fecha.year)
    return eventos.get(fecha)


def proxima_fecha_comercial(desde=None):
    """Devuelve (fecha, nombre) de la siguiente fecha comercial a partir de hoy."""
    if desde is None:
        desde = date.today()

    candidatas = []
    for year in (desde.year, desde.year + 1):
        candidatas.extend(fechas_comerciales(year).items())

    futuras = [(f, n) for f, n in candidatas if f >= desde]
    futuras.sort(key=lambda x: x[0])
    return futuras[0] if futuras else (None, None)


# ---------------------------------------------------------------------------
# NUEVO: orden cronológico fijo de los eventos (las fechas de cada uno,
# dentro de un mismo año, siempre quedan en este orden — no cambia de año
# a año), usado para poder navegar con flechas entre eventos.
# ---------------------------------------------------------------------------
ORDEN_EVENTOS = [
    "San Valentín",
    "Día de la Mujer",
    "Día de la Madre",
    "Día del Amor y la Amistad",
    "Halloween",
    "Día de las Velitas",
    "Navidad",
]


def fecha_evento_en_anio(nombre, year):
    """Fecha exacta de un evento (por nombre) en un año dado."""
    for fecha, n in fechas_comerciales(year).items():
        if n == nombre:
            return fecha
    return None


def secuencia_eventos(desde):
    """Los 7 eventos comerciales del año de `desde`, en orden cronológico,
    como lista de tuplas (fecha, nombre)."""
    items = [(fecha_evento_en_anio(nombre, desde.year), nombre) for nombre in ORDEN_EVENTOS]
    items.sort(key=lambda x: x[0])
    return items