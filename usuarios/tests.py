# Create your tests here.
from django.test import TestCase
from .forms import LoginForm, RegistroForm
from .models import Usuario


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