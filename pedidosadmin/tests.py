from decimal import Decimal
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from pedidos.models import Pedido
from catalogo.models import Categoria, Producto
from inventario.models import CategoriaInventario, ItemInventario

Usuario = get_user_model()


def crear_usuario(username='admin1', email='admin1@mimada.com', password='clave12345'):
    return Usuario.objects.create_user(username=username, email=email, password=password)


def crear_cliente(username='cliente1', email='cliente1@mimada.com', first_name='Lucia'):
    return Usuario.objects.create_user(
        username=username, email=email, password='clave12345',
        first_name=first_name, telefono='3001234567',
    )


def crear_pedido(cliente, estado='PENDIENTE', total='90000.00', **extra):
    datos = {
        'cliente': cliente,
        'estado': estado,
        'total': Decimal(total),
    }
    datos.update(extra)
    return Pedido.objects.create(**datos)


class ListaPedidosViewTests(TestCase):
    """Pruebas de front para pedidosadmin:dashboard (lista_pedidos)."""

    def setUp(self):
        self.admin = crear_usuario()
        self.client.force_login(self.admin)
        self.url = reverse('pedidosadmin:dashboard')

    def test_requiere_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)

    def test_sin_pedidos_muestra_mensaje_vacio(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No hay pedidos todavía.')

    def test_lista_pedidos_existentes(self):
        cliente = crear_cliente()
        pedido = crear_pedido(cliente, estado='PENDIENTE')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'#MD-{pedido.id}')
        self.assertContains(response, 'Lucia')

    def test_tab_todos_por_defecto(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['tab_activo'], 'TODOS')

    def test_filtro_por_tab_estado(self):
        cliente = crear_cliente()
        crear_pedido(cliente, estado='PENDIENTE')
        listo = crear_pedido(cliente, estado='LISTO')

        response = self.client.get(self.url, {'tab': 'LISTO'})
        pedidos_mostrados = list(response.context['page_obj'])

        self.assertEqual(len(pedidos_mostrados), 1)
        self.assertEqual(pedidos_mostrados[0].pk, listo.pk)

    def test_busqueda_por_nombre_cliente(self):
        cliente = crear_cliente(username='ana1', email='ana@mimada.com', first_name='Ana')
        otro = crear_cliente(username='beatriz1', email='bea@mimada.com', first_name='Beatriz')
        crear_pedido(cliente)
        crear_pedido(otro)

        response = self.client.get(self.url, {'q': 'Ana'})
        pedidos_mostrados = list(response.context['page_obj'])

        self.assertEqual(len(pedidos_mostrados), 1)
        self.assertEqual(pedidos_mostrados[0].cliente.pk, cliente.pk)

    def test_busqueda_por_numero_pedido(self):
        cliente = crear_cliente()
        pedido = crear_pedido(cliente)

        response = self.client.get(self.url, {'q': str(pedido.id)})
        pedidos_mostrados = list(response.context['page_obj'])

        self.assertEqual(len(pedidos_mostrados), 1)
        self.assertEqual(pedidos_mostrados[0].pk, pedido.pk)

    def test_busqueda_sin_resultados(self):
        cliente = crear_cliente()
        crear_pedido(cliente)

        response = self.client.get(self.url, {'q': 'nombre-que-no-existe'})
        self.assertContains(response, 'No hay pedidos todavía.')

    def test_paginacion_diez_por_pagina(self):
        cliente = crear_cliente()
        for _ in range(15):
            crear_pedido(cliente)

        response = self.client.get(self.url)
        self.assertEqual(len(response.context['page_obj']), 10)
        self.assertEqual(response.context['total_pedidos'], 15)

        response_pagina_2 = self.client.get(self.url, {'page': 2})
        self.assertEqual(len(response_pagina_2.context['page_obj']), 5)

    def test_ver_muestra_panel_detalle(self):
        cliente = crear_cliente()
        pedido = crear_pedido(cliente)

        response = self.client.get(self.url, {'ver': pedido.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['pedido_detalle'])
        self.assertEqual(response.context['pedido_detalle'].pk, pedido.pk)

    def test_ver_con_id_inexistente_da_404(self):
        response = self.client.get(self.url, {'ver': 99999})
        self.assertEqual(response.status_code, 404)

    def test_sin_ver_pedido_detalle_es_none(self):
        response = self.client.get(self.url)
        self.assertIsNone(response.context['pedido_detalle'])


class AccionPedidoViewTests(TestCase):
    """Pruebas del flujo de cambio de estado (form POST) de pedidosadmin:accion."""

    def setUp(self):
        self.admin = crear_usuario()
        self.client.force_login(self.admin)
        self.cliente = crear_cliente()

    def _url(self, pedido):
        return reverse('pedidosadmin:accion', args=[pedido.pk])

    def test_requiere_login(self):
        self.client.logout()
        pedido = crear_pedido(self.cliente)
        response = self.client.post(self._url(pedido), {'accion': 'aprobar'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)

    def test_aprobar_cambia_a_en_proceso(self):
        pedido = crear_pedido(self.cliente, estado='PENDIENTE')
        self.client.post(self._url(pedido), {'accion': 'aprobar'})
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'EN_PROCESO')

    def test_marcar_listo_redirige_a_desglose_sin_cambiar_estado(self):
        # 'marcar_listo' ya no cambia el estado directo: primero pide el
        # desglose de flores (ver DesgloseFloresViewTests para el flujo completo).
        pedido = crear_pedido(self.cliente, estado='EN_PROCESO')
        response = self.client.post(self._url(pedido), {'accion': 'marcar_listo'})

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse('pedidosadmin:desglosar_flores', args=[pedido.pk]),
            response.url,
        )

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'EN_PROCESO')

    def test_entregar_cambia_a_entregado(self):
        pedido = crear_pedido(self.cliente, estado='LISTO')
        self.client.post(self._url(pedido), {'accion': 'entregar'})
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'ENTREGADO')

    def test_cancelar_cambia_a_cancelado(self):
        pedido = crear_pedido(self.cliente, estado='PENDIENTE')
        self.client.post(self._url(pedido), {'accion': 'cancelar'})
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'CANCELADO')

    def test_accion_invalida_no_cambia_estado(self):
        pedido = crear_pedido(self.cliente, estado='PENDIENTE')
        self.client.post(self._url(pedido), {'accion': 'algo_que_no_existe'})
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'PENDIENTE')

    def test_sin_accion_no_cambia_estado(self):
        pedido = crear_pedido(self.cliente, estado='PENDIENTE')
        self.client.post(self._url(pedido), {})
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'PENDIENTE')

    def test_redirige_a_next_si_se_provee(self):
        pedido = crear_pedido(self.cliente, estado='PENDIENTE')
        next_url = '/pedidosadmin/?tab=TODOS&page=1'
        response = self.client.post(self._url(pedido), {'accion': 'aprobar', 'next': next_url})
        self.assertRedirects(response, next_url, fetch_redirect_response=False)

    def test_redirige_a_dashboard_sin_next(self):
        pedido = crear_pedido(self.cliente, estado='PENDIENTE')
        response = self.client.post(self._url(pedido), {'accion': 'aprobar'})
        self.assertRedirects(response, reverse('pedidosadmin:dashboard'))

    def test_pedido_inexistente_da_404(self):
        response = self.client.post(reverse('pedidosadmin:accion', args=[99999]), {'accion': 'aprobar'})
        self.assertEqual(response.status_code, 404)

    def test_get_no_procesa_accion(self):
        pedido = crear_pedido(self.cliente, estado='PENDIENTE')
        response = self.client.get(self._url(pedido))
        pedido.refresh_from_db()
        # un GET no debe cambiar el estado, solo redirigir
        self.assertEqual(pedido.estado, 'PENDIENTE')
        self.assertEqual(response.status_code, 302)


