from napari.components import ViewerModel  # <--- LOGICA PURA (Sin GUI)
from napari.qt import QtViewer             # <--- WIDGET QT (El Canvas)
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
                               QFileDialog, QLabel, QStackedLayout, QApplication, QPushButton,
                               QToolBar, QStyle, QMessageBox, QInputDialog, QProgressBar)
from PySide6.QtGui import QAction, QPixmap, QIcon
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QKeySequence, QShortcut, QAction # Agrega QKeySequence, QShortcut
import os

# Importar la logica
from logic.image_loader import SatelliteLoader
from ui.roi_manager import ROIManager
from logic.load_worker import LoadWorker

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PeruSat-1 Analyzer Modular v0.2")
        self.resize(1200, 800)

        self.base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(self.base_path, 'assets', 'inei_logo.png')
        self.setWindowIcon(QIcon(logo_path))
        
        # 1. Instancias Lógicas
        self.loader = SatelliteLoader()
        self.viewer_model = ViewerModel()
        self.viewer_model.theme = 'dark'  # Opciones: 'dark', 'light', 'system'
        #Le pasamos el control del visor y el loader

        self.roi_manager = ROIManager(self.viewer_model, self.loader, onToggleCallback= self.update_roi_ui)

        # 2. Configurar Interfaz (UI)
        self.setup_ui()          # Layouts y QtViewer
        self.setup_toolbar()        # Barra de Menú
        #self.setup_menuBar()
        self.setup_status_bar()  # Barra de Estado (Etiquetas)
        
        # 3. Conectar Eventos (Signals & Slots)
        self.setup_connections()

        # 4. Flags
        self.archivo_cargado = False

    @property
    def archivo_cargado(self):
        return self._archivo_cargado
    
    @archivo_cargado.setter
    def archivo_cargado(self, valor):
        self._archivo_cargado = valor
        # callback automatico
        self.actualizar_disponibilidad_ui(valor)

    def actualizar_disponibilidad_ui(self, habilitado):
        """Activar o deshabilitar botones si se ha cargado un archivo"""
        self.action_roi.setEnabled(habilitado)
        self.action_analyze.setEnabled(habilitado)
        if habilitado:
            self.statusBar().showMessage("Imagen Lista para procesar", 5000)

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
        logo_path = os.path.join(self.base_path, 'assets', 'inei_logo.png')
        
        # Verificar si existe y cargar
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            # Opcional: Escalar si es muy gigante (ej. max 400x400)
            pixmap = pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_img.setPixmap(pixmap)
        else:
            lbl_img.setText("PeruSat Analyzer\n(Logo no encontrado en src/assets/)")
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

    def setup_toolbar(self):
        """Crea la barra de botones superior"""
        toolbar = QToolBar("Herramientas Principales")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(36,18))
        self.addToolBar(toolbar)

        #--- Boton 1: Abrir (Icono de Carpeta) ---
        icon_open = self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        action_open = QAction(icon_open, "Abrir Imagen", self)
        action_open.triggered.connect(self.abrir_archivo)
        toolbar.addAction(action_open)

        toolbar.addSeparator()

        #--- Boton 2: Dibujar ROI ---
        icon_draw = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        self.action_roi = QAction(icon_draw, "Dibujar ROI (R)", self)
        self.action_roi.setCheckable(True)
        self.action_roi.setShortcut("R")
        toolbar.addAction(self.action_roi)
 
        toolbar.addSeparator()

        #--- Boton 3: Analizar ---
        icon_play = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.action_analyze = QAction(icon_play, "Analizar", self)
        toolbar.addAction(self.action_analyze)
        
    def update_roi_ui(self, is_active):
        """
        Este es el callback. ROIManager lo llamará pasando True o False.
        """
        self.action_roi.setChecked(is_active)
        if is_active:
            self.action_roi.setText("ROI: Activo (Esc)")
            self.statusBar().showMessage("Modo Selección: Dibuje un rectángulo en el visor", 0) # 0 para que no desaparezca
        else:
            self.action_roi.setText("Seleccionar ROI")
            self.statusBar().clearMessage()
            self.statusBar().showMessage("Listo", 3000)

    def setup_menu(self):
        """Configura la barra de menú superior (Archivo, etc.)"""
        #--- Menu Archivo ---
        menu = self.menuBar().addMenu("Archivo")
        action = QAction("Abrir GeoTIFF...", self)
        action.triggered.connect(self.abrir_archivo)
        menu.addAction(action)

        #--- Boton Analizar
        btn_analzar = QPushButton("Analizar", self)
        btn_analzar.clicked.connect(self.analizar_image)
        self.main_stack.addWidget(btn_analzar)

    #def setup_menuBar(self):
    #    menu_tools = self.menuBar().addMenu("Herramientas")
    #    action_roi = QAction("Dibujar ROI", self)
    #    action_roi.setShortcut("R")
    #    action_roi.triggered.connect(self.roi_manager.activar_herramienta)
    #    menu_tools.addAction(action_roi)

    def setup_status_bar(self):
        """Configura widgets de la barra de estado inferior"""
        # Definimos self.lbl_coords aquí porque es parte de la UI persistente

        self.lbl_coords = QLabel("Coords: - , -")
        self.statusBar().addPermanentWidget(self.lbl_coords)

        self.lbl_coords_lat_lon = QLabel("| - , -")
        self.statusBar().addPermanentWidget(self.lbl_coords_lat_lon)

        #Progress Bar
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(15)
        self.progress.setMaximumWidth(150)
        self.statusBar().addPermanentWidget(self.progress)
        self.progress.hide()

    def setup_connections(self):
        """Conecta eventos del modelo con handlers de la UI"""
        # Evento de movimiento del mouse
        self.viewer_model.mouse_move_callbacks.append(self.actualizar_coordenadas)
        
        # 2. atajoCtrl+C
        # QShortcut escucha en toda la ventana, sin importar si Napari tiene el foco
        self.copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        self.copy_shortcut.activated.connect(self.copiar_al_portapapeles)
        # connectar a ROI
        self.action_roi.triggered.connect(self.activar_roi)
        # conectar a analizar
        self.action_analyze.triggered.connect(self.analizar_imagen)

    def copiar_al_portapapeles(self):
        """Método conectado al atajo Ctrl+C"""
        # Verificar si existen coordenadas guardadas (y que no sean None)
        if hasattr(self, 'lat_lon') and self.lat_lon is not None:
            lat, lon  = self.lat_lon
            
            # Formato estándar "Lat, Lon" (Google Maps style)
            # O "X, Y" si es UTM
            texto = f"{lat:.6f}, {lon:.6f}"
            
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
            # Devuelve (X_GEO, Y_GEO) -> invierte y devuelve (Lat(y), Lon(x))
            x_geo, y_geo, lat, lon  = self.loader.cursor_to_coords(x_px, y_px)
            
            # --- MEJORA: GUARDAR DATOS CRUDOS ---
            # Guardamos esto para que la función de COPIAR (Ctrl+C) lo use directo
            self.lat_lon = (lat, lon) 
            # ------------------------------------

            # 4. Formate (Geográfico y Proyectado)
            texto = f" E: {x_geo:.2f}, N: {y_geo:.2f}"
            texto_2 = f" Lat: {lat:.6f}, Lon: {lon:.6f}"

            self.lbl_coords.setText(texto)
            self.lbl_coords.setText(texto_2)

        except Exception as e:
            # Es útil ver el error en la consola si estás desarrollando
            print(f"Error coords: {e}") 
            self.lbl_coords.setText("Coordenadas: Fuera de rango")
            self.lbl_coords_lat_lon.setText("- , -")

    def activar_roi(self):
        if self.archivo_cargado:
            self.roi_manager.activar_herramienta()
        else:
            QMessageBox.warning(
                    self,
                    "Cargar Imagen",
                    "Cargar una imagen para realizar el trazado del ROI"
                )
            self.statusBar().showMessage("ROI inválido - ajusta la selección")
            return None

    def abrir_archivo(self):

        # 1. Create the instance
        dialog = QInputDialog(self)
        dialog.setInputMode(QInputDialog.IntInput)
        dialog.setWindowTitle("Resolución para visualizar imagen")
        # Opción A: Hablar de "Nivel de Detalle"
        dialog.setLabelText(
            "Seleccione el nivel de reducción:\n"
            "1 = Calidad Original (Lento)\n"
            "10 = Máxima Reducción (Rápido, 1/10 del tamaño)"
        )
        dialog.setIntRange(1, 10)
        dialog.setIntValue(5)

        # 2. Set the size (Width, Height)
        dialog.resize(300, 200) 

        # 3. Execute and handle results
        ok = dialog.exec_()
        input_res = dialog.intValue()

        if ok:
            path, _ = QFileDialog.getOpenFileName(self, "Abrir Imagen", "", "GeoTIFF (*.tif *.tiff)")
            if path:
                self.cargar_en_visor(path, input_res)
        else:
            # This triggers if the user clicks 'Cancel'
            print("Operación cancelada por el usuario")


    def cargar_en_visor(self, ruta_archivo, input_escala):
        try:
            # --- limpiar visor ---
            self.limpiar_visor()
            
            # --- cargar la vista previa de la imagen ---
            print("Solicitando imagen al módulo Logic...")
            self.progress.show()
            self.progress.setRange(0, 100)
            self.progress.setValue(0)

            # Creamos el hilo
            self.worker = LoadWorker(self.loader, ruta_archivo, input_escala)

            self.worker.progress_update.connect(self.progress.setValue)

            # 1. ACTUALIZACIÓN INSTANTÁNEA: 
            # En cuanto el hilo abre el archivo (ms), cambia la barra de estado
            self.worker.metadata_ready.connect(
                lambda w, h: self.statusBar().showMessage(f"Procesando imagen de {w}x{h} px...")
            )

            # 2. CUANDO TERMINA EL PROCESO PESADO:
            self.worker.finished.connect(self.finalizar_carga_img)
            
            # 3. MANEJO DE ERRORES:
            self.worker.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))

            # Ejecutar hilo
            self.worker.start()
            
            # La imagen cargó bien. Cambiamos el stack para mostrar el visor (Índice 1) en vez del logo.
            self.main_stack.setCurrentIndex(1)
            print("Nueva imagen cargada correctamente.")
            
        except Exception as e:
            print(f"Error UI: {e}", flush=True)
            # Opcional: Mostrar alerta visual
            # QMessageBox.critical(self, "Error", str(e))

    def finalizar_carga_img(self, img_data):
        # Añadimos a Napari
        self.viewer_model.add_image(img_data, name="PeruSat-1 Preview")
        self.archivo_cargado = True 
        self.statusBar().showMessage("Imagen cargada exitosamente", 5000)

        # --- visualizar la imagen ---
        self.viewer_model.add_image(
            img_data, 
            name='Vista Satelital',
            rgb=True
        )
        self.viewer_model.reset_view()

        # Actulizar flag
        self.archivo_cargado = True
        self.progress.hide()
    
    def limpiar_visor(self):
        """Elimina todas las capas (Imagen y Shapes) y resetea la cámara"""
        # 1. Eliminar todas las capas (Imagen previa, ROIs, etiquetas, etc.)
        self.viewer_model.layers.clear()
        
        # 2. Resetear referencias internas
        self.roi_manager.limpiar()
            
        print("Visor limpiado.", flush=True)

    def analizar_imagen(self):
        """
        Analiza la región de interés (ROI) seleccionada:
        1. Valida que exista un ROI
        2. Extrae coordenadas y datos
        3. Ejecuta inferencia con PyTorch
        """
        try:
            x, y, w, h = self.loader.roi_to_coords(
                layer=self.roi_manager.layer
            )

            # Validar ROI
            es_valido, mensaje_error = self.loader.validar_roi(x, y, w, h)
            if not es_valido:
                QMessageBox.warning(
                    self,
                    "ROI Inválido",
                    mensaje_error
                )
                self.statusBar().showMessage("ROI inválido - ajusta la selección")
                return None
            print(f"Enviando a PyTorch región: x={x}, y={y}, w={w}, h={h}")
            
            # TODO: inferencia real con PyTorch
            # resultado = self.modelo.eval(...)
            
            self._mostrar_resultado_analisis(w, h)
            
        except Exception as e:
            QMessageBox.critical(self, "Error de Análisis", 
                            f"Error durante el análisis:\n{str(e)}")
    
    def _mostrar_resultado_analisis(self, w: float, h: float) -> None:
        """Muestra el resultado del análisis al usuario."""
        QMessageBox.information(
            self, 
            "Análisis Completado", 
            f"Región analizada de {w}×{h} píxeles\n"
        )