import sqlite3
import datetime
import os
import shutil

class GoldLogger:
    def __init__(self, db_path="gold_log.db", legacy_txt_path="gold_diary.txt"):
        self.db_path = db_path
        self._init_db()
        self._migrate_legacy_txt(legacy_txt_path)

    def _init_db(self):
        """Inicializa la base de datos si no existe."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gold_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    amount INTEGER
                )
            """)

    def _migrate_legacy_txt(self, txt_path):
        """Migra datos del fichero de texto antiguo si existe y lo mueve a zz."""
        if not os.path.exists(txt_path):
            return
            
        print(f"Migrando {txt_path} a SQLite...")
        entries = []
        try:
            with open(txt_path, "r") as f:
                for line in f:
                    if "Gold Won:" in line:
                        # Formato: YYYY-MM-DD HH:MM:SS | Gold Won: N
                        parts = line.split("| Gold Won:")
                        if len(parts) == 2:
                            ts = parts[0].strip()
                            try:
                                amt = int(parts[1].strip())
                                entries.append((ts, amt))
                            except ValueError:
                                pass
                                
            if entries:
                with sqlite3.connect(self.db_path) as conn:
                    # Usamos executemany para eficiencia
                    conn.executemany("INSERT INTO gold_history (timestamp, amount) VALUES (?, ?)", entries)
                print(f"Migradas {len(entries)} entradas correctamente.")
            
            # Mover a zz
            destination_dir = "zz"
            if not os.path.exists(destination_dir):
                os.makedirs(destination_dir)
            
            shutil.move(txt_path, os.path.join(destination_dir, txt_path))
            print(f"Archivo movido a {destination_dir}/{txt_path}")
            
        except Exception as e:
            print(f"Error en migración: {e}")

    def log_gold(self, amount):
        """Registra una ganancia de oro en la BD."""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("INSERT INTO gold_history (timestamp, amount) VALUES (?, ?)", (now_str, amount))
            print(f"Log saved DB: {amount} Gold at {now_str}")
        except Exception as e:
            print(f"Error escribiendo en DB: {e}")

    def get_todays_gold(self):
        """Suma el oro ganado hoy (YYYY-MM-DD)."""
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT SUM(amount) FROM gold_history WHERE timestamp LIKE ?", (f"{today_str}%",))
                result = cursor.fetchone()[0]
            return result if result else 0
        except Exception:
            return 0

    def get_all_time_gold(self):
        """Suma TODO el oro histórico."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT SUM(amount) FROM gold_history")
                result = cursor.fetchone()[0]
            return result if result else 0
        except Exception:
            return 0