class DesgloseFloresViewTests(TestCase):
    """Pruebas del formulario de desglose de flores (pedidosadmin:desglosar_flores),
    que ahora es el paso que de verdad marca un pedido como LISTO y descuenta
    el inventario."""

    def setUp(self):
        self.admin = crear_usuario()
        self.client.force_login(self.admin)
        self.cliente = crear_cliente()

        self.categoria_girasoles = CategoriaInventario.objects.create(
            nombre='girasoles', tipo='PRODUCTO_TERMINADO',
        )
        self.item_girasol = ItemInventario.objects.create(
            categoria=self.categoria_girasoles, nombre='Girasol', stock_actual=50,
        )

    def _url(self, pedido):
        return reverse('pedidosadmin:desglosar_flores', args=[pedido.pk])

    def test_requiere_login(self):
        self.client.logout()
        pedido = crear_pedido(self.cliente, estado='EN_PROCESO')
        response = self.client.get(self._url(pedido))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)

    def test_get_muestra_formulario(self):
        pedido = crear_pedido(self.cliente, estado='EN_PROCESO')
        response = self.client.get(self._url(pedido))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Girasol')

    def test_post_descuenta_inventario_y_marca_listo(self):
        pedido = crear_pedido(self.cliente, estado='EN_PROCESO')

        response = self.client.post(self._url(pedido), {
            f'item_{self.item_girasol.id}': '5',
        })

        self.assertRedirects(response, reverse('pedidosadmin:dashboard'))

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'LISTO')

        self.item_girasol.refresh_from_db()
        self.assertEqual(self.item_girasol.stock_actual, 45)

    def test_post_redirige_a_next_si_se_provee(self):
        pedido = crear_pedido(self.cliente, estado='EN_PROCESO')
        next_url = '/pedidosadmin/?tab=TODOS&page=1'

        response = self.client.post(
            f'{self._url(pedido)}?next={quote(next_url)}',
            {f'item_{self.item_girasol.id}': '3'},
        )

        self.assertRedirects(response, next_url, fetch_redirect_response=False)

    def test_post_sin_cantidades_no_marca_listo(self):
        pedido = crear_pedido(self.cliente, estado='EN_PROCESO')
        self.client.post(self._url(pedido), {})
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'EN_PROCESO')

    def test_no_descuenta_dos_veces_el_mismo_pedido(self):
        pedido = crear_pedido(self.cliente, estado='EN_PROCESO')

        self.client.post(self._url(pedido), {f'item_{self.item_girasol.id}': '5'})
        self.item_girasol.refresh_from_db()
        self.assertEqual(self.item_girasol.stock_actual, 45)

        # Si se vuelve a entrar al formulario (o se reenvía), no debe
        # volver a descontar.
        self.client.post(self._url(pedido), {f'item_{self.item_girasol.id}': '5'})
        self.item_girasol.refresh_from_db()
        self.assertEqual(self.item_girasol.stock_actual, 45)

    def test_pedido_inexistente_da_404(self):
        response = self.client.get(reverse('pedidosadmin:desglosar_flores', args=[99999]))
        self.assertEqual(response.status_code, 404)


