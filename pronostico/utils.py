from datetime import timedelta
from .models import HistorialVentas
from .fechas_comerciales import es_dia_comercial

#    mapea nombres reales del catálogo -> nombre histórico en el Excel
ALIAS_PRODUCTOS = {
    'ramo de 7 rosas': 'ramo de 7 rosas',
    'ramo 7 rosas': 'ramo de 7 rosas',
    'ramo de siete rosas': 'ramo de 7 rosas',
    # agrega aquí cualquier variante que use tu compañera en el catálogo
}


def normalizar_nombre_producto(nombre):
    nombre = nombre.strip().lower()
    return ALIAS_PRODUCTOS.get(nombre, nombre)

def inicio_de_semana(fecha):
    """Lunes de la semana que contiene esa fecha."""
    return fecha - timedelta(days=fecha.weekday())


def registrar_venta(producto, cantidad, fecha):
    if cantidad <= 0:
        return

    fecha_inicio = inicio_de_semana(fecha)
    fecha_fin = fecha_inicio + timedelta(days=6)
    # Día exacto de la venta contra el día exacto del evento — no el rango
    # completo de la semana (mismo criterio que pedidosadmin/views.py).
    comercial = es_dia_comercial(fecha)

    # comercial va DENTRO de la búsqueda del get_or_create (no solo en
    # defaults): así una venta del día del evento y una venta de otro día
    # de la MISMA semana, del mismo producto, quedan en filas separadas
    # en vez de mezclarse en una sola fila que arrastra la marca de
    # evento para siempre.
    registro, creado = HistorialVentas.objects.get_or_create(
        producto=producto,
        fecha_inicio=fecha_inicio,
        fecha_comercial=comercial,
        defaults={'fecha_fin': fecha_fin, 'cantidad': cantidad},
    )
    if not creado:
        registro.cantidad += cantidad
        registro.save(update_fields=['cantidad'])