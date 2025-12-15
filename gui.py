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
from adb_wrapper import ADBWrapper


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
        style.configure("Stat.TLabel", background=BG_CARD, foreground="#829AB1", font=("Segoe UI", 10))
        style.configure("StatValue.TLabel", background=BG_CARD, font=("Segoe UI", 20, "bold"))
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
        ttk.Label(left_panel, text="RR3 AUTOBOT", style="Header.TLabel").pack(pady=(0, 25), anchor=tk.W)

        # Control Card
        control_frame = ttk.LabelFrame(left_panel, text="CONTROL", style="Card.TLabelframe", padding=15)
        control_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.btn_start = ttk.Button(control_frame, text="▶ INICIAR", command=self.start_bot, style="Action.TButton")
        self.btn_start.pack(fill=tk.X, pady=(0, 10))
        
        self.btn_stop = ttk.Button(control_frame, text="⏹ DETENER", command=self.stop_bot, state=tk.DISABLED, style="Action.TButton")
        self.btn_stop.pack(fill=tk.X)
        
        self.lbl_status = ttk.Label(control_frame, text="• Listo", style="Status.TLabel", wraplength=180)
        self.lbl_status.pack(pady=(15, 0), anchor=tk.W)

        # Stats Card
        stats_frame = ttk.LabelFrame(left_panel, text="MÉTRICAS", style="Card.TLabelframe", padding=15)
        stats_frame.pack(fill=tk.X)
        
        def add_stat(label, color="#F0F4F8"):
            ttk.Label(stats_frame, text=label, style="Stat.TLabel").pack(anchor=tk.W)
            lbl = ttk.Label(stats_frame, text="--", style="StatValue.TLabel", foreground=color)
            lbl.pack(anchor=tk.W, pady=(0, 15))
            return lbl

        self.lbl_gold = add_stat("ORO GANADO (SESIÓN)", "#F6E05E")
        self.lbl_gold_speed = add_stat("RITMO (ORO/HORA)", "#F6E05E")
        self.lbl_speed = add_stat("VELOCIDAD (ADs/H)", "#63B3ED")
        self.lbl_gold_history = add_stat("TOTAL HISTÓRICO", "#CBD5E0")

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

    # Métodos de calibración eliminados (save_calibration, load_calibration, _update_calib_label, start_calibration, _calibration_thread)



    # test_click removed
             
    # start_calibration y _calibration_thread eliminados

    def log_message(self, msg):
        self.log_queue.put(msg)

    def update_image(self, cv2_image):
        if cv2_image is not None:
            self.image_queue.put(cv2_image)
            
    def update_stats(self, gold_amount, total_history=0, ads_per_hour=0, gold_per_hour=0):
        # Programar actualización en el hilo principal
        def _update():
            # Use formatting with separators for thousands
            self.lbl_gold.config(text=f"{gold_amount:,}")
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
            self.log_area.insert(tk.END, msg + "\n")
            self.log_area.see(tk.END)
            self.log_area.config(state=tk.DISABLED)
            
            # Actualizar status label si el mensaje parece un estado
            if "Estado:" in msg:
                self.lbl_status.config(text=msg)
                
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
            self.log_message("Bot detenido.")
            self.root.after(0, self._reset_buttons)

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
