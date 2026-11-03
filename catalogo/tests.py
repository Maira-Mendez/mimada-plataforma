from django.test import TestCase
from .forms import ProductoForm, ItemCarruselForm, ProductoDelMesForm
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import Categoria, Producto


class ProductoFormTest(TestCase):

    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='FLORES')

    def test_producto_valido(self):
        form = ProductoForm(data={
            'categoria': self.categoria.id,
            'nombre': 'Ramo de rosas rojas',
            'descripcion': 'Ramo de 12 rosas frescas',
            'precio': 50000,
            'disponible': True,
            'destacado': True,
        })
        self.assertTrue(form.is_valid())

    def test_producto_requiere_categoria(self):
        form = ProductoForm(data={
            'categoria': '',
            'nombre': 'Ramo de rosas rojas',
            'precio': 50000,
            'disponible': True,
            'destacado': True,
        })
        self.assertFalse(form.is_valid())

    def test_producto_requiere_nombre(self):
        form = ProductoForm(data={
            'categoria': self.categoria.id,
            'nombre': '',
            'precio': 50000,
            'disponible': True,
            'destacado': True,
        })
        self.assertFalse(form.is_valid())

    def test_producto_requiere_precio(self):
        form = ProductoForm(data={
            'categoria': self.categoria.id,
            'nombre': 'Ramo de rosas rojas',
            'precio': '',
            'disponible': True,
            'destacado': True,
        })
        self.assertFalse(form.is_valid())

    def test_producto_descripcion_es_opcional(self):
        form = ProductoForm(data={
            'categoria': self.categoria.id,
            'nombre': 'Ramo de rosas rojas',
            'descripcion': '',
            'precio': 50000,
            'disponible': True,
            'destacado': True,
        })
        self.assertTrue(form.is_valid())

    def test_producto_destacado_false_es_valido(self):
        """
        Con blank=True en 'destacado', omitir el checkbox (equivalente a
        desmarcarlo / False) ya no debe hacer fallar el form.
        """
        form = ProductoForm(data={
            'categoria': self.categoria.id,
            'nombre': 'Ramo de rosas rojas',
            'precio': 50000,
            'disponible': True,
            # 'destacado' omitido a propósito, simula checkbox sin marcar
        })
        self.assertTrue(form.is_valid())
        self.assertFalse(form.cleaned_data['destacado'])


class ItemCarruselFormTest(TestCase):

    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='FLORES')
        self.producto = Producto.objects.create(
            categoria=self.categoria,
            nombre='Ramo de rosas rojas',
            precio=50000,
        )

    def test_item_valido_tipo_producto(self):
        form = ItemCarruselForm(data={
            'tipo': 'PRODUCTO',
            'producto': self.producto.id,
            'ajuste_imagen': 'CONTENER',
            'orden': 1,
            'activo': True,
        })
        self.assertTrue(form.is_valid())

    def test_item_valido_tipo_banner(self):
        form = ItemCarruselForm(data={
            'tipo': 'BANNER',
            'ajuste_imagen': 'RECORTAR',
            'titulo': 'Mes del amor y la amistad',
            'subtitulo': 'El mes perfecto para tu pedido',
            'texto_boton': 'Ver más',
            'url_destino': '/catalogo/lista/',
            'orden': 2,
            'activo': True,
        })
        self.assertTrue(form.is_valid())

    def test_item_requiere_tipo(self):
        form = ItemCarruselForm(data={
            'tipo': '',
            'ajuste_imagen': 'CONTENER',
            'orden': 1,
            'activo': True,
        })
        self.assertFalse(form.is_valid())

    def test_item_requiere_ajuste_imagen(self):
        form = ItemCarruselForm(data={
            'tipo': 'BANNER',
            'ajuste_imagen': '',
            'orden': 1,
            'activo': True,
        })
        self.assertFalse(form.is_valid())

    def test_item_requiere_orden(self):
        form = ItemCarruselForm(data={
            'tipo': 'BANNER',
            'ajuste_imagen': 'CONTENER',
            'orden': '',
            'activo': True,
        })
        self.assertFalse(form.is_valid())

    def test_item_titulo_es_opcional(self):
        form = ItemCarruselForm(data={
            'tipo': 'BANNER',
            'ajuste_imagen': 'CONTENER',
            'titulo': '',
            'orden': 1,
            'activo': True,
        })
        self.assertTrue(form.is_valid())

    def test_item_producto_no_es_obligatorio_ni_siquiera_en_tipo_producto(self):
        """
        Documenta el comportamiento actual: a diferencia de ProductoDelMesForm,
        ItemCarruselForm NO tiene un clean() que exija 'producto' cuando
        tipo == 'PRODUCTO'. Con los datos de hoy, esta combinación sí valida.
        Si quieres la misma validación cruzada que en ProductoDelMesForm,
        avísame y le agregamos un clean() igual.
        """
        form = ItemCarruselForm(data={
            'tipo': 'PRODUCTO',
            'producto': '',
            'ajuste_imagen': 'CONTENER',
            'orden': 1,
            'activo': True,
        })
        self.assertTrue(form.is_valid())


