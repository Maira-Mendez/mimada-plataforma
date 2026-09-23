from urllib.parse import quote
from datetime import date
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from inventario.models import ItemInventario, CategoriaInventario
from catalogo.models import Producto
from .forms import PedidoForm
from .models import Pedido, DetallePedido, ConfiguracionRamo
from .utils import calcular_pliegos, es_modo_manual
from . import carrito as carrito_helper
from decimal import Decimal


class StockInsuficiente(Exception):
    """Señal interna para abortar la transacción cuando no alcanza el papel."""
    pass


@login_required(login_url="usuarios:login")
def inicio(request):
    pedidos = request.user.pedidos.all().order_by("-fecha_creacion")
    return render(request, "pedidos/inicio.html", {"pedidos": pedidos})


PUNTOS_RECOGIDA = {
    "SOACHA": {
        "direccion": "Cl 15 #2B-11, Soacha",
        "horario": "Lun-Vie: 8:00 AM - 7:00 PM · Dom y festivos: 9:00 AM - 6:00 PM",
    },
    "PLAZA": {
        "direccion": "Centro Comercial Plaza de las Américas",
        "horario": "Lunes, martes y jueves",
    },
}

VALOR_DOMICILIO = 10000


def calcular_domicilio(tipo_entrega):
    if tipo_entrega == "DOMICILIO":
        return VALOR_DOMICILIO
    return 0


def crear_detalle(request):

    def items_de(nombre_categoria):
        try:
            categoria = CategoriaInventario.objects.get(nombre=nombre_categoria)
            return ItemInventario.objects.filter(categoria=categoria, stock_actual__gt=0)
        except CategoriaInventario.DoesNotExist:
            return ItemInventario.objects.none()

    rosas = items_de("Rosas")
    girasoles = items_de("girasoles")
    cintas = items_de("Cintas")
    papeles = items_de("papel coreano")
    adicionales = items_de("adicciones")
    peluches = items_de("Peluches")

    detalle_inicial = request.session.get("detalle_personalizado")

    return render(
        request,
        "pedidos/crear_detalle.html",
        {
            "rosas": rosas,
            "girasoles": girasoles,
            "cintas": cintas,
            "papeles": papeles,
            "adicionales": adicionales,
            "peluches": peluches,
            "precio_base_rosa": rosas.first().precio if rosas.exists() else 0,
            "precio_base_girasol": girasoles.first().precio if girasoles.exists() else 0,
            "detalle_inicial": detalle_inicial,
        },
    )


def nuevo_detalle(request):
    request.session.pop("detalle_personalizado", None)
    return redirect("pedidos:crear_detalle")


def guardar_detalle_personalizado(request):

    if request.method != "POST":
        return redirect("pedidos:crear_detalle")

    cantidad_rosas = int(request.POST.get("cantidad_rosas", 0))
    cantidad_girasoles = int(request.POST.get("cantidad_girasoles", 0))
    cantidad_lirios = int(request.POST.get("cantidad_lirios", 0))

    total_flores = cantidad_rosas + cantidad_girasoles + cantidad_lirios

    papel_id = request.POST.get("papel_id") or None
    tipo_armado = request.POST.get("tipo_armado") or None
    pliegos_manual_raw = request.POST.get("pliegos_manual")
    pliegos_manual = int(pliegos_manual_raw) if pliegos_manual_raw else None

    try:
        pliegos_utilizados = calcular_pliegos(total_flores, pliegos_manual)
    except ValidationError as e:
        messages.error(request, e.message)
        return redirect("pedidos:crear_detalle")

    if not es_modo_manual(total_flores) and not papel_id:
        messages.error(request, "Selecciona un papel decorativo para continuar.")
        return redirect("pedidos:crear_detalle")

    detalle = {
        "cantidad_rosas": cantidad_rosas,
        "cantidad_girasoles": cantidad_girasoles,
        "cantidad_lirios": cantidad_lirios,
        "color_lirio_ids": request.POST.getlist("color_lirio_ids"),
        "color_cinta_ids": request.POST.getlist("color_cinta_ids"),
        "papel_id": papel_id,
        "adicionales_ids": request.POST.getlist("adicionales_ids"),
        "peluche_id": request.POST.get("peluche_id") or None,
        "precio_rosas": float(request.POST.get("precio_rosas", 0)),
        "precio_girasoles": float(request.POST.get("precio_girasoles", 0)),
        "precio_lirios": float(request.POST.get("precio_lirios", 0)),
        "precio_color_lirio": float(request.POST.get("precio_color_lirio", 0)),
        "precio_cinta": float(request.POST.get("precio_cinta", 0)),
        "precio_papel": float(request.POST.get("precio_papel", 0)),
        "precio_adicionales": float(request.POST.get("precio_adicionales", 0)),
        "precio_peluche": float(request.POST.get("precio_peluche", 0)),
        "tipo_armado": tipo_armado,
        "pliegos_utilizados": pliegos_utilizados,
    }

    detalle["total"] = (
            detalle["precio_rosas"]
            + detalle["precio_girasoles"]
            + detalle["precio_lirios"]
            + detalle["precio_cinta"]
            + detalle["precio_color_lirio"]
            + detalle["precio_papel"]
            + detalle["precio_adicionales"]
            + detalle["precio_peluche"]
    )

    request.session.pop("detalle_personalizado", None)
    request.session.pop("producto", None)

    if not request.user.is_authenticated:
        login_url = reverse("usuarios:login")
        siguiente = reverse("pedidos:crear_detalle")
        return redirect(f"{login_url}?next={siguiente}")

    carrito_helper.agregar_personalizado(request, detalle)
    messages.success(request, "Tu ramo personalizado se añadió al carrito.")
    return redirect("pedidos:ver_carrito")


