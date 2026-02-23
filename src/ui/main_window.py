from napari.components import ViewerModel  # <--- LOGICA PURA (Sin GUI)
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QFileDialog, QMessageBox, QInputDialog, QDialog)
from PySide6.QtGui import QIcon
import gc

# Importar la logica
from logic.image_loader import SatelliteLoader
from logic.load_worker import LoadWorker
from logic.utils.config_manager import settings
from logic.modelo.model_utils import cargar_recargar_modelo

from ui.roi_manager import ROIManager

from ui.dialogs.analyze_dialog import AnalyzeDialog
from ui.dialogs.load_dialog import LoadDialog
from ui.dialogs.settings_dialog import SettingsDialog

from ui.components.viewer_panel import ViewerPanel
from ui.components.toolbar import AppToolbar
from ui.components.status_bar import StatusBarManager
from ui.components.sidebar import SideBarManager

from ui.handlers.mouse_handler import MouseHandler
from ui.handlers.keyboard_handler import KeyboardHandler

from constants import (DEFAULT_WINDOW_HEIGHT, DEFAULT_WINDOW_WIDTH, MSG_ROI_ACTIVE, 
                       MSG_ROI_READY, MSG_IMAGE_LOADED, TIMEOUT_MEDIUM, 
                       TIMEOUT_LONG, MIN_AREA_KM2)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PeruSat-1 Modular v0.2")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        self.setWindowIcon(QIcon(settings.logo_path))

        # Instancias Lógicas
        self.loader = SatelliteLoader()
        self.viewer_model= ViewerModel()

        self.container = QWidget()
        self.main_layout = QHBoxLayout(self.container)
        self.main_layout.setContentsMargins(0,0,0,0)
        self.main_layout.setSpacing(0)
        self.setCentralWidget(self.container)

        # Componentes
        self.viewer_panel = ViewerPanel(self.viewer_model, settings.base_path)
        self.toolbar = AppToolbar(parent=self)      # parent permite self.style()
        self.addToolBar(self.toolbar)                         # setup_toolbar()
        self.status_mgr = StatusBarManager(self.statusBar())   # setup_status_bar()

        self.sidebar_mgr = SideBarManager()
        ## Adding them to horizontal layout
        self.main_layout.addWidget(self.viewer_panel)
        self.main_layout.addWidget(self.sidebar_mgr.sidebar)

        # Ensure viewer takes up all space, sidebar takes only what it needs
        self.main_layout.setStretch(0, 1) # Viewer expands
        self.main_layout.setStretch(1, 0) # Sidebar stays fixed
        

        # Handlers
        self.mouse_handler = MouseHandler(self)                 # mouse callbacks
        self.keyboard_handler = KeyboardHandler(self)          # shortcuts

        # Managers
        self.roi_manager = ROIManager(
            self.viewer_model, 
            onToggleCallback=self.toggle_checked_roi,
            onDataChanged=self.existe_poligono
        )

        self._connect_signals()

        # Flags
        self.archivo_cargado = False
        self.modelo_cargado = False

        self.model = None

        exito, self.model , msg = cargar_recargar_modelo()
        self.modelo_cargado = exito
        self.status_mgr.show_message(msg, TIMEOUT_LONG if exito else TIMEOUT_MEDIUM)

    def toggle_checked_roi(self, is_active: bool):
        self.toolbar.set_roi_checked(is_active)        # setText happens inside here
        if is_active:
            self.status_mgr.show_message(MSG_ROI_ACTIVE)
        else:
            self.status_mgr.show_message(MSG_IMAGE_LOADED, TIMEOUT_MEDIUM)

    def existe_poligono(self, tiene_datos: bool):
        """
        Este método recibe True o False desde el ROIManager
        Habilita o deshabilita el boton analizar si hay poligono
        """
        self.toolbar.set_analyze_enabled(tiene_datos)
        self.toolbar.set_reset_enabled(tiene_datos)
        if tiene_datos:
            self.status_mgr.show_message(MSG_ROI_READY, TIMEOUT_MEDIUM)
        else:
            self.status_mgr.show_message("Dibuje un área para analizar.", TIMEOUT_MEDIUM)

    def _connect_signals(self):
        # Solo conexiones de alto nivel
        self.toolbar.action_open.triggered.connect(self.abrir_archivo)
        self.toolbar.action_roi.triggered.connect(self.toggle_modo_roi)
        self.toolbar.action_analyze.triggered.connect(self.analizar_imagen)
        self.toolbar.action_reset.triggered.connect(self.reset)
        self.toolbar.action_config.triggered.connect(self.settings)
        self.mouse_handler.connect()
        self.keyboard_handler.connect()

    @property
    def archivo_cargado(self):
        return self._archivo_cargado

    @archivo_cargado.setter
    def archivo_cargado(self, valor):
        self._archivo_cargado = valor
        # callback automatico
        self.actualizar_disponibilidad_ui(valor)

    def actualizar_disponibilidad_ui(self, habilitado):
        """
        Activar o deshabilitar botones si se ha cargado un archivo
        """
        self.toolbar.set_roi_enabled(habilitado)
        if habilitado:
            self.status_mgr.setEPSG(self.loader.crs)
            self.toolbar.set_open_enabled(True)
            self.status_mgr.setEscala(f"{1/self.loader.scale_factor:.1f}")
            self.status_mgr.show_message("Imagen lista para analizar", TIMEOUT_LONG)
            self.status_mgr.hide_progress()

    @property
    def modelo_cargado(self):
        return self._modelo_cargado

    @modelo_cargado.setter
    def modelo_cargado(self, valor):
        self._modelo_cargado = valor
        #self.toolbar.set_config_enabled = valor


    def abrir_archivo(self):
        raster_path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Raster","", "GeoTIFF (*.tif *.tiff)",
        )
        
        if not raster_path:
            return # El usuario canceló el explorador
        
        self.workerMetadata = LoadWorker(file_path = raster_path, loader = self.loader , mode = 'metadata')
        self.workerMetadata.finished.connect(lambda shape: self.mostrar_load_dialog(raster_path, height = shape[0], width = shape[1]))
        self.workerMetadata.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
        self.workerMetadata.start()
        

    def mostrar_load_dialog(self, raster_path, width = 0, height = 0):
        #Show custom dialog
        dialog = LoadDialog(self, width, height)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            escala = dialog.get_values()
            self.cargar_en_visor(raster_path, escala)
        else:
            print("Carga cancelada.")

    def cargar_en_visor(self, ruta_archivo, input_escala):
        self.archivo_cargado = False
        try:
            # --- limpiar visor ---
            self.limpiar_visor()
            
            # --- cargar la vista previa de la imagen ---
            print("Solicitando imagen al módulo Logic...")
            self.status_mgr.show_progress()
            self.status_mgr.update_progress(0, "Cargando Imagen")

            # Creamos el hilo
            self.worker = LoadWorker(ruta_archivo, base_project_path=settings.base_path, loader = self.loader, escala = input_escala, mode = 'load')
            
            self.worker.progress_update.connect(self.status_mgr.update_progress)
            # Conectamos la señal al nuevo método de ventana emergente
            self.worker.status_msg.connect(lambda msg: QMessageBox.warning(self, "Optimizacion de Escala", msg, QMessageBox.StandardButton.Ok) )

            # ACTUALIZACIÓN INSTANTÁNEA: 
            # En cuanto el hilo abre el archivo (ms), cambia la barra de estado
            self.worker.metadata_ready.connect(
                lambda w, h: self.status_mgr.show_message(f"Procesando imagen de {w}x{h} px...")
            )

            # CUANDO TERMINA EL PROCESO PESADO:
            self.worker.finished.connect(self.finalizar_carga_img)
            
            # MANEJO DE ERRORES:
            self.worker.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))

            self.toolbar.set_all_enabled(False)

            # Ejecutar hilo
            self.worker.start()
            
            # La imagen cargó bien. Cambiamos el stack para mostrar el visor (Índice 1) en vez del logo.
            self.viewer_panel.show_viewer()
            
        except Exception as e:
            print(f"Error UI: {e}", flush=True)
            # Opcional: Mostrar alerta visual
            # QMessageBox.critical(self, "Error", str(e))

    def finalizar_carga_img(self, img_data):
        # Añadimos a Napari
        self.viewer_model.add_image(img_data, name="PeruSat-1 Preview", rgb=True)
        self.status_mgr.show_message("Imagen cargada exitosamente", TIMEOUT_LONG)
        self.viewer_model.reset_view()

        # Actulizar flag
        self.archivo_cargado = True
        self.toolbar.set_config_enabled(True)
        print("Nueva imagen cargada correctamente.")
    
    def limpiar_visor(self):
        self.viewer_model.layers.clear()
        self.roi_manager.limpiar()
        
        # Esto ahora es seguro y no causará Access Violation
        self.sidebar_mgr.limpiar()
        
        # Opcional: solo si ves que la RAM no baja tras muchas imágenes
        gc.collect()

    def toggle_modo_roi(self):
        if self.archivo_cargado:
            self.roi_manager.activar_herramienta()
        else:
            QMessageBox.warning(
                    self,
                    "Cargar Imagen",
                    "Cargar una imagen para realizar el trazado del ROI"
                )
            self.status_mgr.show_message("ROI inválido - ajusta la selección")
            return None

    def analizar_imagen(self):
        """
        Analiza la región de interés (ROI) seleccionada:
        1. Valida que exista un ROI
        2. Extrae coordenadas y datos
        3. Ejecuta inferencia con PyTorch
        """
        self.sidebar_mgr.show_sidebar()
        self.sidebar_mgr.add_result("Adasdas", "asdasdasdsasd")
        self.sidebar_mgr.add_result("Adasdas", "asdasdasdsasd")
        self.sidebar_mgr.add_result("Adasdas", "asdasdasdsasd")
        self.sidebar_mgr.add_result("Adasdas", "asdasdasdsasd")
        try:
            # Validar ROI
            es_valido, mensaje = self.roi_manager.validar_roi(
                min_area_km2 = MIN_AREA_KM2, 
                original_shape = self.loader.get_original_shape()
            )

            if not es_valido:
                if "pequeño" in mensaje:
                    # ROI pequeño => ofrecer continuar de todas formas
                    msgBox = QMessageBox(self)
                    msgBox.setIcon(QMessageBox.Icon.Warning)
                    msgBox.setWindowTitle("ROI Pequeño")
                    msgBox.setText(mensaje)
                    
                    # Botones estándar
                    msgBox.setStandardButtons(QMessageBox.StandardButton.Cancel)
                    
                    # botón personalizado
                    btn_continuar = msgBox.addButton("Continuar de todas formas", QMessageBox.ButtonRole.AcceptRole)
                    
                    result = msgBox.exec()
                    
                    # Verificar qué botón se presionó
                    if msgBox.clickedButton() == btn_continuar:
                        print("Continuar con ROI pequeño")
                        # Continuar con el análisis
                    else:
                        # cancelar análisis
                        self.status_mgr.show_message("Operación cancelada")
                        return None
                
                else:
                    # Otros errores de validación → solo advertencia
                    QMessageBox.warning(self, "ROI Inválido", mensaje)
                    self.status_mgr.show_message("ROI inválido - ajusta la selección")
                    return None

            if not self.modelo_cargado:
                self.settings()
                return None

            analyze_dlg = AnalyzeDialog(self, self.roi_manager.area_km2, lambda: self.select_directory(ruta_inicial=self.loader.path))
            ok = analyze_dlg.exec()
            
            if ok:
                if analyze_dlg.selected_path is None:
                    QMessageBox.warning(
                        self,
                        "Path inválido",
                        "Directorio inexistente"
                    )
                    self.status_mgr.show_message("Carpeta Inválida")
                    return None

                self.workerTiler = LoadWorker(base_project_path=settings.base_path, 
                                              file_path=self.loader.path,
                                              loader = self.loader,
                                              coords=self.roi_manager.coords, 
                                              mode='tiling',
                                              modelo = self.model, 
                                              output_dir=analyze_dlg.selected_path)
                self.status_mgr.show_progress()

                self.workerTiler.progress_update.connect(self.status_mgr.update_progress)# progress for loading model (infinite bar progress)

                self.workerTiler.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
                self.workerTiler.finished.connect(self._mostrar_resultado_analisis)

                self.toolbar.set_all_enabled(False)

                #Desactivar el modo_dibujo
                self.toggle_modo_roi()
                self.workerTiler.start()

                # TODO: inferencia real con PyTorch
                # resultado = self.modelo.eval(...)
                #image_to_tiles(self.base_path, )
                        
        except Exception as e:
            QMessageBox.critical(self, "Error de Análisis", 
                            f"Error durante el análisis:\n{str(e)}")
    
    def select_directory(self, titulo="Seleccionar Carpeta", ruta_inicial=""):
        """
        Abre un diálogo para seleccionar una carpeta.
        Retorna la ruta seleccionada o None si se cancela.
        """
        folder_path = QFileDialog.getExistingDirectory(
            self,
            titulo,
            ruta_inicial
        )

        if folder_path:
            print(folder_path)
            return folder_path
        return None

    def _mostrar_resultado_analisis(self, shape_data: object) -> None:
        """Muestra el resultado del análisis al usuario."""

        # Determine which method to use based on the data type
        if shape_data['type'] == 'points':
            self.viewer_model.add_points(
                shape_data['data'],
                name='Puntos Detectados',
                face_color='magenta',
                size=10
            )
        elif shape_data['type'] == 'shapes':
            self.viewer_model.add_shapes(
                shape_data['data'],
                name='Polígonos Detectados',
                shape_type=shape_data['shape_type'],
                edge_color='cyan',
                face_color=[0, 1, 1, 0.3]
            )
        
        QMessageBox.information(
            self, 
            "Analisis completado", 
            f"Capa vectorial añadida con éxito\n"
        )
        
        print(f"Capa vectorial añadida con éxito")

        self.toolbar.set_all_enabled(True)
        self.status_mgr.hide_progress()

    def reset(self):
        self.roi_manager.limpiar()

    def settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            print("Configuración actualizada, recargando modelo...")
            exito, self.model , msg = cargar_recargar_modelo()
            self.modelo_cargado = exito
            self.status_mgr.show_message(msg, TIMEOUT_LONG if exito else TIMEOUT_MEDIUM)