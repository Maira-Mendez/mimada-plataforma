from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Pedido
from pronostico.utils import registrar_venta


@receiver(pre_save, sender=Pedido)
def guardar_estado_anterior(sender, instance, **kwargs):
    if instance.pk:
        try:
            anterior = Pedido.objects.get(pk=instance.pk)
            instance._estado_anterior = anterior.estado
        except Pedido.DoesNotExist:
            instance._estado_anterior = None
    else:
        instance._estado_anterior = None


@receiver(post_save, sender=Pedido)
def registrar_venta_al_entregar(sender, instance, created, **kwargs):
    if created:
        return

    estado_anterior = getattr(instance, '_estado_anterior', None)
    if estado_anterior == 'ENTREGADO' or instance.estado != 'ENTREGADO':
        return  # solo actúa la PRIMERA vez que pasa a Entregado

    fecha = instance.fecha_entrega or timezone.now().date()

    for detalle in instance.detalles.all():
        if detalle.es_personalizado and hasattr(detalle, 'configuracion'):
            config = detalle.configuracion
            if config.cantidad_rosas:
                registrar_venta('rosas unidad', config.cantidad_rosas * detalle.cantidad, fecha)
            if config.cantidad_girasoles:
                registrar_venta('unidad girasol', config.cantidad_girasoles * detalle.cantidad, fecha)
        elif detalle.producto:
            registrar_venta(detalle.producto.nombre.lower(), detalle.cantidad, fecha)