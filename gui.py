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
from ml.trainer import ModelTrainer
from ml.evaluator import ModelEvaluator
from ml.monitor import LiveMonitor


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
        BG_PANEL = "#1E3246"  # Sidebar / Panel
        BG_CARD = "#243B53"   # Cards
        FG_TEXT = "#D9E2EC"   # Text
        ACCENT = "#334E68"
        BTN_BG = "#2B6CB0"    # Vivid Blue
        BTN_FG = "#FFFFFF"
        BTN_ACTIVE = "#3182CE"

        style.configure(".", background=BG_MAIN, foreground=FG_TEXT, font=("Segoe UI", 10))
        
        # Custom Frames
        style.configure("Main.TFrame", background=BG_MAIN)
        style.configure("Panel.TFrame", background=BG_PANEL)
        
        # Cards
        style.configure("Card.TLabelframe", background=BG_CARD, bordercolor=BG_MAIN, relief="flat")
        style.configure("Card.TLabelframe.Label", background=BG_CARD, foreground="#829AB1", font=("Segoe UI", 9, "bold"))
        
        # Labels
        style.configure("TLabel", background=BG_MAIN, foreground=FG_TEXT)
        style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG_TEXT)
        style.configure("Header.TLabel", font=("Segoe UI", 20, "bold"), foreground="#627D98", background=BG_PANEL)
        
        style.configure("Stat.TLabel", background=BG_PANEL, foreground="#829AB1", font=("Segoe UI", 8)) 
        style.configure("StatValue.TLabel", background=BG_PANEL, font=("Segoe UI", 14, "bold")) 
        style.configure("Status.TLabel", background=BG_PANEL, foreground="#48BB78", font=("Segoe UI", 11, "bold"))

        # Buttons
        style.configure("Action.TButton", padding=10, relief="flat", background=BTN_BG, foreground=BTN_FG, borderwidth=0, font=("Segoe UI", 10, "bold"))
        style.map("Action.TButton", background=[('active', BTN_ACTIVE)])
        
        style.configure("Small.TButton", padding=5, relief="flat", background=ACCENT, foreground=FG_TEXT, borderwidth=0, font=("Segoe UI", 8))

    def _setup_ui(self):
        # Master Container 3 Columnas
        main_container = ttk.Frame(self.root, style="Main.TFrame")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # =========================================================================
        # COLUMNA 1: IZQUIERDA (CONTROL) (20%)
        # =========================================================================
        left_panel = ttk.Frame(main_container, style="Panel.TFrame", padding=15)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0,1))
        
        # LOGO / HEADER
        ttk.Label(left_panel, text="RR3\nCOMMAND\nCENTER", style="Header.TLabel", justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 25))

        # CONTROL PRINCIPAL
        ttk.Label(left_panel, text="CONTROL DE MISIÓN", style="Stat.TLabel").pack(anchor=tk.W, pady=(0,5))
        
        self.btn_start = ttk.Button(left_panel, text="▶ INICIAR OPERACIÓN", command=self.start_bot, style="Action.TButton")
        self.btn_start.pack(fill=tk.X, pady=(0, 8))
        
        self.btn_stop = ttk.Button(left_panel, text="⏹ DETENER", command=self.stop_bot, state=tk.DISABLED, style="Action.TButton")
        self.btn_stop.pack(fill=tk.X, pady=(0, 20))
        
        # STATUS INDICATOR
        self.status_frame = tk.Frame(left_panel, bg="#1E3246")
        self.status_frame.pack(fill=tk.X, pady=(0, 20))
        tk.Label(self.status_frame, text="ESTADO ACTUAL", fg="#829AB1", bg="#1E3246", font=("Segoe UI", 8)).pack(anchor=tk.W)
        
        self.lbl_status = tk.Label(self.status_frame, text="INACTIVO", fg="#A0AEC0", bg="#1E3246", font=("Segoe UI", 12, "bold"))
        self.lbl_status.pack(anchor=tk.W)
        
        # ML NEURAL NET SECTION
        ttk.Label(left_panel, text="RED NEURONAL (BRAIN)", style="Stat.TLabel").pack(anchor=tk.W, pady=(10,5))
        
        ml_frame = tk.Frame(left_panel, bg="#1E3246")
        ml_frame.pack(fill=tk.X)
        
        # Buttons ML Grid
        self.btn_ml_train = tk.Button(ml_frame, text="🧠 Entrenar", bg="#4A5568", fg="white", bd=0, command=self._ml_train, cursor="hand2")
        self.btn_ml_train.pack(fill=tk.X, pady=2)
        
        self.btn_ml_test = tk.Button(ml_frame, text="🧪 Testear", bg="#38A169", fg="white", bd=0, command=self._ml_test, cursor="hand2")
        self.btn_ml_test.pack(fill=tk.X, pady=2)
        
        self.btn_ml_activate = tk.Button(ml_frame, text="⚡ Activar Monitor", bg="#805AD5", fg="white", bd=0, command=self._ml_toggle_monitor, cursor="hand2")
        self.btn_ml_activate.pack(fill=tk.X, pady=2)
        
        self.lbl_ml_status = tk.Label(ml_frame, text="Ready", bg="#1E3246", fg="#718096", font=("Segoe UI", 8))
        self.lbl_ml_status.pack(anchor=tk.W, pady=(5,0))

        # =========================================================================
        # COLUMNA 2: CENTRO (VISION + LOGS) (55%)
        # =========================================================================
        center_panel = ttk.Frame(main_container, style="Main.TFrame", padding=15)
        center_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # LOGS HEADER
        log_header = tk.Frame(center_panel, bg="#102A43")
        log_header.pack(fill=tk.X, pady=(0, 5))
        tk.Label(log_header, text="TERMINAL DE REGISTRO", fg="#627D98", bg="#102A43", font=("Consolas", 10, "bold")).pack(side=tk.LEFT)
        
        # LOG AREA (Arriba)
        self.log_area = scrolledtext.ScrolledText(center_panel, height=12, state=tk.DISABLED, 
                                                  font=("Consolas", 10), 
                                                  bg="#0F2439", fg="#D9E2EC", 
                                                  relief="flat", padx=10, pady=10,
                                                  insertbackground="white")
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        self._configure_log_tags()

        # LIVE VIEW HEADER
        view_header = tk.Frame(center_panel, bg="#102A43")
        view_header.pack(fill=tk.X, pady=(0, 5))
        tk.Label(view_header, text="VISIÓN EN TIEMPO REAL (ADB LIVE)", fg="#627D98", bg="#102A43", font=("Consolas", 10, "bold")).pack(side=tk.LEFT)
        
        # PREVIEW CONTAINER (Abajo)
        # Ratio 16:9 for 640px width -> 360px height
        self.preview_frame = tk.Frame(center_panel, bg="#000000", width=640, height=360)
        self.preview_frame.pack(anchor=tk.CENTER)
        self.preview_frame.pack_propagate(False) # Force size
        
        self.canvas = tk.Canvas(self.preview_frame, width=640, height=360, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # =========================================================================
        # COLUMNA 3: DERECHA (METRICAS) (25%)
        # =========================================================================
        right_panel = ttk.Frame(main_container, style="Panel.TFrame", padding=15)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(1,0))
        
        ttk.Label(right_panel, text="RENDIMIENTO", style="Stat.TLabel").pack(anchor=tk.W, pady=(0,15))
        
        # SESSION TIMER
        self.lbl_runtime = self._create_stat_block(right_panel, "TIEMPO SESIÓN", "00:00:00", "#63B3ED")
        
        # GOLD SESSION
        self.lbl_gold = self._create_stat_block(right_panel, "ORO (SESIÓN)", "0", "#F6E05E")
        
        # GOLD RATE
        self.lbl_gold_speed = self._create_stat_block(right_panel, "RITMO (GC/H)", "0", "#F6E05E")
        
        # ADS RATE
        self.lbl_speed = self._create_stat_block(right_panel, "VELOCIDAD (ADS/H)", "0.0", "#63B3ED")
        
        # TOTAL HISTORY
        self.lbl_gold_history = self._create_stat_block(right_panel, "TOTAL HISTÓRICO", "--", "#CBD5E0")
        
        # GRAPHS & CALENDAR
        btn_frame = tk.Frame(right_panel, bg="#1E3246")
        btn_frame.pack(fill=tk.X, pady=20)
        
        tk.Button(btn_frame, text="📊 Ver Gráfica", bg="#2D3748", fg="white", bd=0, pady=5, command=self._show_history_chart).pack(fill=tk.X, pady=2)
        tk.Button(btn_frame, text="📅 Calendario", bg="#2D3748", fg="white", bd=0, pady=5, command=self._show_calendar_view).pack(fill=tk.X, pady=2)
        
        # ML METRICS MINI-DASH
        ttk.Label(right_panel, text="MÉTRICAS ML", style="Stat.TLabel").pack(anchor=tk.W, pady=(20,10))
        
        self.lbl_ml_accuracy = self._create_metric_row(right_panel, "Precisión", "N/A", "#9F7AEA")
        self.lbl_ml_samples = self._create_metric_row(right_panel, "Capturas", "0", "#A0AEC0")
        self.lbl_ml_concordance = self._create_metric_row(right_panel, "Concordancia", "--", "#A0AEC0")

        # Initialize ML components
        self._init_ml_components()

    def _create_stat_block(self, parent, label, initial, color):
        frame = tk.Frame(parent, bg="#1E3246")
        frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(frame, text=label, fg="#829AB1", bg="#1E3246", font=("Segoe UI", 9)).pack(anchor=tk.W)
        lbl = tk.Label(frame, text=initial, fg=color, bg="#1E3246", font=("Segoe UI", 20, "bold"))
        lbl.pack(anchor=tk.W)
        return lbl

    def _create_metric_row(self, parent, label, initial, color):
        frame = tk.Frame(parent, bg="#1E3246")
        frame.pack(fill=tk.X, pady=2)
        tk.Label(frame, text=label, fg="#829AB1", bg="#1E3246", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        lbl = tk.Label(frame, text=initial, fg=color, bg="#1E3246", font=("Segoe UI", 9, "bold"))
        lbl.pack(side=tk.RIGHT)
        return lbl

    def _configure_log_tags(self):
        self.log_area.tag_config("gold", foreground="#F6E05E")     # Yellow
        self.log_area.tag_config("error", foreground="#FC8181")    # Red
        self.log_area.tag_config("state", foreground="#63B3ED")    # Blue
        self.log_area.tag_config("success", foreground="#68D391")  # Green
        self.log_area.tag_config("highlight", foreground="#D9E2EC", font=("Consolas", 10, "bold"))


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
            # Actualizar status label si el mensaje parece un estado
            if "Estado:" in msg or "CAMBIO ESTADO:" in msg:
                clean_msg = ""
                # Caso 1: Cambio de estado explícito
                if "CAMBIO ESTADO" in msg:
                     # Parsear "CAMBIO ESTADO: X -> Y" => Mostrar "Y"
                     parts = msg.split("->")
                     if len(parts) > 1:
                         new_state = parts[-1].strip()
                         clean_msg = new_state
                # Caso 2: Mensaje de "Estado:" (log directo)
                elif "Estado:" in msg:
                    # Limpiar timestamp y prefijo
                    clean_msg = msg.split("]")[-1].strip()
                    if "Estado:" in clean_msg:
                        clean_msg = clean_msg.split("Estado:")[-1].strip()
                    # Quitar el bullet si lo hubiera
                    clean_msg = clean_msg.replace("•", "").strip()
                
                if clean_msg:
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
        self.lbl_status.config(text="Iniciando...", foreground="#63B3ED")
        
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
            self.lbl_status.config(text="Deteniendo...", foreground="#FC8181")
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


    def _init_ml_components(self):
        """Inicializa componentes ML."""
        try:
            self.ml_trainer = ModelTrainer()
            self.ml_evaluator = ModelEvaluator()
            self.ml_monitor = LiveMonitor()
            self._update_ml_stats()
            # Iniciar actualizacion periodica (cada 5 segundos)
            self._schedule_ml_stats_update()
        except Exception as e:
            print(f"Error inicializando ML: {e}")
            self.ml_trainer = None
            self.ml_evaluator = None
            self.ml_monitor = None
    
    def _schedule_ml_stats_update(self):
        """Actualiza stats ML periodicamente."""
        self._update_ml_stats()
        self.root.after(5000, self._schedule_ml_stats_update)  # Cada 5 segundos
    
    def _update_ml_stats(self):
        """Actualiza estadisticas ML en la GUI."""
        if not hasattr(self, 'ml_trainer') or not self.ml_trainer:
            return
        
        # Accuracy
        if hasattr(self.ml_evaluator, 'accuracy') and self.ml_evaluator.accuracy > 0:
            self.lbl_ml_accuracy.config(text=f"{self.ml_evaluator.accuracy:.1f}%")
        
        # Capturas nuevas
        samples = self.ml_trainer.get_sample_count()
        color = "#68D391" if samples >= 500 else "#FC8181"  # Verde si >500, rojo si <500
        self.lbl_ml_samples.config(text=str(samples), fg=color)
        
        # Concordancia (si monitor activo)
        if hasattr(self, 'ml_monitor') and self.ml_monitor and self.ml_monitor.is_active:
            stats = self.ml_monitor.get_stats()
            conc = stats.get('concordance', 0)
            if conc >= 99:
                color = "#68D391"  # Verde
            elif conc >= 97:
                color = "#63B3ED"  # Azul
            else:
                color = "#FC8181"  # Rojo
            self.lbl_ml_concordance.config(text=f"{conc:.1f}%", fg=color)
        else:
            self.lbl_ml_concordance.config(text="--", fg="#A0AEC0")
    
    def _ml_train(self):
        """Inicia entrenamiento del modelo."""
        if not self.ml_trainer:
            self.lbl_ml_status.config(text="Error: ML no inicializado")
            return
        
        if self.ml_trainer.is_training:
            self.lbl_ml_status.config(text="Entrenamiento en curso...")
            return
        
        samples = self.ml_trainer.get_sample_count()
        if samples < 10:
            self.lbl_ml_status.config(text=f"Error: Solo {samples} muestras (min 10)")
            return
        
        self.btn_ml_train.config(state=tk.DISABLED)
        self.lbl_ml_status.config(text="Iniciando entrenamiento...")
        
        def on_complete(success, accuracy):
            self.root.after(0, lambda: self._on_training_complete(success, accuracy))
        
        self.ml_trainer.train(epochs=10, callback=on_complete)
        
        # Iniciar timer para actualizar progreso
        self._update_training_progress()
    
    def _update_training_progress(self):
        """Actualiza progreso de entrenamiento."""
        if not self.ml_trainer or not self.ml_trainer.is_training:
            return
        
        # Obtener logs
        logs = self.ml_trainer.get_logs()
        for log in logs:
            self.lbl_ml_status.config(text=log)
        
        # Actualizar cada 500ms
        self.root.after(500, self._update_training_progress)
    
    def _on_training_complete(self, success, accuracy):
        """Callback cuando termina el entrenamiento."""
        self.btn_ml_train.config(state=tk.NORMAL)
        if success:
            self.lbl_ml_status.config(text=f"Completado! Accuracy: {accuracy:.1f}%")
            self.lbl_ml_accuracy.config(text=f"{accuracy:.1f}%")
        else:
            self.lbl_ml_status.config(text="Error en entrenamiento")
        self._update_ml_stats()
    
    def _ml_test(self):
        """Ejecuta test del modelo."""
        if not self.ml_evaluator:
            self.lbl_ml_status.config(text="Error: ML no inicializado")
            return
        
        self.lbl_ml_status.config(text="Evaluando modelo...")
        self.btn_ml_test.config(state=tk.DISABLED)
        
        def _run_test():
            result = self.ml_evaluator.evaluate()
            self.root.after(0, lambda: self._on_test_complete(result))
        
        import threading
        threading.Thread(target=_run_test, daemon=True).start()
    
    def _on_test_complete(self, result):
        """Callback cuando termina el test."""
        self.btn_ml_test.config(state=tk.NORMAL)
        if "error" in result:
            self.lbl_ml_status.config(text=f"Error: {result['error']}")
        else:
            acc = result.get('accuracy', 0)
            total = result.get('total_samples', 0)
            self.lbl_ml_status.config(text=f"Test: {acc:.1f}% ({total} muestras)")
            self.lbl_ml_accuracy.config(text=f"{acc:.1f}%")
    
    def _ml_toggle_monitor(self):
        """Activa/desactiva monitor en tiempo real."""
        if not self.ml_monitor:
            self.lbl_ml_status.config(text="Error: ML no inicializado")
            return
        
        if self.ml_monitor.is_active:
            self.ml_monitor.stop()
            self.btn_ml_activate.config(text="Activar", bg="#805AD5")
            self.lbl_ml_status.config(text="Monitor detenido")
            self.lbl_ml_concordance.config(text="--", fg="#A0AEC0")
        else:
            if not self.ml_monitor.model.is_trained:
                self.lbl_ml_status.config(text="Error: Modelo no entrenado")
                return
            self.ml_monitor.start()
            self.btn_ml_activate.config(text="Detener", bg="#E53E3E")
            self.lbl_ml_status.config(text="Monitor activo")
            self._update_monitor_stats()
    
    def _update_monitor_stats(self):
        """Actualiza estadisticas del monitor."""
        if not self.ml_monitor or not self.ml_monitor.is_active:
            return
        
        stats = self.ml_monitor.get_stats()
        conc = stats.get('concordance', 0)
        
        if conc >= 99:
            color = "#68D391"  # Verde
        elif conc >= 97:
            color = "#63B3ED"  # Azul
        else:
            color = "#FC8181"  # Rojo
        
        self.lbl_ml_concordance.config(text=f"{conc:.1f}%", fg=color)
        
        # Actualizar cada segundo
        self.root.after(1000, self._update_monitor_stats)

    def _reset_buttons(self):
        self.is_bot_running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_status.config(text="Detenido", foreground="#A0AEC0")

    # open_scrcpy removed

def main():
    root = tk.Tk()
    # Intentar cargar icono si existe
    # root.iconbitmap("assets/icon.ico") 
    app = BotGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
