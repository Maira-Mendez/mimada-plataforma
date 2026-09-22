from django.urls import path
from . import views

app_name = 'pedidosadmin'

urlpatterns = [
    path('', views.lista_pedidos, name='dashboard'),
    path('<int:pk>/', views.detalle_pedido, name='detalle'),
    path('<int:pk>/accion/', views.accion_pedido, name='accion'),
path('registrar-presencial/', views.registrar_venta_presencial, name='registrar_presencial'),
    path('pedidos/<int:pk>/listo/', views.desglosar_flores, name='desglosar_flores'),
]