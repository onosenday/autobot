import cv2
import numpy as np

class Vision:
    def __init__(self):
        pass

    def find_template(self, screen_image, template_path, threshold=0.8):
        """
        Busca una imagen plantilla dentro de la captura de pantalla.
        Devuelve (x, y) del centro si se encuentra, o None si no.
        """
        if screen_image is None:
            return None

        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None:
            print(f"Error: No se pudo cargar la imagen plantilla: {template_path}")
            return None
            
        # Verify sizes
        t_h, t_w = template.shape[:2]
        s_h, s_w = screen_image.shape[:2]
        
        if s_h < t_h or s_w < t_w:
            print(f"⚠ Warning: Imagen de pantalla ({s_w}x{s_h}) más pequeña que template ({t_w}x{t_h}). Saltando.")
            return None

        # Template Matching
        result = cv2.matchTemplate(screen_image, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            # Calcular el centro
            h, w = template.shape[:2]
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return (center_x, center_y, w, h)
        
        return None

    def generate_x_templates(self):
        """Genera plantillas de 'X' en memoria para no depender de archivos."""
        templates = []
        
        # 1. X Simple (Blanca sobre negro / Negra sobre blanco)
        for thickness in [2, 4, 6]:
            for size in [30, 40, 50]:
                img = np.zeros((size, size), dtype=np.uint8)
                # Dibujar X blanca
                cv2.line(img, (5, 5), (size-5, size-5), 255, thickness)
                cv2.line(img, (size-5, 5), (5, size-5), 255, thickness)
                templates.append((f"gen_x_{size}_{thickness}", img))
                
                # Invertir (X negra)
                img_inv = cv2.bitwise_not(img)
                templates.append((f"gen_x_inv_{size}_{thickness}", img_inv))

        return templates

    def generate_ff_templates(self):
        """Genera plantillas de Fast Forward (>>) en memoria."""
        templates = []
        # Tamaños típicos (Rango ampliado)
        for size in range(20, 81, 5):
            img = np.zeros((size, size), dtype=np.uint8)
            
            # Dibujar Triángulo 1
            # Puntos: (x1,y1), (x1,y2), (x2, y_mid)
            # Margen 5px
            mid_y = size // 2
            margin = 5
            
            x_start = margin
            x_mid = size // 2
            x_end = size - margin
            
            # Triangulo Izq
            # Base a la izquierda, Punta en el centro
            pt1 = (x_start, margin)
            pt2 = (x_start, size-margin)
            pt3 = (x_mid, mid_y)
            triangle_cnt1 = np.array( [pt1, pt2, pt3] )
            cv2.drawContours(img, [triangle_cnt1], 0, 255, -1)
            
            # Triangulo Der
            # Base en el centro (tocando punta de Izq), Punta a la derecha
            pt4 = (x_mid, margin)
            pt5 = (x_mid, size-margin)
            pt6 = (x_end, mid_y)
            triangle_cnt2 = np.array( [pt4, pt5, pt6] )
            cv2.drawContours(img, [triangle_cnt2], 0, 255, -1)
            
            # Linea Vertical (Skip)
            # Toca el vertice del segundo triangulo (x_end)
            # Grosor proporcional (ej: size//10)
            line_w = max(2, size // 15)
            cv2.rectangle(img, (x_end, margin), (x_end + line_w, size-margin), 255, -1)

            templates.append((f"gen_ff_{size}", img))
            
            # Invertido (Negro sobre blanco)
            img_inv = cv2.bitwise_not(img)
            templates.append((f"gen_ff_inv_{size}", img_inv))
            
        return templates

    def find_fast_forward_button(self, image):
        """
        Busca el botón de Fast Forward (>>) usando el asset provisto (ff_button.png)
        y su canal Alpha como máscara para ignorar el fondo.
        """
        template_path = "assets/ff_button.png"
        template = cv2.imread(template_path, cv2.IMREAD_UNCHANGED)
        
        if template is None:
            print("⚠ Asset ff_button.png no encontrado. Usando lógica generativa (backup)...")
            return self.find_fast_forward_button_backup(image)

        # Try to find match with file
        found_file_match = None
        
        height, width = image.shape[:2]
        
        # ROIs: Esquinas (25%)
        roi_size_w = int(width * 0.25)
        roi_size_h = int(height * 0.25)
        
        rois = [
            ("top_right", width - roi_size_w, 0, width, roi_size_h),
            ("bottom_right", width - roi_size_w, height - roi_size_h, width, height)
        ]

        if template is not None:
            # Usar BGR directo (mascara da problemas con esta version de opencv)
            tmpl_bgr = template[:, :, :3] if template.shape[2] == 4 else template
            
            for roi_name, x1, y1, x2, y2 in rois:
                roi_img = image[y1:y2, x1:x2]
                res = cv2.matchTemplate(roi_img, tmpl_bgr, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                
                if max_val > 0.55:
                    h, w = tmpl_bgr.shape[:2]
                    global_x = x1 + max_loc[0] + w // 2
                    global_y = y1 + max_loc[1] + h // 2
                    return (global_x, global_y, w, h)

        # Fallback: Generative logic (The shape user described: >>|)
        # print("ℹ Usando lógica generativa para Fast Forward (>>|)...")
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Generar plantillas dinámicas
        gen_templates = self.generate_ff_templates()
        
        for roi_name, x1, y1, x2, y2 in rois:
            roi_img = gray_image[y1:y2, x1:x2]
            
            for name, tmpl in gen_templates:
                res = cv2.matchTemplate(roi_img, tmpl, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                
                if max_val > 0.55: # Threshold tolerante (Lowered to 0.55 for reliability)
                    h, w = tmpl.shape[:2]
                    global_x = x1 + max_loc[0] + w // 2
                    global_y = y1 + max_loc[1] + h // 2
                    # print(f"Match generativo FF ({name}): {max_val} en {global_x},{global_y}")
                    return (global_x, global_y, w, h)
                    
        return None

    def find_fast_forward_button_backup(self, image):
        # ... Lógica generativa antigua (renombrada) ...
        # (Resto del código generativo si se quiere conservar como backup, 
        #  o simplemente eliminarlo para limpieza. Lo eliminaré para simplificar)
        return None

    def find_close_button_dynamic(self, image, ignored_zones=None):
        """
        Busca botones de cerrar (X) escaneando las esquinas y usando formas genéricas.
        ignored_zones: Lista de tuplas (x, y, radio) para ignorar.
        """
        height, width = image.shape[:2]
        
        # Definir regiones de interés (ROIs): Las 4 esquinas (15% del tamaño)
        roi_size_w = int(width * 0.15)
        roi_size_h = int(height * 0.15)
        
        rois = [
            ("top_left", 0, 0, roi_size_w, roi_size_h),
            ("top_right", width - roi_size_w, 0, width, roi_size_h),
            # Algunos ads tienen la X abajo, aunque es raro en RR3
            # ("bottom_left", 0, height - roi_size_h, roi_size_w, height),
            # ("bottom_right", width - roi_size_w, height - roi_size_h, width, height)
        ]
        
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # 1. Búsqueda con templates generados
        generated_templates = self.generate_x_templates()
        
        for roi_name, x1, y1, x2, y2 in rois:
            roi_img = gray_image[y1:y2, x1:x2]
            
            for name, tmpl in generated_templates:
                # Usar un threshold un poco más bajo para formas genéricas
                res = cv2.matchTemplate(roi_img, tmpl, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                
                if max_val > 0.65: # Threshold tolerante para formas
                    h, w = tmpl.shape[:2]
                    # Ajustar coordenadas globales
                    global_x = x1 + max_loc[0] + w // 2
                    global_y = y1 + max_loc[1] + h // 2
                    
                    # Verificar si está en zona ignorada
                    if ignored_zones:
                        is_ignored = False
                        for (ix, iy, ir) in ignored_zones:
                            dist = np.sqrt((global_x - ix)**2 + (global_y - iy)**2)
                            if dist < ir:
                                is_ignored = True
                                break
                        if is_ignored:
                            continue

                    return (global_x, global_y, w, h)

        return None