class DetallePedidoViewTests(TestCase):
    """Pruebas de front para pedidosadmin:detalle (página alternativa completa)."""

    def setUp(self):
        self.admin = crear_usuario()
        self.client.force_login(self.admin)
        self.cliente = crear_cliente()

    def test_requiere_login(self):
        self.client.logout()
        pedido = crear_pedido(self.cliente)
        response = self.client.get(reverse('pedidosadmin:detalle', args=[pedido.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)

    def test_muestra_detalle_del_pedido(self):
        pedido = crear_pedido(self.cliente, estado='EN_PROCESO')
        response = self.client.get(reverse('pedidosadmin:detalle', args=[pedido.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'order-{pedido.id}')
        self.assertContains(response, 'En proceso')

    def test_pedido_inexistente_da_404(self):
        response = self.client.get(reverse('pedidosadmin:detalle', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_muestra_productos_del_detalle_pedido(self):
        categoria = Categoria.objects.create(nombre='FLORES')
        producto = Producto.objects.create(
            categoria=categoria, nombre='Ramo de 7 Rosas', precio=Decimal('90000.00'),
        )
        pedido = crear_pedido(self.cliente)
        pedido.detalles.create(
            producto=producto, cantidad=1,
            precio_unitario=Decimal('90000.00'), subtotal=Decimal('90000.00'),
        )

        response = self.client.get(reverse('pedidosadmin:detalle', args=[pedido.pk]))
        self.assertContains(response, 'Ramo de 7 Rosas')

    def test_pedido_sin_productos_muestra_mensaje(self):
        pedido = crear_pedido(self.cliente)
        response = self.client.get(reverse('pedidosadmin:detalle', args=[pedido.pk]))
        self.assertContains(response, 'Sin productos registrados.')