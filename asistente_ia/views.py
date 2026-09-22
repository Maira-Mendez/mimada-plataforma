import json
from datetime import date
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .heuristica import (
    CONTENIDO_ROSAS, CONTENIDO_GIRASOLES, CONTENIDO_LIRIOS,
    alerta_stock_flor_fecha_comercial, alerta_stock_cinta_fecha_comercial,
    alerta_stock_flor_semana_siguiente, serie_semanal_flor_completa,
    serie_anual_evento_agregada, evento_tiene_historial, prediccion_evento_en_anio,
    cargar_historial, cargar_stock_por_categoria,
)
from .fechas_comerciales import proxima_fecha_comercial, secuencia_eventos

FLORES = [
    {'clave': 'rosas', 'nombre_display': 'Rosas', 'mapeo': CONTENIDO_ROSAS},
    {'clave': 'girasoles', 'nombre_display': 'Girasoles', 'mapeo': CONTENIDO_GIRASOLES},
    {'clave': 'lirios', 'nombre_display': 'Lirios', 'mapeo': CONTENIDO_LIRIOS},
]
MAPEOS_FLORES = [f['mapeo'] for f in FLORES]

SEMANAS_A_MOSTRAR = 8


def _linea_de_tiempo_eventos(historial, hoy=None):
    """Los eventos comerciales que SÍ tienen al menos una venta registrada,
    en orden cronológico, cubriendo este año y el que sigue (para nunca
    quedarse sin 'siguiente' al llegar a diciembre)."""
    hoy = hoy or date.today()
    nodos = []
    vistos = set()
    for anio_ref in (hoy.year, hoy.year + 1):
        for fecha, nombre in secuencia_eventos(date(anio_ref, 1, 1)):
            clave = (nombre, fecha.year)
            if clave in vistos:
                continue
            if not evento_tiene_historial(MAPEOS_FLORES, nombre, historial=historial):
                continue
            vistos.add(clave)
            nodos.append({'fecha': fecha, 'nombre': nombre, 'anio': fecha.year})
    nodos.sort(key=lambda n: n['fecha'])
    return nodos


def _idx_default(nodos, hoy):
    """Índice del próximo evento con datos (el que se muestra por defecto)."""
    return next((i for i, n in enumerate(nodos) if n['fecha'] >= hoy), len(nodos) - 1)


def _armar_evento_actual(nodos, idx, historial, hoy):
    """Arma las barras (real + predicha reconstruida) para el nodo `idx`
    de la línea de tiempo. Solo se agrega la barra de predicción si el
    evento sigue siendo futuro, o si es el que ACABA de pasar (el
    inmediatamente anterior al próximo) — para las fechas más antiguas no
    se reconstruye nada, tal como pediste."""
    idx_recien_pasado = _idx_default(nodos, hoy) - 1

    nodo = nodos[idx]
    es_futuro = nodo['fecha'] >= hoy
    mostrar_prediccion = es_futuro or idx == idx_recien_pasado

    flores_evento = []
    for flor in FLORES:
        serie = serie_anual_evento_agregada(flor['mapeo'], nodo['nombre'], historial=historial)
        labels = [str(anio) for anio, _ in serie]
        valores = [float(total) for _, total in serie]
        indice_prediccion = None

        if mostrar_prediccion:
            pred = prediccion_evento_en_anio(flor['mapeo'], nodo['nombre'], nodo['anio'], historial=historial)
            if pred is not None:
                labels.append(f"{nodo['anio']} (est.)")
                valores.append(float(pred))
                indice_prediccion = len(valores) - 1

        if valores:
            flores_evento.append({
                'clave': flor['clave'],
                'nombre_display': flor['nombre_display'],
                'labels': json.dumps(labels),
                'valores': json.dumps(valores),
                'indice_prediccion': indice_prediccion,
            })

    return {
        'nombre': nodo['nombre'],
        'anio': nodo['anio'],
        'fecha': nodo['fecha'],
        'es_futuro': es_futuro,
        'flores': flores_evento,
    }


@login_required
def dashboard(request):
    hoy = date.today()
    historial = cargar_historial()
    stock_por_categoria = cargar_stock_por_categoria()

    # ---------- Fechas especiales, con flechas ----------
    nodos = _linea_de_tiempo_eventos(historial, hoy)
    evento_actual = None
    nav = {'anterior': None, 'siguiente': None}

    if nodos:
        nombre_sel, anio_sel = request.GET.get('evento'), request.GET.get('anio')
        idx = next((i for i, n in enumerate(nodos)
                    if n['nombre'] == nombre_sel and str(n['anio']) == anio_sel), None)
        if idx is None:
            idx = _idx_default(nodos, hoy)
        evento_actual = _armar_evento_actual(nodos, idx, historial, hoy)

        if idx > 0:
            nav['anterior'] = nodos[idx - 1]
        if idx < len(nodos) - 1:
            nav['siguiente'] = nodos[idx + 1]

    # ---------- Alertas de insumos (siempre sobre la PRÓXIMA fecha real) ----------
    fecha_prox, nombre_prox = proxima_fecha_comercial()

    secciones = []
    for flor in FLORES:
        alerta = None
        if nombre_prox:
            alerta = alerta_stock_flor_fecha_comercial(
                flor['clave'], nombre_prox,
                historial=historial, stock_por_categoria=stock_por_categoria,
            )

        semanal = serie_semanal_flor_completa(flor['mapeo'], historial=historial)[-SEMANAS_A_MOSTRAR:]
        labels = [f.strftime('%d %b') for f, _ in semanal]
        valores = [float(total) for _, total in semanal]

        alerta_semanal = alerta_stock_flor_semana_siguiente(
            flor['clave'], historial=historial, stock_por_categoria=stock_por_categoria,
        )
        if alerta_semanal and alerta_semanal.get('necesidad') is not None:
            labels.append('Próx. semana')
            valores.append(float(alerta_semanal['necesidad']))

        secciones.append({
            'clave': flor['clave'],
            'nombre_display': flor['nombre_display'],
            'chart_labels': json.dumps(labels),
            'chart_valores': json.dumps(valores),
            'alerta': alerta,
            'alerta_semanal': alerta_semanal,
        })

    cinta = None
    if nombre_prox:
        cinta = alerta_stock_cinta_fecha_comercial(
            nombre_prox, historial=historial, stock_por_categoria=stock_por_categoria,
        )

    context = {
        'secciones': secciones,
        'cinta': cinta,
        'fecha_proxima': fecha_prox,
        'nombre_fecha_proxima': nombre_prox,
        'evento_actual': evento_actual,
        'nav': nav,
    }
    return render(request, 'asistente_ia/dashboard.html', context)