@login_required(login_url="usuarios:login")
def crear_pedido_personalizado(request):

    detalle = request.session.get("detalle_personalizado")

    if not detalle:
        return redirect("pedidos:crear_detalle")

    if request.method == "POST":

        form = PedidoForm(request.POST)

        if form.is_valid():

            datos = form.cleaned_data.copy()
            datos["fecha_entrega"] = datos["fecha_entrega"].isoformat()

            request.session["pedido"] = datos
            request.session["items_pedido"] = [{
                "tipo": "personalizado",
                "detalle": detalle,
            }]
            request.session.pop("producto", None)
            request.session.pop("detalle_personalizado", None)
            return redirect("pedidos:resumen")

    else:
        form = PedidoForm()

    return render(
        request,
        "pedidos/crear_pedido.html",
        {
            "form": form,
            "producto": "Ramo personalizado",
            "es_personalizado": True,
        },
    )


@login_required(login_url="usuarios:login")
def crear_pedido(request, producto_id):

    producto = get_object_or_404(Producto, pk=producto_id)

    cantidad_raw = request.POST.get("cantidad") or request.GET.get("cantidad", 1)
    try:
        cantidad = int(cantidad_raw)
    except (TypeError, ValueError):
        cantidad = 1
    if cantidad < 1:
        cantidad = 1

    if request.method == "POST":

        form = PedidoForm(request.POST)

        if form.is_valid():

            datos = form.cleaned_data.copy()

            datos["fecha_entrega"] = datos["fecha_entrega"].isoformat()

            request.session["pedido"] = datos
            request.session["items_pedido"] = [{
                "tipo": "producto",
                "producto_id": producto.id,
                "cantidad": cantidad,
            }]
            request.session.pop("producto", None)
            request.session.pop("cantidad_producto", None)
            return redirect("pedidos:resumen")

    else:
        form = PedidoForm()

    return render(
        request,
        "pedidos/crear_pedido.html",
        {
            "form": form,
            "producto": producto,
            "cantidad": cantidad,
        },
    )


def _resumen_items(items_pedido):
    """Convierte session['items_pedido'] en filas listas para mostrar en resumen/formulario."""
    resumen_items = []
    for item in items_pedido:
        if item["tipo"] == "producto":
            producto = get_object_or_404(Producto, pk=item["producto_id"])
            cantidad = item.get("cantidad", 1)
            precio_unitario = producto.precio
            subtotal = precio_unitario * cantidad
            resumen_items.append({
                "nombre": producto.nombre,
                "cantidad": cantidad,
                "precio_unitario": precio_unitario,
                "subtotal": subtotal,
            })
        else:
            detalle = item["detalle"]
            subtotal = Decimal(str(detalle["total"]))
            resumen_items.append({
                "nombre": "Ramo personalizado",
                "cantidad": 1,
                "precio_unitario": subtotal,
                "subtotal": subtotal,
            })
    return resumen_items


