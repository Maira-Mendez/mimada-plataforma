from decimal import Decimal, InvalidOperation
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.urls import reverse

from pedidos.models import Pedido, DetallePedido
from asistente_ia.models import HistorialVentas
from asistente_ia.fechas_comerciales import es_dia_comercial
from asistente_ia.heuristica import inicio_semana
from inventario.models import ItemInventario, DesglosePedidoFlores, DesgloseFlorItem
from .forms import VentaPresencialForm

Usuario = get_user_model()
USERNAME_MOSTRADOR = 'mostrador'


ESTADO_TABS = [
    ('TODOS', 'Todos'),
    ('PENDIENTE', 'Pendientes'),
    ('EN_PROCESO', 'En Proceso'),
    ('LISTO', 'Listos'),
    ('ENTREGADO', 'Entregados'),
    ('CANCELADO', 'Cancelados'),
]


def _construir_contexto_lista(request):
    """Arma el contexto base del listado (filtros, paginación, detalle) —
    compartido entre lista_pedidos y registrar_venta_presencial, para que
    esta última pueda re-renderizar la misma lista si el formulario falla."""
    pedidos = Pedido.objects.select_related('cliente').prefetch_related('detalles__producto')

    tab_activo = request.GET.get('tab', 'TODOS')
    if tab_activo != 'TODOS':
        pedidos = pedidos.filter(estado=tab_activo)

    query = request.GET.get('q')
    if query:
        pedidos = pedidos.filter(
            Q(cliente__first_name__icontains=query) |
            Q(cliente__email__icontains=query) |
            Q(nombre_destinatario__icontains=query) |
            Q(id__icontains=query)
        )

    pedidos = pedidos.order_by('-fecha_creacion')

    paginator = Paginator(pedidos, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    pedido_detalle = None
    ver_id = request.GET.get('ver')
    if ver_id:
        pedido_detalle = get_object_or_404(
            Pedido.objects.select_related('cliente').prefetch_related(
                'detalles__producto', 'detalles__configuracion'
            ),
            pk=ver_id
        )

    return {
        'page_obj': page_obj,
        'tabs': ESTADO_TABS,
        'tab_activo': tab_activo,
        'query': query or '',
        'total_pedidos': paginator.count,
        'pedido_detalle': pedido_detalle,
    }


def _items_flores():
    """Devuelve los items de Inventario agrupados por categoría de flor.
    Reutilizado por desglosar_flores y registrar_venta_presencial (ambos
    piden el mismo desglose de rosas/girasoles/lirios)."""
    items_rosas = ItemInventario.objects.filter(categoria__nombre__iexact='rosas').order_by('nombre')
    items_girasoles = ItemInventario.objects.filter(categoria__nombre__iexact='girasoles').order_by('nombre')
    items_lirios = ItemInventario.objects.filter(categoria__nombre__iexact='lirios').order_by('nombre')
    return items_rosas, items_girasoles, items_lirios


def _leer_movimientos_flores(request):
    """Lee del POST las cantidades de rosas (filas dinámicas color+cantidad)
    y de girasoles/lirios (un campo por item) y devuelve un dict
    {item_id: cantidad_acumulada}. Reutilizado por desglosar_flores y
    registrar_venta_presencial."""
    _, items_girasoles, items_lirios = _items_flores()
    movimientos = {}

    ids_rosas = request.POST.getlist('rosa_item')
    cantidades_rosas = request.POST.getlist('rosa_cantidad')
    for item_id, cantidad_str in zip(ids_rosas, cantidades_rosas):
        cantidad = _decimal_o_none(cantidad_str)
        if item_id and cantidad:
            # Por si acaso llega con separador de miles (localización es-co)
            item_id_int = int(str(item_id).replace('.', '').replace(',', ''))
            movimientos[item_id_int] = movimientos.get(item_id_int, Decimal('0')) + cantidad

    for item in list(items_girasoles) + list(items_lirios):
        cantidad = _decimal_o_none(request.POST.get(f'item_{item.id}'))
        if cantidad:
            movimientos[item.id] = movimientos.get(item.id, Decimal('0')) + cantidad

    return movimientos


def _descontar_inventario_flores(pedido, movimientos):
    """Crea el DesglosePedidoFlores y descuenta stock_actual de cada item.
    Debe llamarse dentro de una transaction.atomic(). Si movimientos está
    vacío, no hace nada (el desglose de flores es opcional en venta de
    vitrina: no toda venta de mostrador es de flores)."""
    if not movimientos:
        return
    desglose = DesglosePedidoFlores.objects.create(pedido_id=pedido.pk)
    for item_id, cantidad in movimientos.items():
        item = ItemInventario.objects.select_for_update().get(pk=item_id)
        item.stock_actual = max(Decimal('0'), item.stock_actual - cantidad)
        item.save(update_fields=['stock_actual', 'fecha_actualizacion'])
        DesgloseFlorItem.objects.create(desglose=desglose, item=item, cantidad=cantidad)


@login_required
def lista_pedidos(request):
    context = _construir_contexto_lista(request)
    context['mostrar_form_presencial'] = request.GET.get('nueva') == '1'
    context['form_presencial'] = VentaPresencialForm()
    if context['mostrar_form_presencial']:
        items_rosas, items_girasoles, items_lirios = _items_flores()
        context['items_rosas'] = items_rosas
        context['items_girasoles'] = items_girasoles
        context['items_lirios'] = items_lirios
    return render(request, 'pedidosadmin/lista.html', context)


@login_required
def accion_pedido(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    if request.method == 'POST':
        accion = request.POST.get('accion')
        next_url = request.POST.get('next') or reverse('pedidosadmin:dashboard')

        # 'marcar_listo' ya no guarda de una: primero pide el desglose de
        # flores (por color) para poder descontar el inventario.
        if accion == 'marcar_listo':
            url = reverse('pedidosadmin:desglosar_flores', args=[pedido.pk])
            return redirect(f'{url}?next={next_url}')

        transiciones = {
            'aprobar': 'EN_PROCESO',
            'entregar': 'ENTREGADO',
            'cancelar': 'CANCELADO',
        }
        if accion in transiciones:
            pedido.estado = transiciones[accion]
            pedido.save()
            messages.success(request, f'Pedido #{pedido.id} actualizado.')

        return redirect(next_url)
    return redirect('pedidosadmin:dashboard')


def _decimal_o_none(valor):
    if not valor:
        return None
    try:
        d = Decimal(str(valor).strip())
    except InvalidOperation:
        return None
    return d if d > 0 else None


@login_required
def desglosar_flores(request, pk):
    """Formulario que aparece al marcar un pedido como LISTO: pide cuántas
    rosas de cada color, girasoles y lirios se van a usar, descuenta eso
    del inventario y recién ahí guarda el pedido como LISTO. Aplica igual
    para pedidos del ecommerce y de venta presencial — ambos son el mismo
    modelo Pedido."""
    pedido = get_object_or_404(Pedido, pk=pk)
    next_url = request.GET.get('next') or request.POST.get('next') or reverse('pedidosadmin:dashboard')

    if DesglosePedidoFlores.objects.filter(pedido_id=pedido.pk).exists():
        messages.info(request, f'El pedido #{pedido.id} ya tenía su desglose de flores registrado.')
        return redirect(next_url)

    items_rosas, items_girasoles, items_lirios = _items_flores()

    if request.method == 'POST':
        movimientos = _leer_movimientos_flores(request)

        if not movimientos:
            messages.error(request, 'Ingresa al menos una cantidad para poder descontar del inventario.')
        else:
            with transaction.atomic():
                _descontar_inventario_flores(pedido, movimientos)
                pedido.estado = 'LISTO'
                pedido.save()

            messages.success(request,
                             f'Pedido #{pedido.id} marcado como listo. Se descontaron las flores del inventario.')
            return redirect(next_url)
    return render(request, 'pedidosadmin/desglose_flores.html', {
        'pedido': pedido,
        'items_rosas': items_rosas,
        'items_girasoles': items_girasoles,
        'items_lirios': items_lirios,
        'next': next_url,
    })

# Se mantiene por si acaso, como página completa alternativa
@login_required
def detalle_pedido(request, pk):

    pedido = get_object_or_404(
        Pedido.objects.select_related('cliente').prefetch_related(
            'detalles__producto', 'detalles__configuracion'
        ),
        pk=pk
    )
    return render(request, 'pedidosadmin/detalle.html', {'pedido': pedido})


def obtener_cliente_mostrador():
    """Cuenta genérica usada para TODAS las ventas presenciales, para no
    tener que crear una cuenta real por cada cliente de mostrador."""
    cliente, _creado = Usuario.objects.get_or_create(
        username=USERNAME_MOSTRADOR,
        defaults={
            'email': 'mostrador@mimada.local',
            'first_name': 'Venta',
            'last_name': 'Mostrador',
            'es_cliente': False,
        },
    )
    return cliente





def registrar_en_historial(nombre_producto, cantidad, fecha_venta):
    """Suma esta venta a la semana correspondiente de HistorialVentas,
    para que el Asistente IA la vea en la próxima predicción."""
    fecha_inicio = inicio_semana(fecha_venta)
    fecha_fin = fecha_inicio + timedelta(days=7)
    # Día exacto de la venta contra el día exacto del evento — no el rango
    # completo de la semana. Así una venta de un día cualquiera de la
    # semana no se contamina solo porque esa semana también contiene un
    # evento comercial en otro día.
    fecha_comercial = es_dia_comercial(fecha_venta)

    registro, creado = HistorialVentas.objects.get_or_create(
        producto=nombre_producto,
        fecha_inicio=fecha_inicio,
        defaults={
            'fecha_fin': fecha_fin,
            'cantidad': cantidad,
            'fecha_comercial': fecha_comercial,
        },
    )
    if not creado:
        registro.cantidad += cantidad
        if not registro.fecha_comercial and fecha_comercial:
            registro.fecha_comercial = fecha_comercial
        registro.save()

    return registro


@login_required
def registrar_venta_presencial(request):
    """Procesa el formulario del panel de 'Venta de vitrina'. Si es válido,
    crea el Pedido + DetallePedido, suma a HistorialVentas y — si se
    llenaron cantidades de rosas/girasoles/lirios — descuenta esas flores
    del inventario (igual que al marcar un pedido como LISTO). El desglose
    de flores es opcional porque no toda venta de mostrador es de flores.
    Si el formulario NO es válido, vuelve a mostrar la lista con el panel
    abierto y los errores visibles, en vez de una página aparte."""
    if request.method != 'POST':
        return redirect('pedidosadmin:dashboard')

    form = VentaPresencialForm(request.POST)
    if form.is_valid():
        datos = form.cleaned_data
        producto = datos.get('producto')
        cantidad = datos['cantidad']
        precio_unitario = datos['precio_unitario']
        subtotal = precio_unitario * cantidad

        movimientos = _leer_movimientos_flores(request)

        cliente_mostrador = obtener_cliente_mostrador()

        with transaction.atomic():
            pedido = Pedido.objects.create(
                cliente=cliente_mostrador,
                estado='ENTREGADO',
                tipo_entrega='MOSTRADOR',
                total=subtotal,
                nombre_destinatario=datos.get('nombre_cliente', ''),
                telefono_destinatario=datos.get('telefono_cliente', ''),
                fecha_entrega=datos['fecha_venta'],
            )
            DetallePedido.objects.create(
                pedido=pedido,
                producto=producto,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                subtotal=subtotal,
            )

            _descontar_inventario_flores(pedido, movimientos)

        nombre_historial = form.nombre_para_historial()
        registrar_en_historial(nombre_historial, cantidad, datos['fecha_venta'])

        if movimientos:
            messages.success(
                request,
                f'Venta de vitrina registrada (Pedido #{pedido.id}), sumada al historial del Asistente IA '
                f'y se descontaron las flores del inventario.',
            )
        else:
            messages.success(
                request,
                f'Venta de vitrina registrada (Pedido #{pedido.id}) y sumada al historial del Asistente IA.',
            )
        next_url = request.POST.get('next') or 'pedidosadmin:dashboard'
        if next_url.startswith('?'):
            return redirect(f"/pedidosadmin/{next_url}")
        return redirect(next_url)

    # formulario inválido: reconstruimos la lista y mostramos el panel con errores
    context = _construir_contexto_lista(request)
    context['mostrar_form_presencial'] = True
    context['form_presencial'] = form
    items_rosas, items_girasoles, items_lirios = _items_flores()
    context['items_rosas'] = items_rosas
    context['items_girasoles'] = items_girasoles
    context['items_lirios'] = items_lirios
    return render(request, 'pedidosadmin/lista.html', context)


def reverse_lista(request):
    from django.urls import reverse
    return reverse('pedidosadmin:dashboard')