# Create your tests here.
from django.test import TestCase
from .forms import LoginForm, RegistroForm
from .models import Usuario
from django.urls import reverse
from django.contrib.auth import get_user_model

Usuario = get_user_model()

class RegistroFormTest(TestCase):
    def test_registro_valido(self):
        form = RegistroForm(data={
            'first_name': 'Maira Mendez',
            'email': 'maira@ejemplo.com',
            'telefono': '3001234567',
            'password1': 'ContraseñaSegura123',
            'password2': 'ContraseñaSegura123',
            'acepta_tratamiento_datos': True,
        })
        self.assertTrue(form.is_valid())

    def test_registro_rechaza_correo_duplicado(self):
        Usuario.objects.create_user(
            username='existente@ejemplo.com', email='existente@ejemplo.com',
            password='Clave12345'
        )
        form = RegistroForm(data={
            'first_name': 'Otra Persona',
            'email': 'existente@ejemplo.com',
            'telefono': '3009999999',
            'password1': 'OtraClave123',
            'password2': 'OtraClave123',
            'acepta_tratamiento_datos': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_registro_rechaza_contrasenas_distintas(self):
        form = RegistroForm(data={
            'first_name': 'Alguien',
            'email': 'nuevo@ejemplo.com',
            'telefono': '3001112233',
            'password1': 'ClaveUno123',
            'password2': 'ClaveDistinta456',
            'acepta_tratamiento_datos': True,
        })
        self.assertFalse(form.is_valid())

    def test_registro_rechaza_sin_aceptar_tratamiento_datos(self):
        form = RegistroForm(data={
            'first_name': 'Otra Persona',
            'email': 'nueva@ejemplo.com',
            'telefono': '3001112233',
            'password1': 'ContraseñaSegura123',
            'password2': 'ContraseñaSegura123',
            # acepta_tratamiento_datos no se envía
        })
        self.assertFalse(form.is_valid())
        self.assertIn('acepta_tratamiento_datos', form.errors)


class LoginFormTest(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(
            username='ana@ejemplo.com', email='ana@ejemplo.com', password='ClaveSegura123'
        )

    def test_login_valido(self):
        form = LoginForm(data={'username': 'ana@ejemplo.com', 'password': 'ClaveSegura123'})
        self.assertTrue(form.is_valid())

    def test_login_rechaza_contrasena_incorrecta(self):
        form = LoginForm(data={'username': 'ana@ejemplo.com', 'password': 'ClaveEquivocada'})
        self.assertFalse(form.is_valid())



class AccesoAdminTest(TestCase):
    RUTAS = ['inventario:dashboard', 'finanzas:dashboard',
                 'pedidosadmin:dashboard', 'asistente_ia:dashboard']

    def setUp(self):
        self.cliente = Usuario.objects.create_user(
            username='cliente@x.com', email='cliente@x.com', password='Clave12345')
        self.admin = Usuario.objects.create_user(
            username='admin@x.com', email='admin@x.com', password='Clave12345', es_admin=True)

    def test_anonimo_es_redirigido_al_login(self):
        for ruta in self.RUTAS:
            self.assertEqual(self.client.get(reverse(ruta)).status_code, 302)

    def test_cliente_recibe_403(self):
        self.client.login(username='cliente@x.com', password='Clave12345')
        for ruta in self.RUTAS:
            self.assertEqual(self.client.get(reverse(ruta)).status_code, 403)

    def test_admin_puede_entrar(self):
        self.client.login(username='admin@x.com', password='Clave12345')
        for ruta in self.RUTAS:
            self.assertEqual(self.client.get(reverse(ruta)).status_code, 200)