@login_required(login_url="usuarios:login")
def resumen(request):
    datos = request.session.get("pedido")
    items_pedido = request.session.get("items_pedido")

    if not datos or not items_pedido:
        return redirect("pedidos:inicio")

    items = _resumen_items(items_pedido)
    subtotal_productos = sum((i["subtotal"] for i in items), Decimal("0"))

    tipo_entrega = datos.get("tipo_entrega")
    tipo_entrega_display = dict(Pedido.TIPO_ENTREGA).get(tipo_entrega, tipo_entrega)
    valor_domicilio = calcular_domicilio(tipo_entrega)
    total = subtotal_productos + valor_domicilio

    return render(request, "pedidos/resumen.html", {
        "datos": datos,
        "items": items,
        "subtotal_productos": subtotal_productos,
        "tipo_entrega_display": tipo_entrega_display,
        "es_domicilio": tipo_entrega == "DOMICILIO",
        "punto_recogida": PUNTOS_RECOGIDA.get(tipo_entrega),
        "valor_domicilio": valor_domicilio,
        "total": total,
    })


@login_required(login_url="usuarios:login")
def confirmar_pedido(request):
    datos = request.session.get("pedido")
    items_pedido = request.session.get("items_pedido")

    if not datos or not items_pedido:
        return redirect("pedidos:inicio")

    # Solo se confirma por POST, con el checkbox de términos marcado.
    if request.method != "POST" or not request.POST.get("acepta_terminos"):
        messages.error(request, "Debes aceptar los términos y condiciones para confirmar el pedido.")
        return redirect("pedidos:resumen")

    valor_domicilio = calcular_domicilio(datos["tipo_entrega"])

    try:
        with transaction.atomic():
            # 1) Validar y descontar stock de papel para cada ramo personalizado
            for item in items_pedido:
                if item["tipo"] == "personalizado" and item["detalle"].get("papel_id"):
                    detalle_p = item["detalle"]
                    papel_item = ItemInventario.objects.select_for_update().get(pk=detalle_p["papel_id"])
                    pliegos_necesarios = detalle_p["pliegos_utilizados"]
                    total_flores = (
                        detalle_p["cantidad_rosas"] + detalle_p["cantidad_girasoles"] + detalle_p["cantidad_lirios"]
                    )
                    if not es_modo_manual(total_flores) and papel_item.stock_actual < pliegos_necesarios:
                        messages.error(request, "Uno de los papeles seleccionados ya no está disponible.")
                        raise StockInsuficiente()
                    papel_item.stock_actual -= pliegos_necesarios
                    papel_item.save()

            # 2) Calcular totales
            filas = []  # (item, producto_o_None, cantidad, precio_unitario, subtotal)
            subtotal_productos = Decimal("0")
            for item in items_pedido:
                if item["tipo"] == "producto":
                    producto = get_object_or_404(Producto, pk=item["producto_id"])
                    cantidad = item.get("cantidad", 1)
                    precio_unitario = producto.precio
                    subtotal = precio_unitario * cantidad
                else:
                    producto = None
                    cantidad = 1
                    precio_unitario = Decimal(str(item["detalle"]["total"]))
                    subtotal = precio_unitario
                subtotal_productos += subtotal
                filas.append((item, producto, cantidad, precio_unitario, subtotal))

            total = subtotal_productos + valor_domicilio

            # 3) Crear el pedido
            pedido = Pedido.objects.create(
                cliente=request.user,
                tipo_entrega=datos["tipo_entrega"],
                es_regalo=datos["es_regalo"],
                entrega_anonima=datos["entrega_anonima"],
                nombre_destinatario=datos["nombre_destinatario"],
                telefono_destinatario=datos["telefono_destinatario"],
                mensaje=datos["mensaje"],
                direccion=datos["direccion"],
                barrio=datos["barrio"],
                ciudad=datos["ciudad"],
                referencia=datos["referencia"],
                fecha_entrega=date.fromisoformat(datos["fecha_entrega"]),
                hora_entrega=datos["hora_entrega"],
                valor_domicilio=valor_domicilio,
                total=total,
                acepta_terminos=True,
                fecha_aceptacion_terminos=timezone.now(),
            )

            # 4) Crear un DetallePedido por cada ítem (y su ConfiguracionRamo si aplica)
            lineas_mensaje = []
            for item, producto, cantidad, precio_unitario, subtotal in filas:
                es_personalizado = item["tipo"] == "personalizado"

                detalle_obj = DetallePedido.objects.create(
                    pedido=pedido,
                    producto=producto,
                    es_personalizado=es_personalizado,
                    cantidad=cantidad,
                    precio_unitario=precio_unitario,
                    subtotal=subtotal,
                )

                nombre_mostrado = producto.nombre if producto else "Ramo personalizado"
                lineas_mensaje.append(f"- {nombre_mostrado} x{cantidad}: ${subtotal}")

                if es_personalizado:
                    detalle_p = item["detalle"]
                    config = ConfiguracionRamo.objects.create(
                        detalle_pedido=detalle_obj,
                        cantidad_rosas=detalle_p["cantidad_rosas"],
                        cantidad_girasoles=detalle_p["cantidad_girasoles"],
                        cantidad_lirios=detalle_p["cantidad_lirios"],
                        papel_decorativo_id=detalle_p["papel_id"] or None,
                        pliegos_utilizados=detalle_p["pliegos_utilizados"],
                        tipo_armado=detalle_p.get("tipo_armado") or None,
                    )
                    if detalle_p["color_cinta_ids"]:
                        config.color_cinta.set(detalle_p["color_cinta_ids"])
                    if detalle_p["color_lirio_ids"]:
                        config.color_lirio.set(detalle_p["color_lirio_ids"])

                    adicionales_y_peluche = list(detalle_p["adicionales_ids"])
                    if detalle_p.get("peluche_id"):
                        adicionales_y_peluche.append(detalle_p["peluche_id"])
                    if adicionales_y_peluche:
                        config.adicionales.set(adicionales_y_peluche)

            # 5) Recién ahora que el pedido se creó con éxito, limpiar del carrito
            #    los ítems que vinieron de ahí (selección múltiple).
            for item in items_pedido:
                cart_item_id = item.get("cart_item_id")
                if cart_item_id:
                    carrito_helper.eliminar_item(request, cart_item_id)

    except StockInsuficiente:
        return redirect("pedidos:resumen")

    if datos["tipo_entrega"] == "DOMICILIO":
        bloque_entrega = f"""Dirección:
{pedido.direccion}

Barrio:
{pedido.barrio}

Ciudad:
{pedido.ciudad}"""
    else:
        punto = PUNTOS_RECOGIDA.get(pedido.tipo_entrega, {})
        bloque_entrega = f"""Punto de recogida:
{punto.get('direccion', '')}

Horario:
{punto.get('horario', '')}"""

    domicilio_texto = "Gratis" if pedido.valor_domicilio == 0 else f"${pedido.valor_domicilio}"
    productos_texto = "\n".join(lineas_mensaje)

    mensaje = f"""
🌸 *Nuevo pedido Mimada*

Pedido No: {pedido.id}

Productos:
{productos_texto}

Domicilio:
{domicilio_texto}

Total:
${pedido.total}

Tipo de entrega:
{pedido.get_tipo_entrega_display()}

{bloque_entrega}

Fecha:
{pedido.fecha_entrega}

Hora:
{pedido.hora_entrega}

¿Es regalo?
{'Sí' if pedido.es_regalo else 'No'}

Destinatario:
{pedido.nombre_destinatario}

Teléfono:
{pedido.telefono_destinatario}

Mensaje:
{pedido.mensaje}

Muchas gracias.

Quedo atento(a) a la información para realizar el pago.
"""

    telefono = "573238883587"
    url = f"https://wa.me/{telefono}?text={quote(mensaje)}"

    request.session.pop("pedido", None)
    request.session.pop("items_pedido", None)

    return redirect(url)


