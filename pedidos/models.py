from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from inventario.models import ItemInventario
from catalogo.models import Producto


class Pedido(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('CONFIRMADO', 'Confirmado'),
        ('EN_PROCESO', 'En proceso'),
        ('LISTO', 'Listo para entregar'),
        ('ENTREGADO', 'Entregado'),
        ('CANCELADO', 'Cancelado'),
    ]
    TIPO_ENTREGA = [
        ('DOMICILIO', 'Domicilio'),
        ('SOACHA', 'Recoger en tienda ubicada en Soacha'),
        ('PLAZA', 'Recoger en Plaza de las Américas'),
        #('MOSTRADOR', 'Venta presencial en mostrador'),
    ]

    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='pedidos'
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PENDIENTE'
    )

    tipo_entrega = models.CharField(
        max_length=20,
        choices=TIPO_ENTREGA,
        default='DOMICILIO'
    )

    es_regalo = models.BooleanField(default=False)

    entrega_anonima = models.BooleanField(default=False)

    nombre_destinatario = models.CharField(
        max_length=120,
        blank=True
    )

    telefono_destinatario = models.CharField(
        max_length=20,
        blank=True
    )

    mensaje = models.TextField(
        blank=True
    )

    direccion = models.CharField(
        max_length=250,
        blank=True
    )

    barrio = models.CharField(
        max_length=100,
        blank=True
    )

    ciudad = models.CharField(
        max_length=80,
        default="Bogotá"
    )

    referencia = models.TextField(
        blank=True
    )

    fecha_entrega = models.DateField(
        null=True,
        blank=True
    )
    hora_entrega = models.CharField(
        max_length=30,
        blank=True,
        default=""
    )

    valor_domicilio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    acepta_terminos = models.BooleanField(default=False)
    fecha_aceptacion_terminos = models.DateTimeField(null=True, blank=True)

    fecha_creacion = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Pedido #{self.id} - {self.cliente}"

class DetallePedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, null=True, blank=True)
    es_personalizado = models.BooleanField(default=False)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)


    def __str__(self):
        return f"Detalle de pedido #{self.pedido_id}"


class ConfiguracionRamo(models.Model):
    """Solo existe si DetallePedido.es_personalizado = True"""

    TIPO_ARMADO_CHOICES = [
        ('INDIVIDUAL', 'Flores individuales'),
        ('RAMO', 'En ramo'),
    ]

    detalle_pedido = models.OneToOneField(DetallePedido, on_delete=models.CASCADE, related_name='configuracion')
    cantidad_rosas = models.PositiveSmallIntegerField(default=0)
    cantidad_girasoles = models.PositiveSmallIntegerField(default=0)
    cantidad_lirios = models.PositiveSmallIntegerField(default=0)
    color_cinta = models.ManyToManyField(ItemInventario, blank=True, related_name='+')
    color_lirio = models.ManyToManyField(ItemInventario, blank=True, related_name='+')
    papel_decorativo = models.ForeignKey(ItemInventario, on_delete=models.PROTECT, related_name='+', null=True,
                                         blank=True)
    adicionales = models.ManyToManyField(ItemInventario, blank=True, related_name='+')

    pliegos_utilizados = models.PositiveSmallIntegerField(
        default=0,
        help_text="Pliegos de papel descontados para este ramo (calculados por tabla o ingresados manualmente en pedidos de 50/100 flores)."
    )
    tipo_armado = models.CharField(
        max_length=10,
        choices=TIPO_ARMADO_CHOICES,
        blank=True,
        null=True,
        help_text="Solo aplica para pedidos de 50 o 100 flores. Dato informativo, no afecta cálculos."
    )

    def __str__(self):
        return f"Config. ramo - detalle #{self.detalle_pedido_id}"