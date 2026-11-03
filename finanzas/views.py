from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone
from pedidos.models import Pedido
from .models import Abono
from .forms import AbonoForm
from usuarios.decorators import admin_requerido

@admin_requerido
def dashboard_view(request):
    pedidos = Pedido.objects.select_related('cliente').exclude(
        estado='CANCELADO'
    ).annotate(total_abonado=Sum('abonos__monto')).prefetch_related('detalles__producto')

    query = request.GET.get('q', '').strip()
    hoy = timezone.now()

    clientes = []
    total_por_cobrar = 0
    clientes_con_deuda = 0

    for pedido in pedidos:
        abonado = pedido.total_abonado or 0
        saldo = pedido.total - abonado

        if saldo <= 0:
            continue  # ya está pagado, no es una deuda

        nombre_cliente = pedido.cliente.get_full_name() or pedido.cliente.username
        if query and query.lower() not in nombre_cliente.lower():
            continue

        clientes_con_deuda += 1
        total_por_cobrar += saldo

        estado = 'AL_DIA'
        fecha_info = 'Sin fecha de entrega programada'
        if pedido.fecha_entrega:
            dias_restantes = (pedido.fecha_entrega - hoy.date()).days
            if dias_restantes < 0:
                estado = 'VENCIDO'
                fecha_info = f"Venció el {pedido.fecha_entrega.strftime('%d/%m/%Y')}"
            elif dias_restantes <= 3:
                estado = 'PROXIMO'
                fecha_info = f"Vence en {dias_restantes} día(s) ({pedido.fecha_entrega.strftime('%d %b')})"
            else:
                fecha_info = f"Entrega: {pedido.fecha_entrega.strftime('%d de %B')}"

        productos = ', '.join(d.producto.nombre for d in pedido.detalles.all() if d.producto_id) or 'Ramo personalizado'

        clientes.append({
            'pedido_id': pedido.id,
            'nombre': nombre_cliente,
            'detalle': productos,
            'estado': estado,
            'valor_total': pedido.total,
            'abonado': abonado,
            'saldo': saldo,
            'fecha_info': fecha_info,
        })

    pagos_del_mes = Abono.objects.filter(
        fecha_abono__year=hoy.year, fecha_abono__month=hoy.month
    ).aggregate(total=Sum('monto'))['total'] or 0

    context = {
        'clientes': clientes,
        'total_por_cobrar': total_por_cobrar,
        'clientes_con_deuda': clientes_con_deuda,
        'pagos_del_mes': pagos_del_mes,
        'query': query,
    }
    return render(request, 'finanzas/dashboard.html', context)


@admin_requerido
def registrar_abono(request, pedido_id=None):
    initial = {}
    if pedido_id:
        pedido = get_object_or_404(Pedido, pk=pedido_id)
        initial['pedido'] = pedido

    if request.method == 'POST':
        form = AbonoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Abono registrado correctamente.')
            return redirect('finanzas:dashboard')
    else:
        form = AbonoForm(initial=initial)

    return render(request, 'finanzas/abono_form.html', {'form': form})