class ProductoDelMesFormTest(TestCase):

    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='FLORES')
        self.producto = Producto.objects.create(
            categoria=self.categoria,
            nombre='Ramo de rosas rojas',
            precio=50000,
        )

    def test_producto_del_mes_valido_tipo_producto(self):
        form = ProductoDelMesForm(data={
            'tipo': 'PRODUCTO',
            'producto': self.producto.id,
            'orden': 1,
            'activo': True,
        })
        self.assertTrue(form.is_valid())

    def test_producto_del_mes_valido_tipo_personalizado(self):
        form = ProductoDelMesForm(data={
            'tipo': 'PERSONALIZADO',
            'titulo': 'Promo especial',
            'descripcion': 'Contenido armado a mano para este mes',
            'orden': 2,
            'activo': True,
        })
        self.assertTrue(form.is_valid())

    def test_producto_del_mes_tipo_producto_requiere_producto(self):
        form = ProductoDelMesForm(data={
            'tipo': 'PRODUCTO',
            'producto': '',
            'orden': 1,
            'activo': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('producto', form.errors)

    def test_producto_del_mes_requiere_tipo(self):
        form = ProductoDelMesForm(data={
            'tipo': '',
            'orden': 1,
            'activo': True,
        })
        self.assertFalse(form.is_valid())

    def test_producto_del_mes_requiere_orden(self):
        form = ProductoDelMesForm(data={
            'tipo': 'PERSONALIZADO',
            'titulo': 'Promo especial',
            'orden': '',
            'activo': True,
        })
        self.assertFalse(form.is_valid())

    def test_producto_del_mes_descripcion_es_opcional(self):
        form = ProductoDelMesForm(data={
            'tipo': 'PERSONALIZADO',
            'titulo': 'Promo especial',
            'descripcion': '',
            'orden': 1,
            'activo': True,
        })
        self.assertTrue(form.is_valid())

# Create your tests here.
Usuario = get_user_model()


class CatalogoVistasPublicasTest(TestCase):
    """Vistas que no requieren login: cualquier visitante debe poder verlas."""

    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='FLORES')
        self.producto = Producto.objects.create(
            categoria=self.categoria, nombre='Ramo de rosas rojas', precio=50000,
        )

    def test_lista_productos_carga_ok(self):
        response = self.client.get(reverse('catalogo:lista'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'catalogo/lista.html')
        self.assertContains(response, 'Ramo de rosas rojas')

    def test_detalle_producto_carga_ok(self):
        response = self.client.get(reverse('catalogo:detalle_producto', args=[self.producto.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'catalogo/detalle_producto.html')

    def test_detalle_producto_404_si_no_existe(self):
        response = self.client.get(reverse('catalogo:detalle_producto', args=[9999]))
        self.assertEqual(response.status_code, 404)

    def test_nosotros_carga_ok(self):
        response = self.client.get(reverse('catalogo:nosotros'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'catalogo/nosotros.html')


class AdminDashboardAccesoTest(TestCase):
    """Patrón de permisos de admin_dashboard: se repite igual en
    carrusel_dashboard y destacados_mes_dashboard, así que este es el que
    se prueba a fondo (anónimo / cliente normal / admin)."""

    def setUp(self):
        self.cliente = Usuario.objects.create_user(
            username='cliente@ejemplo.com', email='cliente@ejemplo.com', password='ClaveSegura123'
        )
        self.admin = Usuario.objects.create_user(
            username='admin@ejemplo.com', email='admin@ejemplo.com', password='ClaveSegura123'
        )
        self.admin.es_admin = True
        self.admin.save()

    def test_admin_dashboard_redirige_si_no_esta_logueado(self):
        response = self.client.get(reverse('catalogo:admin_dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_admin_dashboard_prohibido_si_no_es_admin(self):
        self.client.login(username='cliente@ejemplo.com', password='ClaveSegura123')
        response = self.client.get(reverse('catalogo:admin_dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_admin_dashboard_ok_si_es_admin(self):
        self.client.login(username='admin@ejemplo.com', password='ClaveSegura123')
        response = self.client.get(reverse('catalogo:admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'catalogoadmin/dashboard.html')


class CarruselYDestacadosDashboardAccesoTest(TestCase):
    """Chequeo rápido de que el mismo patrón de permisos también
    está aplicado en las otras 2 dashboards de admin."""

    def setUp(self):
        self.cliente = Usuario.objects.create_user(
            username='cliente2@ejemplo.com', email='cliente2@ejemplo.com', password='ClaveSegura123'
        )
        self.admin = Usuario.objects.create_user(
            username='admin2@ejemplo.com', email='admin2@ejemplo.com', password='ClaveSegura123'
        )
        self.admin.es_admin = True
        self.admin.save()

    def test_carrusel_dashboard_prohibido_si_no_es_admin(self):
        self.client.login(username='cliente2@ejemplo.com', password='ClaveSegura123')
        response = self.client.get(reverse('catalogo:carrusel_dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_carrusel_dashboard_ok_si_es_admin(self):
        self.client.login(username='admin2@ejemplo.com', password='ClaveSegura123')
        response = self.client.get(reverse('catalogo:carrusel_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_destacados_mes_dashboard_prohibido_si_no_es_admin(self):
        self.client.login(username='cliente2@ejemplo.com', password='ClaveSegura123')
        response = self.client.get(reverse('catalogo:destacados_mes_dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_destacados_mes_dashboard_ok_si_es_admin(self):
        self.client.login(username='admin2@ejemplo.com', password='ClaveSegura123')
        response = self.client.get(reverse('catalogo:destacados_mes_dashboard'))
        self.assertEqual(response.status_code, 200)


class ProductoCrudViewTest(TestCase):
    """Flujo de crear/eliminar producto desde el admin."""

    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='FLORES')
        self.admin = Usuario.objects.create_user(
            username='admin3@ejemplo.com', email='admin3@ejemplo.com', password='ClaveSegura123'
        )
        self.admin.es_admin = True
        self.admin.save()
        self.producto = Producto.objects.create(
            categoria=self.categoria, nombre='Ramo viejo', precio=20000,
        )

    def test_crear_producto_prohibido_si_no_es_admin(self):
        response = self.client.get(reverse('catalogo:crear_producto'))
        self.assertEqual(response.status_code, 302)  # ni siquiera logueado -> redirige a login

    def test_crear_producto_post_valido_crea_y_redirige(self):
        self.client.login(username='admin3@ejemplo.com', password='ClaveSegura123')
        response = self.client.post(reverse('catalogo:crear_producto'), data={
            'categoria': self.categoria.id,
            'nombre': 'Ramo nuevo',
            'precio': 30000,
            'disponible': True,
            'destacado': False,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Producto.objects.filter(nombre='Ramo nuevo').exists())

    def test_eliminar_producto_con_get_lo_borra_igual(self):
        """
        Documenta el comportamiento actual: eliminar_producto no revisa
        request.method, así que un simple GET (entrar al link) ya borra el
        producto. Si más adelante se agrega el 'if request.method == POST',
        este test debe cambiarse para esperar que el producto SIGA existiendo
        tras un GET.
        """
        self.client.login(username='admin3@ejemplo.com', password='ClaveSegura123')
        response = self.client.get(reverse('catalogo:eliminar_producto', args=[self.producto.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Producto.objects.filter(pk=self.producto.pk).exists())


















