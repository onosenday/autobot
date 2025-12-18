import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
from PIL import Image, ImageTk
import cv2
import queue
import subprocess
import time
import json
import os
from datetime import datetime, timedelta
from adb_wrapper import ADBWrapper
from logger import GoldLogger


# Importamos la clase del bot (que refactorizaremos en breve)
# Importación diferida o asumiendo que main.py estará listo
try:
    from main import RealRacingBot
except ImportError:
    RealRacingBot = None

class BotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Real Racing 3 Bot Control")
        self.root.geometry("960x700")
        self.root.configure(bg="#102A43") # Match Theme BG
        
        self.adb_preview = ADBWrapper()
        self.is_bot_running = False
        
        self.bot_thread = None
        self.stop_event = threading.Event()
        self.log_queue = queue.Queue()
        self.image_queue = queue.Queue()
        
        self.bot_instance = None
        
        self._apply_theme()
        self._setup_ui()
        self._start_queue_processing()
        
        # Hilo de preview constante
        self.preview_thread = threading.Thread(target=self._run_idle_preview, daemon=True)
        self.preview_thread.start()

        # Session Data
        self.logger = GoldLogger()
        self.session_start_time = None
        self.session_initial_gold = 0
        self.current_session_gold = 0

    def _apply_theme(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Paleta "Night Blue"
        BG_MAIN = "#102A43"   # Deep Navy
        BG_PANEL = "#1E3246"  # Sidebar
        BG_CARD = "#243B53"   # Cards
        FG_TEXT = "#D9E2EC"   # Text
        ACCENT = "#334E68"
        BTN_BG = "#2B6CB0"    # Vivid Blue
        BTN_FG = "#FFFFFF"
        BTN_ACTIVE = "#3182CE"

        style.configure(".", background=BG_MAIN, foreground=FG_TEXT, font=("Segoe UI", 11))
        
        # Custom Frames
        style.configure("Main.TFrame", background=BG_MAIN)
        style.configure("Panel.TFrame", background=BG_PANEL)
        
        # Cards (Labelframes)
        style.configure("Card.TLabelframe", background=BG_CARD, bordercolor=BG_MAIN, relief="flat")
        style.configure("Card.TLabelframe.Label", background=BG_CARD, foreground="#829AB1", font=("Segoe UI", 10, "bold"))
        
        # Labels
        style.configure("TLabel", background=BG_MAIN, foreground=FG_TEXT)
        style.configure("Header.TLabel", font=("Segoe UI", 22, "bold"), foreground="#627D98", background=BG_PANEL)
        style.configure("Stat.TLabel", background=BG_CARD, foreground="#829AB1", font=("Segoe UI", 9)) # Reduced font
        style.configure("StatValue.TLabel", background=BG_CARD, font=("Segoe UI", 16, "bold")) # Reduced font
        style.configure("Status.TLabel", background=BG_CARD, foreground="#48BB78", font=("Segoe UI", 12))

        # Buttons
        style.configure("Action.TButton", padding=12, relief="flat", background=BTN_BG, foreground=BTN_FG, borderwidth=0, font=("Segoe UI", 11, "bold"))
        style.map("Action.TButton", background=[('active', BTN_ACTIVE)])

    def _setup_ui(self):
        main_frame = ttk.Frame(self.root, style="Main.TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Sidebar (Panel Izquierdo) ---
        left_panel = ttk.Frame(main_frame, style="Panel.TFrame", padding=20)
        left_panel.pack(side=tk.LEFT, fill=tk.Y)
        
        # Título
        ttk.Label(left_panel, text="RR3 AUTOBOT", style="Header.TLabel").pack(pady=(0, 20), anchor=tk.W) # Reduced pady

        # Control Card
        control_frame = ttk.LabelFrame(left_panel, text="CONTROL", style="Card.TLabelframe", padding=15)
        control_frame.pack(fill=tk.X, pady=(0, 15)) # Reduced pady
        
        self.btn_start = ttk.Button(control_frame, text="▶ INICIAR", command=self.start_bot, style="Action.TButton")
        self.btn_start.pack(fill=tk.X, pady=(0, 10))
        
        self.btn_stop = ttk.Button(control_frame, text="⏹ DETENER", command=self.stop_bot, state=tk.DISABLED, style="Action.TButton")
        self.btn_stop.pack(fill=tk.X)
        
        self.lbl_status = ttk.Label(control_frame, text="• Listo", style="Status.TLabel", wraplength=180)
        self.lbl_status.pack(pady=(10, 0), anchor=tk.W)

        # Stats Card
        # Usamos Frame normal en lugar de LabelFrame para personalizar el header
        stats_card = ttk.Frame(left_panel, style="Card.TLabelframe", padding=2) # Simulate border/bg
        stats_card.pack(fill=tk.X)
        
        # Inner Frame for content
        stats_inner = tk.Frame(stats_card, bg="#243B53", padx=10, pady=10) # Reduced padding
        stats_inner.pack(fill=tk.BOTH, expand=True)

        # Custom Header inside Card
        header_frame = tk.Frame(stats_inner, bg="#243B53")
        header_frame.pack(fill=tk.X, pady=(0, 10)) # Reduced pady
        
        ttk.Label(header_frame, text="MÉTRICAS", style="Card.TLabelframe.Label", background="#243B53").pack(side=tk.LEFT)
        
        # Graph Button (Small, Icon only)
        btn_graph = tk.Button(header_frame, text="📊", font=("Segoe UI Emoji", 12), 
                            bg="#243B53", fg="#4FD1C5", bd=0, relief="flat", highlightthickness=0,
                            activebackground="#243B53", activeforeground="#4FD1C5",
                            cursor="hand2", command=self._show_history_chart)
        btn_graph.pack(side=tk.RIGHT)
        
        # Calendar Button
        btn_calendar = tk.Button(header_frame, text="📅", font=("Segoe UI Emoji", 12), 
                            bg="#243B53", fg="#F6E05E", bd=0, relief="flat", highlightthickness=0,
                            activebackground="#243B53", activeforeground="#F6E05E",
                            cursor="hand2", command=self._show_calendar_view)
        btn_calendar.pack(side=tk.RIGHT, padx=(0, 5))
        
        # Stats Content
        def add_stat(label, color="#F0F4F8"):
            ttk.Label(stats_inner, text=label, style="Stat.TLabel", background="#243B53").pack(anchor=tk.W)
            lbl = ttk.Label(stats_inner, text="--", style="StatValue.TLabel", background="#243B53", foreground=color)
            lbl.pack(anchor=tk.W, pady=(0, 5)) # Reduced pady significantly
            return lbl

        self.lbl_gold = add_stat("ORO GANADO (SESIÓN)", "#F6E05E")
        self.lbl_runtime = add_stat("TIEMPO EJECUCIÓN", "#4FD1C5")
        self.lbl_gold_speed = add_stat("RITMO (ORO/HORA)", "#F6E05E")
        self.lbl_speed = add_stat("VELOCIDAD (ADs/H)", "#63B3ED")
        self.lbl_gold_history = add_stat("TOTAL HISTÓRICO", "#CBD5E0")
        
        # Set initial values
        self.lbl_runtime.config(text="00:00:00")

        # Font override removed to use style defaults

        # --- Main Area (Panel Derecho) ---
        right_panel = ttk.Frame(main_frame, style="Main.TFrame", padding=20)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Live View
        ttk.Label(right_panel, text="VISTA EN VIVO", background="#102A43", foreground="#829AB1", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0,5))
        
        preview_container = tk.Frame(right_panel, bg="#102A43", bd=0, highlightthickness=2, highlightbackground="#243B53")
        preview_container.pack(anchor=tk.W, pady=(0, 20))
        
        self.canvas = tk.Canvas(preview_container, width=640, height=360, bg="#102A43", highlightthickness=0)
        self.canvas.pack()
        
        # Logs
        ttk.Label(right_panel, text="REGISTRO DE ACTIVIDAD", background="#102A43", foreground="#829AB1", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0,5))
        
        self.log_area = scrolledtext.ScrolledText(right_panel, height=8, state=tk.DISABLED, 
                                                  font=("Consolas", 10), 
                                                  bg="#0F2439", fg="#D9E2EC", 
                                                  relief="flat", padx=10, pady=10,
                                                  insertbackground="white") # Cursor white
        self.log_area.pack(fill=tk.BOTH, expand=True)
        
        # Log Tags Configuration
        self.log_area.tag_config("gold", foreground="#F6E05E")     # Yellow
        self.log_area.tag_config("error", foreground="#FC8181")    # Red
        self.log_area.tag_config("state", foreground="#63B3ED")    # Blue
        self.log_area.tag_config("success", foreground="#68D391")  # Green
        self.log_area.tag_config("highlight", foreground="#D9E2EC", font=("Consolas", 10, "bold")) # Bright White

    # Métodos de calibración eliminados (save_calibration, load_calibration, _update_calib_label, start_calibration, _calibration_thread)



    # test_click removed
             
    # start_calibration y _calibration_thread eliminados

    def log_message(self, msg):
        self.log_queue.put(msg)

    def update_image(self, cv2_image):
        if cv2_image is not None:
            self.image_queue.put(cv2_image)
            
    def update_stats(self, todays_total_gold, total_history=0, ads_per_hour=0, gold_per_hour=0):
        # Programar actualización en el hilo principal
        def _update():
            # Calcular oro de sesión real (Total Hoy - Inicial al empezar sesión)
            # Si no estamos corriendo, mostramos 0 o el último valor
            session_val = 0
            if self.is_bot_running and self.session_initial_gold >= 0:
                session_val = max(0, todays_total_gold - self.session_initial_gold)
            
            self.current_session_gold = session_val # Guardar para logging

            # Use formatting with separators for thousands
            self.lbl_gold.config(text=f"{session_val:,}")
            self.lbl_gold_history.config(text=f"{total_history:,}")
            self.lbl_speed.config(text=f"{ads_per_hour:.1f} /h")
            self.lbl_gold_speed.config(text=f"{int(gold_per_hour):,} /h")
        self.root.after(0, _update)

    def _start_queue_processing(self):
        self._process_logs()
        self._process_images()
        
    def _process_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_area.config(state=tk.NORMAL)
            
            # Map icons to tags
            icon_map = {
                "💰": "gold", "🤑": "gold",
                "⚠": "error", "❌": "error", "Error": "error",
                "🔄": "state", 
                "✅": "success", "Listo": "success",
                "👀": "state", "👉": "state", "🔍": "state", "⌨": "state", "🖱": "state"
            }
            
            found_icon = None
            tag_to_use = None
            
            # Find first matching icon
            for icon, tag in icon_map.items():
                if icon in msg:
                    found_icon = icon
                    tag_to_use = tag
                    break
            
            if found_icon:
                parts = msg.split(found_icon, 1)
                self.log_area.insert(tk.END, parts[0]) # Timestamp / Prefix
                self.log_area.insert(tk.END, found_icon, tag_to_use) # Colored Icon
                self.log_area.insert(tk.END, parts[1] + "\n") # Rest of text
            else:
                self.log_area.insert(tk.END, msg + "\n")

            self.log_area.see(tk.END)
            self.log_area.config(state=tk.DISABLED)
            
            # Actualizar status label si el mensaje parece un estado
            if "Estado:" in msg or "CAMBIO ESTADO:" in msg:
                clean_msg = msg.split("]")[-1].strip() # Limpiar timestamp si se desea
                # Opcional: Filtrar solo el nuevo estado
                if "CAMBIO ESTADO" in msg:
                     # Parsear "CAMBIO ESTADO: X -> Y" => Mostrar "Estado: Y"
                     parts = msg.split("->")
                     if len(parts) > 1:
                         new_state = parts[-1].strip()
                         clean_msg = f"• Estado: {new_state}"
                
                self.lbl_status.config(text=clean_msg)
                
        self.root.after(100, self._process_logs)

    def _process_images(self):
        try:
            # Consumir la última imagen y descartar anteriores para no laggy
            latest_image = None
            while not self.image_queue.empty():
                latest_image = self.image_queue.get_nowait()
            
            if latest_image is not None:
                # Convertir CV2 (BGR) a PIL (RGB)
                rgb_image = cv2.cvtColor(latest_image, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_image)
                
                # Resize manteniendo aspect ratio
                target_w, target_h = 640, 360
                ratio = min(target_w / pil_image.width, target_h / pil_image.height)
                new_w = int(pil_image.width * ratio)
                new_h = int(pil_image.height * ratio)
                
                pil_image = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                
                self.photo = ImageTk.PhotoImage(pil_image)
                
                # Centrar en canvas
                x_pos = (target_w - new_w) // 2
                y_pos = (target_h - new_h) // 2
                
                self.canvas.delete("all")
                self.canvas.create_image(x_pos, y_pos, image=self.photo, anchor=tk.NW)
        except Exception:
            pass
            
        self.root.after(200, self._process_images)

    def _run_idle_preview(self):
        """Toma capturas periodicas cuando el bot no está corriendo."""
        while True:
            if not self.is_bot_running:
                try:
                    # Usamos take_screenshot del wrapper (fix SD card ya implementado alli)
                    # Hemos añadido timeout en adb_wrapper para que esto no bloquee
                    img = self.adb_preview.take_screenshot()
                    if img is not None:
                        self.update_image(img)
                except Exception as e:
                    print(f"Error preview idle: {e}")
                    time.sleep(2) # Espera extra si falla
                
                time.sleep(1.5) # 1.5s refresh rate pare idle
            else:
                time.sleep(1) # Dormir mientras el bot corre (él manda las imagenes)

    def start_bot(self):
        if self.bot_thread and self.bot_thread.is_alive():
            return
        
        self.is_bot_running = True
        self.stop_event.clear()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.lbl_status.config(text="• Iniciando...", foreground="#63B3ED")
        
        self.bot_thread = threading.Thread(target=self._run_bot_thread, daemon=True)
        self.bot_thread.start()
        
        # Start Session Tracking
        self.session_start_time = datetime.now()
        self.session_initial_gold = self.logger.get_todays_gold() # Snapshot inicio
        self.current_session_gold = 0
        self._update_runtime_timer()

    def _update_runtime_timer(self):
        if self.is_bot_running and self.session_start_time:
            delta = datetime.now() - self.session_start_time
            # Format HH:MM:SS
            total_seconds = int(delta.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            time_str = f"{hours:02}:{minutes:02}:{seconds:02}"
            self.lbl_runtime.config(text=time_str)
            
            self.root.after(1000, self._update_runtime_timer)

    def stop_bot(self):
        if self.bot_thread and self.bot_thread.is_alive():
            self.log_message("Deteniendo bot... espere a que termine la acción actual.")
            self.stop_event.set()
            self.lbl_status.config(text="• Deteniendo...", foreground="#FC8181")
            self.btn_stop.config(state=tk.DISABLED)
            # El botón de iniciar se reactivará cuando muera el hilo

    def _run_bot_thread(self):
        try:
            if not RealRacingBot:
                self.log_message("Error: Clase RealRacingBot no encontrada.")
                return

            self.bot_instance = RealRacingBot(
                stop_event=self.stop_event,
                log_callback=self.log_message,
                image_callback=self.update_image,
                stats_callback=self.update_stats
            )
            self.bot_instance.run()
        except Exception as e:
            self.log_message(f"Error crítico en bot: {e}")
        finally:
            # Log Session End
            if self.session_start_time:
                end_time = datetime.now()
                # Log to DB
                self.logger.log_session(self.session_start_time, end_time, self.current_session_gold)
                self.session_start_time = None # Stop timer loop logic check

            self.log_message("Bot detenido.")
            self.root.after(0, self._reset_buttons)

    def _show_history_chart(self):
        """Muestra popup con gráfica de barras de últimos 7 días con auto-refresh."""
        # Popup setup
        popup = tk.Toplevel(self.root)
        popup.title("Historial de Ganancias")
        popup.geometry("600x400")
        popup.configure(bg="#102A43")
        
        # Header
        ttk.Label(popup, text="Últimos 7 Días", font=("Segoe UI", 16, "bold"), background="#102A43", foreground="#D9E2EC").pack(pady=10)
        
        # Canvas
        cw, ch = 550, 300
        canvas = tk.Canvas(popup, width=cw, height=ch, bg="#1E3246", highlightthickness=0)
        canvas.pack(pady=10, padx=20)
        
        def _refresh_data():
            # Check if popup still valid
            try:
                if not popup.winfo_exists(): return
            except:
                return
                
            canvas.delete("all")
            data = self.logger.get_daily_history(7)
            
            if not data:
                canvas.create_text(cw/2, ch/2, text="Sin datos...", fill="#829AB1", font=("Segoe UI", 12))
            else:
                # Draw Logic
                max_val = max(d[1] for d in data) if data else 1
                bar_width = cw / len(data) * 0.6
                spacing = cw / len(data) * 0.4
                
                # Margins
                margin_bottom = 30
                margin_top = 20
                draw_h = ch - margin_bottom - margin_top
                
                x_start = spacing / 2
                
                for i, (date_str, amount) in enumerate(data):
                    # Height relative to max
                    h_bar = (amount / max_val) * draw_h
                    if h_bar < 2: h_bar = 2 # min visible
                    
                    x0 = x_start + i * (bar_width + spacing)
                    y0 = ch - margin_bottom
                    x1 = x0 + bar_width
                    y1 = y0 - h_bar
                    
                    # Color based on amount?
                    color = "#4FD1C5" if amount > 50 else "#63B3ED"
                    
                    # Bar
                    canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
                    
                    # Value Label
                    canvas.create_text((x0+x1)/2, y1 - 10, text=f"{amount}", fill="#FFFFFF", font=("Segoe UI", 8))
                    
                    # Date Label (dd-mm-yy)
                    # date_str is YYYY-MM-DD
                    try:
                        y, m, d = date_str.split('-')
                        formatted_date = f"{d}-{m}-{y[2:]}"
                    except:
                        formatted_date = date_str
                        
                    canvas.create_text((x0+x1)/2, y0 + 15, text=formatted_date, fill="#829AB1", font=("Segoe UI", 8))
            
            # Schedule next refresh in 60s
            popup.after(60000, _refresh_data)

        # First trigger
        _refresh_data()


    def _show_calendar_view(self):
        """Muestra popup con vista de calendario mensual navegable."""
        import calendar
        
        popup = tk.Toplevel(self.root)
        popup.title("Calendario de Ganancias")
        popup.geometry("500x420")
        popup.configure(bg="#102A43")
        
        # Estado del mes actual
        current_date = [datetime.now().year, datetime.now().month]
        
        # Header con navegacion
        header = tk.Frame(popup, bg="#102A43")
        header.pack(fill=tk.X, padx=20, pady=10)
        
        btn_prev = tk.Button(header, text="◀", font=("Segoe UI", 14), 
                            bg="#102A43", fg="#4FD1C5", bd=0, cursor="hand2",
                            command=lambda: navigate(-1))
        btn_prev.pack(side=tk.LEFT)
        
        lbl_month = tk.Label(header, text="", font=("Segoe UI", 16, "bold"), 
                            bg="#102A43", fg="#D9E2EC")
        lbl_month.pack(side=tk.LEFT, expand=True)
        
        btn_next = tk.Button(header, text="▶", font=("Segoe UI", 14), 
                            bg="#102A43", fg="#4FD1C5", bd=0, cursor="hand2",
                            command=lambda: navigate(1))
        btn_next.pack(side=tk.RIGHT)
        
        # Canvas para el calendario
        cal_frame = tk.Frame(popup, bg="#1E3246")
        cal_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Dias de la semana
        days_header = tk.Frame(cal_frame, bg="#1E3246")
        days_header.pack(fill=tk.X)
        for day_name in ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]:
            tk.Label(days_header, text=day_name, width=6, font=("Segoe UI", 9, "bold"),
                    bg="#1E3246", fg="#829AB1").pack(side=tk.LEFT, padx=2)
        
        # Grid de dias
        days_grid = tk.Frame(cal_frame, bg="#1E3246")
        days_grid.pack(fill=tk.BOTH, expand=True, pady=5)
        
        day_labels = []
        for row in range(6):
            row_frame = tk.Frame(days_grid, bg="#1E3246")
            row_frame.pack(fill=tk.X)
            row_labels = []
            for col in range(7):
                lbl = tk.Label(row_frame, text="", width=6, height=2, font=("Segoe UI", 9),
                              bg="#243B53", fg="#D9E2EC", relief="flat")
                lbl.pack(side=tk.LEFT, padx=2, pady=2)
                row_labels.append(lbl)
            day_labels.append(row_labels)
        
        def get_month_data(year, month):
            """Obtiene datos de oro para el mes."""
            try:
                with sqlite3.connect(self.logger.db_path) as conn:
                    query = """
                        SELECT substr(timestamp, 1, 10) as day, SUM(amount)
                        FROM gold_history
                        WHERE timestamp LIKE ?
                        GROUP BY day
                    """
                    pattern = f"{year:04d}-{month:02d}-%"
                    cursor = conn.execute(query, (pattern,))
                    return {row[0]: row[1] for row in cursor.fetchall()}
            except:
                return {}
        
        def refresh_calendar():
            year, month = current_date
            month_names = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                          "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
            lbl_month.config(text=f"{month_names[month]} {year}")
            
            # Obtener datos del mes
            month_data = get_month_data(year, month)
            
            # Calcular grid del calendario
            cal = calendar.Calendar(firstweekday=0)  # Lunes primero
            month_days = cal.monthdayscalendar(year, month)
            
            # Limpiar y rellenar
            for row_idx, row_labels in enumerate(day_labels):
                for col_idx, lbl in enumerate(row_labels):
                    if row_idx < len(month_days):
                        day = month_days[row_idx][col_idx]
                        if day == 0:
                            lbl.config(text="", bg="#1E3246")
                        else:
                            day_str = f"{year:04d}-{month:02d}-{day:02d}"
                            gold = month_data.get(day_str, 0)
                            
                            # Color segun oro
                            if gold > 100:
                                bg_color = "#276749"  # Verde oscuro
                                fg_color = "#F6E05E"
                            elif gold > 0:
                                bg_color = "#2C5282"  # Azul
                                fg_color = "#F6E05E"
                            else:
                                bg_color = "#243B53"
                                fg_color = "#829AB1"
                            
                            display = f"{day}\n{gold}" if gold > 0 else str(day)
                            lbl.config(text=display, bg=bg_color, fg=fg_color)
                    else:
                        lbl.config(text="", bg="#1E3246")
        
        def navigate(delta):
            current_date[1] += delta
            if current_date[1] > 12:
                current_date[1] = 1
                current_date[0] += 1
            elif current_date[1] < 1:
                current_date[1] = 12
                current_date[0] -= 1
            refresh_calendar()
        
        # Necesitamos importar sqlite3 para la query
        import sqlite3
        
        refresh_calendar()

    def _reset_buttons(self):
        self.is_bot_running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_status.config(text="• Detenido", foreground="#A0AEC0")

    # open_scrcpy removed

def main():
    root = tk.Tk()
    # Intentar cargar icono si existe
    # root.iconbitmap("assets/icon.ico") 
    app = BotGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