@login_required(login_url="usuarios:login")
def editar_pedido(request, pedido_id):

    pedido = get_object_or_404(Pedido, pk=pedido_id, cliente=request.user)

    if pedido.estado != "PENDIENTE":
        return redirect("pedidos:inicio")

    if request.method == "POST":
        form = PedidoForm(request.POST, instance=pedido)
        if form.is_valid():
            pedido_editado = form.save(commit=False)
            pedido_editado.valor_domicilio = calcular_domicilio(pedido_editado.tipo_entrega)

            subtotal_productos = sum(
                (d.subtotal for d in pedido_editado.detalles.all()),
                Decimal("0")
            )
            pedido_editado.total = subtotal_productos + pedido_editado.valor_domicilio

            pedido_editado.save()
            return redirect("pedidos:inicio")
    else:
        form = PedidoForm(instance=pedido)

    return render(
        request,
        "pedidos/editar_pedido.html",
        {"form": form, "pedido": pedido},
    )


@login_required(login_url="usuarios:login")
def cancelar_pedido(request, pedido_id):

    pedido = get_object_or_404(Pedido, pk=pedido_id, cliente=request.user)

    if pedido.estado == "PENDIENTE":
        pedido.estado = "CANCELADO"
        pedido.save()

    return redirect("pedidos:inicio")


