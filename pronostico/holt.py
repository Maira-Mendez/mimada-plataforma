from decimal import Decimal
from django.db.models.functions import ExtractYear
from django.db.models import Max
from .models import HistorialVentas


def serie_anual_evento(producto, nombre_evento):
    """Devuelve lista de tuplas (año, total) para un producto en una fecha
    comercial específica, ordenadas de más antiguo a más reciente."""
    registros = (
        HistorialVentas.objects
        .filter(producto__iexact=producto, fecha_comercial=nombre_evento)
        .annotate(anio=ExtractYear('fecha_inicio'))
        .values('anio')
        .annotate(total=Max('cantidad'))
        .order_by('anio')
    )
    return [(r['anio'], Decimal(r['total'])) for r in registros]


def holt_pronostico(valores, alpha=Decimal('0.7'), beta=Decimal('0.3'), phi=Decimal('0.8')):
    """
    Método de Holt con tendencia amortiguada.
    valores: lista de totales anuales, ordenados de más antiguo a más reciente.
    Con N=2 se degrada matemáticamente a una recta entre los dos puntos
    (documentado y esperado); con N>=3 los parámetros alpha/beta ya diferencian.
    """
    if len(valores) < 2:
        return None

    L = valores[0]
    T = valores[1] - valores[0]

    for t in range(1, len(valores)):
        Y = valores[t]
        L_prev, T_prev = L, T
        L = alpha * Y + (1 - alpha) * (L_prev + T_prev)
        T = beta * (L - L_prev) + (1 - beta) * T_prev

    pronostico = L + phi * T

    return {
        'nivel': round(L, 2),
        'tendencia': round(T, 2),
        'pronostico': round(max(pronostico, Decimal('0')), 2),
        'n_observaciones': len(valores),
        'degradado_a_lineal': len(valores) == 2,
    }