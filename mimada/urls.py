from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from catalogo import views as catalogo_views
from usuarios.views import CustomPasswordResetView


urlpatterns = [
    path('', catalogo_views.inicio, name='home'),
    path('admin/', admin.site.urls),
    path('usuarios/', include('usuarios.urls')),
    path('catalogo/', include('catalogo.urls')),
    path('pedidos/', include('pedidos.urls')),
    path('finanzas/', include('finanzas.urls')),
    path('inventario/', include('inventario.urls')),
    path('pedidosadmin/', include('pedidosadmin.urls')),
    path('asistente-ia/', include('pronostico.urls')),
    path('password-reset/', CustomPasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='usuarios/password_reset_done.html'
         ), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='usuarios/password_reset_confirm.html'
         ), name='password_reset_confirm'),
    path('password-reset-complete/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='usuarios/password_reset_complete.html'
         ), name='password_reset_complete'),
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