@login_required(login_url="usuarios:login")
def agregar_al_carrito(request, producto_id):
    if request.method != "POST":
        return redirect("catalogo:detalle_producto", pk=producto_id)

    producto = get_object_or_404(Producto, pk=producto_id)

    cantidad_raw = request.POST.get("cantidad", 1)
    try:
        cantidad = int(cantidad_raw)
    except (TypeError, ValueError):
        cantidad = 1
    if cantidad < 1:
        cantidad = 1

    carrito_helper.agregar_producto(request, producto.id, cantidad)

    messages.success(request, f'"{producto.nombre}" se añadió al carrito.')

    siguiente = request.POST.get("next") or request.META.get("HTTP_REFERER") or "home"
    return redirect(siguiente)


def ver_carrito(request):
    carrito = request.session.get("carrito", [])

    items = []
    total_carrito = Decimal("0")

    for item in carrito:
        if item["tipo"] == "producto":
            producto = Producto.objects.filter(pk=item["producto_id"]).first()
            if not producto:
                continue
            subtotal = producto.precio * item["cantidad"]
            total_carrito += subtotal
            items.append({
                "item_id": item["id"],
                "tipo": "producto",
                "nombre": producto.nombre,
                "imagen": producto.imagen,
                "precio_unitario": producto.precio,
                "cantidad": item["cantidad"],
                "subtotal": subtotal,
                "subtotal_raw": str(subtotal),
            })
        else:
            detalle_pedido = item["detalle"]
            subtotal = Decimal(str(detalle_pedido["total"]))
            total_carrito += subtotal
            items.append({
                "item_id": item["id"],
                "tipo": "personalizado",
                "nombre": "Ramo personalizado",
                "imagen": None,
                "precio_unitario": subtotal,
                "cantidad": 1,
                "subtotal": subtotal,
                "subtotal_raw": str(subtotal),
            })

    return render(request, "pedidos/carrito.html", {
        "items": items,
        "total_carrito": total_carrito,
    })


def eliminar_del_carrito(request, item_id):
    carrito_helper.eliminar_item(request, item_id)
    messages.success(request, "Se eliminó el producto del carrito.")
    return redirect("pedidos:ver_carrito")


def actualizar_cantidad_carrito(request, item_id):
    if request.method == "POST":
        cantidad_raw = request.POST.get("cantidad", 1)
        try:
            cantidad = int(cantidad_raw)
        except (TypeError, ValueError):
            cantidad = 1
        carrito_helper.actualizar_cantidad(request, item_id, cantidad)
    return redirect("pedidos:ver_carrito")


@login_required(login_url="usuarios:login")
def iniciar_pedido_seleccionados(request):
    if request.method != "POST":
        return redirect("pedidos:ver_carrito")

    item_ids = request.POST.getlist("item_ids")
    if not item_ids:
        messages.error(request, "Selecciona al menos un producto para continuar.")
        return redirect("pedidos:ver_carrito")

    carrito = request.session.get("carrito", [])
    seleccionados = [i for i in carrito if i["id"] in item_ids]

    if not seleccionados:
        messages.error(request, "Esos productos ya no están en el carrito.")
        return redirect("pedidos:ver_carrito")

    items_pedido = []
    for item in seleccionados:
        if item["tipo"] == "producto":
            items_pedido.append({
                "tipo": "producto",
                "producto_id": item["producto_id"],
                "cantidad": item.get("cantidad", 1),
                "cart_item_id": item["id"],
            })
        else:
            items_pedido.append({
                "tipo": "personalizado",
                "detalle": item["detalle"],
                "cart_item_id": item["id"],
            })

    # OJO: no se borra nada del carrito aquí. Solo se borra al confirmar el pedido
    # (ver confirmar_pedido), así si el cliente abandona el flujo los productos
    # siguen en su carrito.
    request.session["items_pedido"] = items_pedido
    request.session.modified = True

    return redirect("pedidos:crear_pedido_lote")


@login_required(login_url="usuarios:login")
def crear_pedido_lote(request):
    items_pedido = request.session.get("items_pedido")
    if not items_pedido:
        return redirect("pedidos:ver_carrito")

    if request.method == "POST":
        form = PedidoForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data.copy()
            datos["fecha_entrega"] = datos["fecha_entrega"].isoformat()
            request.session["pedido"] = datos
            return redirect("pedidos:resumen")
    else:
        form = PedidoForm()

    return render(request, "pedidos/crear_pedido.html", {
        "form": form,
        "es_lote": True,
        "items_lote": _resumen_items(items_pedido),
    })