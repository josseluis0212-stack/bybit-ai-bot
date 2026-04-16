import sys
import os

# Añadir el path del proyecto para importar los módulos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from database.db_manager import db_manager

if __name__ == "__main__":
    print("--- Iniciando reset de estadisticas para el lanzamiento de V9.4 ---")
    success = db_manager.reset_all_stats()
    if success:
        print("EXITO: El historial ha sido borrado. Los contadores en el Dashboard empezaran de cero.")
    else:
        print("ERROR: No se pudo resetear la base de datos.")
