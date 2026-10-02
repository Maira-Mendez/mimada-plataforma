from pathlib import Path

from django.core.management.base import BaseCommand
from openpyxl import load_workbook


class Command(BaseCommand):
    help = "Corrige datos específicos del historial de ventas en el Excel"

    def handle(self, *args, **options):
        # Ubicación del Excel: está en la carpeta donde está manage.py
        ruta_excel = Path(__file__).resolve().parents[3] / "ventas_flores_por_semana.xlsx"

        # Abrir el Excel
        libro = load_workbook(ruta_excel)

        # Seleccionar la hoja 2
        hoja = libro.worksheets[1]

        # Cambiar únicamente las celdas indicadas
        hoja["F30"] = 25
        hoja["I30"] = 1
        hoja["P30"] = 2
        hoja["Q30"] = 2

        # Guardar los cambios
        libro.save(ruta_excel)

        self.stdout.write(
            self.style.SUCCESS(
                "Excel corregido correctamente. Se modificaron F30, I30, P30 y Q30 de la hoja 2."
            )
        )