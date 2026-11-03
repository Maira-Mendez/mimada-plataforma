from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from usuarios.decorators import admin_requerido
from .models import ItemInventario, CategoriaInventario
from .forms import ItemInventarioForm, CategoriaInventarioForm


@admin_requerido
def inventario_dashboard(request):
    items = ItemInventario.objects.select_related('categoria').all()

    query = request.GET.get('q')
    if query:
        items = items.filter(
            Q(nombre__icontains=query) | Q(categoria__nombre__icontains=query)
        )

    categoria_id = request.GET.get('categoria')
    if categoria_id:
        items = items.filter(categoria_id=categoria_id)

    total_valor = sum((item.precio or 0) * item.stock_actual for item in items)

    context = {
        'items': items,
        'categorias': CategoriaInventario.objects.all(),
        'total_valor': total_valor,
        'query': query or '',
    }
    return render(request, 'inventario/dashboard.html', context)


@admin_requerido
def item_crear(request):
    if request.method == 'POST':
        form = ItemInventarioForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Producto agregado correctamente.')
            return redirect('inventario:dashboard')
    else:
        form = ItemInventarioForm()
    return render(request, 'inventario/item_form.html', {'form': form, 'titulo': 'Agregar Producto'})


@admin_requerido
def item_editar(request, pk):
    item = get_object_or_404(ItemInventario, pk=pk)
    if request.method == 'POST':
        form = ItemInventarioForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Producto actualizado correctamente.')
            return redirect('inventario:dashboard')
    else:
        form = ItemInventarioForm(instance=item)
    return render(request, 'inventario/item_form.html', {'form': form, 'titulo': 'Editar Producto'})


@admin_requerido
def item_eliminar(request, pk):
    item = get_object_or_404(ItemInventario, pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Producto eliminado.')
        return redirect('inventario:dashboard')
    return render(request, 'inventario/item_confirmar_eliminar.html', {'item': item})


@admin_requerido
def categoria_crear(request):
    if request.method == 'POST':
        form = CategoriaInventarioForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoría creada correctamente.')
            return redirect('inventario:dashboard')
    else:
        form = CategoriaInventarioForm()
    return render(request, 'inventario/categoria_form.html', {'form': form})

@admin_requerido
def categoria_editar(request, pk):
    categoria = get_object_or_404(CategoriaInventario, pk=pk)
    if request.method == 'POST':
        form = CategoriaInventarioForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoría actualizada correctamente.')
            return redirect('inventario:dashboard')
    else:
        form = CategoriaInventarioForm(instance=categoria)
    return render(request, 'inventario/categoria_form.html', {'form': form})


@admin_requerido
def categoria_eliminar(request, pk):
    categoria = get_object_or_404(CategoriaInventario, pk=pk)
    if request.method == 'POST':
        if categoria.items.exists():
            messages.error(request, 'No se puede eliminar: tiene productos asociados. Muévelos o bórralos primero.')
            return redirect('inventario:dashboard')
        categoria.delete()
        messages.success(request, 'Categoría eliminada.')
        return redirect('inventario:dashboard')
    return render(request, 'inventario/categoria_confirmar_eliminar.html', {'categoria': categoria})