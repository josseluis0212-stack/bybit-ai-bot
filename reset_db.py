import sqlite3
import os

# Ruta de la base de datos (según db_manager.py)
DB_PATH = os.path.join(os.path.dirname(__file__), "database", "bot_database.db")

def reset_all_data():
    if not os.path.exists(DB_PATH):
        print(f"La base de datos no existe en {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. Limpiar historial de trades
        cursor.execute("DELETE FROM trades")
        
        # 2. Reiniciar los autoincrementales
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='trades'")
        
        conn.commit()
        conn.close()
        print("✅ Base de datos REINICIADA completamente. Historial borrado.")
    except Exception as e:
        print(f"❌ Error reiniciando DB: {e}")

if __name__ == "__main__":
    reset_all_data()
