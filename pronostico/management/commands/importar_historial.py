import openpyxl
from django.core.management.base import BaseCommand
from pronostico.models import HistorialVentas
from pronostico.fechas_comerciales import detectar_fecha_comercial


class Command(BaseCommand):
    help = 'Importa el historial de ventas desde el Excel (Hoja 2, formato ancho)'

    def add_arguments(self, parser):
        parser.add_argument('ruta_excel', type=str)

    def handle(self, *args, **options):
        ruta = options['ruta_excel']
        wb = openpyxl.load_workbook(ruta, data_only=True)
        ws = wb['Hoja 2']

        filas = list(ws.iter_rows(values_only=True))
        encabezados = filas[1]
        productos_cols = {
            idx: nombre for idx, nombre in enumerate(encabezados)
            if idx >= 5 and nombre
        }

        creados = 0
        HistorialVentas.objects.all().delete()

        for fila in filas[2:]:
            fecha_inicio = fila[2]
            fecha_fin = fila[3]
            if not fecha_inicio or not fecha_fin:
                continue

            fecha_inicio = fecha_inicio.date() if hasattr(fecha_inicio, 'date') else fecha_inicio
            fecha_fin = fecha_fin.date() if hasattr(fecha_fin, 'date') else fecha_fin

            comercial = detectar_fecha_comercial(fecha_inicio, fecha_fin)

            for idx, producto in productos_cols.items():
                cantidad = fila[idx] if idx < len(fila) else None
                cantidad = cantidad if cantidad else 0
                if cantidad == 0:
                    continue

                HistorialVentas.objects.create(
                    producto=producto.strip(),
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    cantidad=int(cantidad),
                    fecha_comercial=comercial,
                )
                creados += 1

        self.stdout.write(self.style.SUCCESS(f"Se importaron {creados} registros de ventas."))