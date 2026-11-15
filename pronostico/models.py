from django.db import models


class HistorialVentas(models.Model):
    producto = models.CharField(max_length=150)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    cantidad = models.PositiveIntegerField()
    fecha_comercial = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = "Historial de Venta"
        verbose_name_plural = "Historial de Ventas"
        ordering = ['fecha_inicio', 'producto']

    def __str__(self):
        return f"{self.producto} — {self.fecha_inicio} ({self.cantidad})"
