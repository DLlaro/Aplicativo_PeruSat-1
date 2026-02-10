from napari.components import ViewerModel  # <--- LOGICA PURA (Sin GUI)
from napari.qt import QtViewer             # <--- WIDGET QT (El Canvas)
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
                               QFileDialog, QLabel, QStackedLayout, QApplication)
from PySide6.QtGui import QAction, QPixmap, QIcon
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QAction, QIcon # Agrega QKeySequence, QShortcut
import os

# IMPORTANTE: Importamos nuestra lógica
# (Esto funciona si ejecutas desde main.py)
from logic.image_loader import SatelliteLoader

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SatAnalyzer Modular v0.2")
        self.resize(1200, 800)

        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(base_path, 'assets', 'inei_logo.png')
        self.setWindowIcon(QIcon(logo_path))
        
        # 1. Instancias Lógicas
        self.loader = SatelliteLoader()
        self.viewer_model = ViewerModel()
        self.viewer_model.theme = 'dark'  # Opciones: 'dark', 'light', 'system'
        
        # 2. Configurar Interfaz (UI)
        self.setup_ui()          # Layouts y QtViewer
        self.setup_menu()        # Barra de Menú
        self.setup_status_bar()  # Barra de Estado (Etiquetas)
        
        # 3. Conectar Eventos (Signals & Slots)
        self.setup_connections()

    def setup_ui(self):
        """Crea el layout central apilado (Logo vs Visor)"""
        central_widget = QWidget()
        
        # 1. Creamos el Layout de Pila (Stack)
        # Este layout permite tener varios widgets uno encima de otro
        # y mostrar solo uno a la vez.
        self.main_stack = QStackedLayout(central_widget)
        
        # --- PÁGINA 0: El Logo de Inicio ---
        page_logo = QWidget()
        # Usamos un layout vertical para centrar el logo
        layout_logo = QVBoxLayout(page_logo)
        
        lbl_img = QLabel()
        # Construir ruta absoluta al asset para evitar errores
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(base_path, 'assets', 'inei_logo.png')
        
        # Verificar si existe y cargar
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            # Opcional: Escalar si es muy gigante (ej. max 400x400)
            pixmap = pixmap.scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_img.setPixmap(pixmap)
        else:
            lbl_img.setText("SatAnalyzer Pro\n(Logo no encontrado en src/assets/)")
            lbl_img.setStyleSheet("font-size: 24px; color: #666;")

        lbl_img.setAlignment(Qt.AlignCenter)
        layout_logo.addWidget(lbl_img)
        
        # Agregar la página del logo al stack (Índice 0)
        self.main_stack.addWidget(page_logo)
        
        # --- PÁGINA 1: El Visor de Napari ---
        self.qt_viewer = QtViewer(self.viewer_model)
        # Agregar el visor al stack (Índice 1)
        self.main_stack.addWidget(self.qt_viewer)
        
        # 2. Configuración final
        # Asegurar que empezamos mostrando el logo (índice 0)
        self.main_stack.setCurrentIndex(0)
        self.setCentralWidget(central_widget)

    def setup_menu(self):
        """Configura la barra de menú superior (Archivo, etc.)"""
        menu = self.menuBar().addMenu("Archivo")
        action = QAction("Abrir GeoTIFF...", self)
        action.triggered.connect(self.abrir_archivo)
        menu.addAction(action)

    def setup_status_bar(self):
        """Configura widgets de la barra de estado inferior"""
        # Definimos self.lbl_coords aquí porque es parte de la UI persistente
        self.lbl_coords = QLabel("Coords: - , -")
        self.statusBar().addPermanentWidget(self.lbl_coords)

    def setup_connections(self):
        """Conecta eventos del modelo con handlers de la UI"""
        # Evento de movimiento del mouse
        self.viewer_model.mouse_move_callbacks.append(self.actualizar_coordenadas)
        # 1. Evento de movimiento del mouse (Ya lo tienes)
        self.viewer_model.mouse_move_callbacks.append(self.actualizar_coordenadas)
        
        # 2. NUEVO: Atajo Global Ctrl+C (Funciona siempre)
        # QShortcut escucha en toda la ventana, sin importar si Napari tiene el foco
        self.copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        self.copy_shortcut.activated.connect(self.copiar_al_portapapeles)

    def copiar_al_portapapeles(self):
        """Método conectado al atajo Ctrl+C"""
        # Verificar si existen coordenadas guardadas (y que no sean None)
        if hasattr(self, 'last_coords') and self.last_coords is not None:
            x_lon, y_lat = self.last_coords
            
            # Formato estándar "Lat, Lon" (Google Maps style)
            # O "X, Y" si es UTM
            texto = f"{y_lat:.6f}, {x_lon:.6f}"
            
            # Copiar al sistema
            QApplication.clipboard().setText(texto)
            
            # Feedback visual
            self.statusBar().showMessage(f"Copiado: {texto}", 2000)
        else:
            self.statusBar().showMessage("Mueve el mouse sobre el mapa primero", 2000)

    def actualizar_coordenadas(self, viewer, event):
        """
        Se ejecuta cada vez que el mouse se mueve sobre el visor.
        Calcula coordenadas reales y actualiza la UI.
        """
        # 1. Validación básica
        if not self.viewer_model.layers:
            self.lbl_coords.setText("Sin imagen")
            return
            
        try:
            # 2. Obtener posición del cursor (Napari usa orden Y, X)
            # cursor.position devuelve una tupla de floats
            cursor_pos = self.viewer_model.cursor.position
            
            # Napari a veces devuelve 3 coordenadas si hay capas 3D (Z, Y, X)
            # Tomamos las últimas dos que suelen ser Y, X
            y_px = cursor_pos[-2] 
            x_px = cursor_pos[-1]
            
            # 3. Conversión Geométrica (Usando tu lógica)
            # Devuelve (X_GEO, Y_GEO) -> (Lon, Lat) o (Easting, Northing)
            x_geo, y_geo = self.loader.pixel_to_coords(x_px, y_px)
            
            # --- MEJORA: GUARDAR DATOS CRUDOS ---
            # Guardamos esto para que la función de COPIAR (Ctrl+C) lo use directo
            self.last_coords = (x_geo, y_geo) 
            # ------------------------------------

            # 4. Formateo Inteligente (Geográfico vs Proyectado)
            # Si X está entre -180 y 180, asumimos Grados Decimales (Lat/Lon)
            if -180 <= x_geo <= 180 and -90 <= y_geo <= 90:
                texto = f"Lat: {y_geo:.6f}, Lon: {x_geo:.6f}"
            else:
                # Coordenadas proyectadas (UTM usually > 100,000)
                texto = f"E: {x_geo:.2f}, N: {y_geo:.2f}"
                
            self.lbl_coords.setText(texto)
            
        except Exception as e:
            # Es útil ver el error en la consola si estás desarrollando
            # print(f"Error coords: {e}") 
            self.lbl_coords.setText("Coordenadas: Fuera de rango")

    def abrir_archivo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Imagen", "", "GeoTIFF (*.tif *.tiff)"
        )
        
        if path:
            self.cargar_en_visor(path)

    def limpiar_visor(self):
        """Elimina todas las capas (Imagen y Shapes) y resetea la cámara"""
        # 1. Eliminar todas las capas (Imagen previa, ROIs, etiquetas, etc.)
        self.viewer_model.layers.clear()
        
        # 2. Resetear referencias internas (importante si guardabas la capa ROI en una variable)
        # Si en el futuro usas 'self.capa_roi', aquí la pones a None para evitar errores.
        if hasattr(self, 'roi_layer'):
            self.roi_layer = None
            
        print("Visor limpiado.")

    def cargar_en_visor(self, ruta_archivo):
        try:
            # --- PASO 1: LIMPIEZA COMPLETA ---
            self.limpiar_visor()
            
            # --- PASO 2: CARGA ---
            print("Solicitando imagen al módulo Logic...")
            # Llamamos a tu lógica (asegúrate de tener self.loader instanciado en __init__)
            imagen_procesada = self.loader.get_preview(ruta_archivo)
            
            # --- PASO 3: VISUALIZACIÓN ---
            self.viewer_model.add_image(
                imagen_procesada, 
                name='Vista Satelital',
                rgb=True
            )
            
            # --- PASO 4: ACTUALIZAR VISTA ---
            # Resetear la cámara para encuadrar la nueva imagen perfectamente
            self.viewer_model.reset_view()

            # --- CAMBIO CLAVE ---
            # Si llegamos aquí, la imagen cargó bien.
            # Cambiamos el stack para mostrar el visor (Índice 1) en vez del logo.
            self.main_stack.setCurrentIndex(1)
            # --------------------
            
            print("Nueva imagen cargada correctamente.")
            
        except Exception as e:
            print(f"Error UI: {e}")
            # Opcional: Mostrar alerta visual
            # QMessageBox.critical(self, "Error", str(e))

    def personalizar_estilo(self):
        """
        Desactiva funciones nativas de Napari para que parezca una app propia.
        """
        # Acceso al widget nativo Qt de Napari
        qt_viewer = self.qt_viewer

        # 1. DESACTIVAR DRAG & DROP (Arrastrar archivos)
        # Esto evita que el usuario arrastre una imagen cualquiera y rompa tu lógica
        qt_viewer.setAcceptDrops(False)

        # 2. QUITAR LOGO DE BIENVENIDA ("napari")
        # Napari muestra un widget de bienvenida con el logo grande cuando no hay imágenes.
        # Es un atributo protegido ("_welcome_widget"), pero podemos ocultarlo así:
        #if hasattr(qt_viewer, '_welcome_widget'):
        #    qt_viewer._welcome_widget.hide()

        # 5. PERSONALIZAR FONDO (Opcional)
        # Si quieres que el fondo sea de otro color (ej. gris oscuro en vez de negro)
        self.viewer_model.theme = 'dark' # o 'light', o 'system'