from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from catalogo.models import Producto
from django.shortcuts import render, redirect, get_object_or_404
from .forms import LoginForm, RegistroForm, EditarPerfilForm
from django.contrib.auth import views as auth_views
from .forms import CustomPasswordResetForm
import random
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import Usuario

@login_required(login_url='usuarios:login')
def mi_cuenta_view(request):
    user = request.user
    nombre_original = user.first_name
    email_original = user.email
    telefono_original = user.telefono or ''

    if request.method == 'POST':
        form = EditarPerfilForm(request.POST, instance=user)
        if form.is_valid():
            nuevo_nombre = form.cleaned_data['first_name']
            nuevo_email = form.cleaned_data['email']
            nuevo_telefono = form.cleaned_data['telefono']

            cambia_email = nuevo_email != email_original
            cambia_telefono = nuevo_telefono != telefono_original

            if nuevo_nombre != nombre_original:
                user.first_name = nuevo_nombre
                user.save(update_fields=['first_name'])

            if cambia_email or cambia_telefono:
                codigo = f"{random.randint(0, 999999):06d}"
                request.session['verificacion_cuenta'] = {
                    'codigo': codigo,
                    'nuevo_email': nuevo_email if cambia_email else None,
                    'nuevo_telefono': nuevo_telefono if cambia_telefono else None,
                    'expira': (timezone.now() + timedelta(minutes=10)).isoformat(),
                }

                send_mail(
                    subject='Código de verificación - Mimada',
                    message=(
                        f'Hola {user.first_name},\n\n'
                        f'Tu código de verificación es: {codigo}\n'
                        f'Expira en 10 minutos.\n\n'
                        f'Si tú no solicitaste este cambio, ignora este mensaje.'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else None,
                    recipient_list=[email_original],
                )

                messages.info(request, f'Te enviamos un código de verificación a {email_original}.')
                return redirect('usuarios:verificar_cambio')

            messages.success(request, 'Tus datos se actualizaron correctamente.')
            return redirect('usuarios:mi_cuenta')
    else:
        form = EditarPerfilForm(instance=user)

    return render(request, 'usuarios/mi_cuenta.html', {'form': form})
@login_required(login_url='usuarios:login')
def verificar_cambio_view(request):
    pendiente = request.session.get('verificacion_cuenta')

    if not pendiente:
        messages.error(request, 'No hay ningún cambio pendiente de verificación.')
        return redirect('usuarios:mi_cuenta')

    expira = timezone.datetime.fromisoformat(pendiente['expira'])
    if timezone.now() > expira:
        del request.session['verificacion_cuenta']
        messages.error(request, 'El código expiró. Intenta el cambio de nuevo.')
        return redirect('usuarios:mi_cuenta')

    if request.method == 'POST':
        codigo_ingresado = request.POST.get('codigo', '').strip()
        if codigo_ingresado == pendiente['codigo']:
            user = request.user
            if pendiente.get('nuevo_email'):
                user.email = pendiente['nuevo_email']
                user.username = pendiente['nuevo_email']
            if pendiente.get('nuevo_telefono') is not None:
                user.telefono = pendiente['nuevo_telefono']
            user.save()

            del request.session['verificacion_cuenta']
            messages.success(request, 'Tus datos se actualizaron correctamente.')
            return redirect('usuarios:mi_cuenta')
        else:
            messages.error(request, 'Código incorrecto. Intenta de nuevo.')

    return render(request, 'usuarios/verificar_cambio.html')

def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
        else:
            correo = request.POST.get('username')
            if correo and not Usuario.objects.filter(username=correo).exists():
                messages.error(request, 'Ese correo no está registrado. ¿Quieres crear una cuenta?')
            else:
                messages.error(request, 'Contraseña incorrecta. Intenta de nuevo.')
    else:
        form = LoginForm()

    return render(request, 'usuarios/login.html', {'form': form})

def registro_view(request):
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.username = form.cleaned_data['email']  # Usa el correo como username
            if form.cleaned_data.get('acepta_tratamiento_datos'):
                user.fecha_aceptacion_tratamiento_datos = timezone.now()
            user.save()
            login(request, user)
            return redirect('home')
    else:
        form = RegistroForm()

    return render(request, 'usuarios/registro.html', {'form': form})


def logout_view(request):
    carrito_actual = request.session.get('carrito', [])
    logout(request)
    request.session['carrito'] = carrito_actual
    return redirect('home')

def login_admin_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_staff:
            login(request, user)
            return redirect('inventario:dashboard')
        else:
            messages.error(
                request,
                'Credenciales incorrectas o no tienes permisos de administrador'
            )

    return render(request, 'usuarios/login_admin.html')


@login_required(login_url='usuarios:login')
def favoritos_view(request):
    favoritos = request.user.favoritos.all()
    return render(request, 'usuarios/favoritos.html', {'favoritos': favoritos})


@login_required(login_url='usuarios:login')
def toggle_favorito(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    if producto in request.user.favoritos.all():
        request.user.favoritos.remove(producto)
    else:
        request.user.favoritos.add(producto)
    return redirect(request.META.get('HTTP_REFERER', 'usuarios:favoritos'))



class CustomPasswordResetView(auth_views.PasswordResetView):
    form_class = CustomPasswordResetForm
    template_name = 'usuarios/password_reset.html'