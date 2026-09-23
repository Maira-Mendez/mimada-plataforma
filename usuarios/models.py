from django.db import models
from django.contrib.auth.models import AbstractUser

class Usuario(AbstractUser):
    telefono = models.CharField(max_length=15, blank=True, null=True)
    es_cliente = models.BooleanField(default=True)
    es_admin = models.BooleanField(default=False)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    favoritos = models.ManyToManyField('catalogo.Producto', blank=True, related_name='favoritado_por')
    acepta_tratamiento_datos = models.BooleanField(default=False)
    fecha_aceptacion_tratamiento_datos = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.email