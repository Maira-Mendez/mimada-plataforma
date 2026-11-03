from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from .models import Producto, Categoria, ItemCarrusel
from .forms import ProductoForm, ItemCarruselForm
from inventario.models import ItemInventario, CategoriaInventario
from .models import Producto, Categoria, ItemCarrusel, ProductoDelMes
from .forms import ProductoForm, ItemCarruselForm, ProductoDelMesForm
from usuarios.decorators import admin_requerido

def inicio(request):
    productos_destacados = Producto.objects.all()
    categorias = Categoria.objects.all()
    items_carrusel = ItemCarrusel.objects.filter(activo=True).select_related('producto')
    destacados_mes = ProductoDelMes.objects.filter(activo=True).select_related('producto')

    def items_de(nombre_categoria):
        try:
            cat = CategoriaInventario.objects.get(nombre=nombre_categoria)
            return ItemInventario.objects.filter(categoria=cat, stock_actual__gt=0)
        except CategoriaInventario.DoesNotExist:
            return ItemInventario.objects.none()

    cintas = items_de('Cintas')
    papeles = items_de('papel coreano')
    adicionales = items_de('adicciones')
    peluches = items_de('Peluches')

    detalle_inicial = request.session.get('detalle_personalizado')

    return render(request, 'catalogo/inicio.html', {
        'productos_destacados': productos_destacados,
        'categorias': categorias,
        'items_carrusel': items_carrusel,
        'destacados_mes': destacados_mes,
        'cintas': cintas,
        'papeles': papeles,
        'adicionales': adicionales,
        'peluches': peluches,
        'detalle_inicial': detalle_inicial,
    })

def lista_productos(request):
        productos = Producto.objects.all()
        categorias = Categoria.objects.all()
        return render(request, 'catalogo/lista.html', {
            'productos': productos,
            'categorias': categorias,
        })

def detalle_producto(request, pk):
        producto = get_object_or_404(Producto, pk=pk)
        return render(request, 'catalogo/detalle_producto.html', {
            'producto': producto,
        })

@admin_requerido
def crear_producto(request):

    if not request.user.es_admin:
        raise PermissionDenied

    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Producto creado correctamente.')
            return redirect('catalogo:admin_dashboard')
    else:
        form = ProductoForm()

    return render(request, 'catalogo/crear_producto.html', {'form': form})

@admin_requerido
def eliminar_producto(request, pk):
    if not request.user.es_admin:
        raise PermissionDenied

    producto = Producto.objects.get(pk=pk)

    producto.delete()

    messages.success(request, "Producto eliminado correctamente.")

    return redirect('catalogo:admin_dashboard')

@admin_requerido
def admin_dashboard(request):
    if not request.user.es_admin:
        raise PermissionDenied

    productos = Producto.objects.select_related('categoria').all()

    context = {
        'productos': productos,
        'total_productos': productos.count(),
        'productos_disponibles': productos.filter(disponible=True).count(),
        'productos_destacados': productos.filter(destacado=True).count(),
    }

    return render(request, 'catalogoadmin/dashboard.html', context)
@admin_requerido
def editar_producto(request, pk):
    if not request.user.es_admin:
        raise PermissionDenied

    producto = Producto.objects.get(pk=pk)

    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES, instance=producto)

        if form.is_valid():
            form.save()
            messages.success(request, "Producto actualizado correctamente.")
            return redirect('catalogo:admin_dashboard')

    else:
        form = ProductoForm(instance=producto)

    return render(
        request,
        "catalogo/crear_producto.html",
        {
            "form": form,
            "editar": True
        }
    )

@admin_requerido
def actualizar_listas(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        try:
            nuevo_valor = int(request.POST.get('unidades_listas', 0))
            producto.unidades_listas = max(0, nuevo_valor)
            producto.save()
            messages.success(request, f'"{producto.nombre}" actualizado.')
        except (ValueError, TypeError):
            messages.error(request, 'Valor inválido.')

    return redirect('catalogo:admin_dashboard')

@admin_requerido
def carrusel_dashboard(request):
    if not request.user.es_admin:
        raise PermissionDenied

    items = ItemCarrusel.objects.select_related('producto').all()

    return render(request, 'catalogoadmin/carrusel_dashboard.html', {
        'items': items,
    })


@admin_requerido
def crear_item_carrusel(request):
    if not request.user.es_admin:
        raise PermissionDenied

    if request.method == 'POST':
        form = ItemCarruselForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Item agregado al carrusel.')
            return redirect('catalogo:carrusel_dashboard')
    else:
        form = ItemCarruselForm()

    return render(request, 'catalogo/crear_item_carrusel.html', {
        'form': form,
        'item': None,
    })


@admin_requerido
def editar_item_carrusel(request, pk):
    if not request.user.es_admin:
        raise PermissionDenied

    item = get_object_or_404(ItemCarrusel, pk=pk)

    if request.method == 'POST':
        form = ItemCarruselForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Item del carrusel actualizado.')
            return redirect('catalogo:carrusel_dashboard')
    else:
        form = ItemCarruselForm(instance=item)

    return render(request, 'catalogo/crear_item_carrusel.html', {
        'form': form,
        'editar': True,
        'item': item,
    })
@admin_requerido
def eliminar_item_carrusel(request, pk):
    if not request.user.es_admin:
        raise PermissionDenied

    item = get_object_or_404(ItemCarrusel, pk=pk)
    item.delete()
    messages.success(request, "Item del carrusel eliminado.")
    return redirect('catalogo:carrusel_dashboard')
def nosotros(request):
    return render(request, 'catalogo/nosotros.html')

@admin_requerido
def destacados_mes_dashboard(request):
    if not request.user.es_admin:
        raise PermissionDenied

    items = ProductoDelMes.objects.select_related('producto').all()

    return render(request, 'catalogoadmin/destacados_mes_dashboard.html', {
        'items': items,
    })


@admin_requerido
def crear_producto_del_mes(request):
    if not request.user.es_admin:
        raise PermissionDenied

    if request.method == 'POST':
        form = ProductoDelMesForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Producto del mes agregado.')
            return redirect('catalogo:destacados_mes_dashboard')
    else:
        form = ProductoDelMesForm()

    return render(request, 'catalogo/crear_producto_del_mes.html', {
        'form': form,
        'item': None,
    })


@admin_requerido
def editar_producto_del_mes(request, pk):
    if not request.user.es_admin:
        raise PermissionDenied

    item = get_object_or_404(ProductoDelMes, pk=pk)

    if request.method == 'POST':
        form = ProductoDelMesForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Producto del mes actualizado.')
            return redirect('catalogo:destacados_mes_dashboard')
    else:
        form = ProductoDelMesForm(instance=item)

    return render(request, 'catalogo/crear_producto_del_mes.html', {
        'form': form,
        'editar': True,
        'item': item,
    })



@admin_requerido
def eliminar_producto_del_mes(request, pk):
    if not request.user.es_admin:
        raise PermissionDenied

    item = ProductoDelMes.objects.filter(pk=pk).first()
    if item:
        item.delete()
        messages.success(request, "Producto del mes eliminado.")
    else:
        messages.info(request, "Ese producto del mes ya había sido eliminado.")

    return redirect('catalogo:destacados_mes_dashboard')