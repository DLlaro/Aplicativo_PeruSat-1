from napari.components import ViewerModel  # <--- LOGICA PURA (Sin GUI)
from PySide6.QtWidgets import (QMainWindow, QFileDialog, QMessageBox, QInputDialog, QDialog)
from PySide6.QtGui import QIcon
import os

# Importar la logica
from logic.image_loader import SatelliteLoader
from ui.roi_manager import ROIManager
from ui.analyze_dialog import AnalyzeDialog
from ui.load_dialog import LoadDialog
from logic.load_worker import LoadWorker

from ui.components.viewer_panel import ViewerPanel
from ui.components.toolbar import AppToolbar
from ui.components.status_bar import StatusBarManager

from ui.handlers.mouse_handler import MouseHandler
from ui.handlers.keyboard_handler import KeyboardHandler

from constants import (DEFAULT_SCALE_FACTOR, DEFAULT_WINDOW_HEIGHT, 
                       DEFAULT_WINDOW_WIDTH, MSG_ROI_ACTIVE, MSG_ROI_READY, MSG_IMAGE_LOADED, 
                       TIMEOUT_MEDIUM, TIMEOUT_LONG, MIN_AREA_KM2)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PeruSat-1 Modular v0.2")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        self.base_path: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path: str = os.path.join(self.base_path, 'assets', 'inei_logo.png')
        self.setWindowIcon(QIcon(logo_path))
        
        # Instancias Lógicas
        self.loader = SatelliteLoader()
        self.viewer_model= ViewerModel()
        self.viewer_model.theme = 'dark'  # Opciones: 'dark', 'light', 'system'

        # Componentes
        self.viewer_panel = ViewerPanel(self.viewer_model, self.base_path)
        self.setCentralWidget(self.viewer_panel)                # setup_ui()
        self.toolbar = AppToolbar(parent=self)      # parent permite self.style()
        self.addToolBar(self.toolbar)                         # setup_toolbar()
        self.status_mgr = StatusBarManager(self.statusBar())   # setup_status_bar()

        # Handlers
        self.mouse_handler = MouseHandler(self)                 # mouse callbacks
        self.keyboard_handler = KeyboardHandler(self)          # shortcuts

        # Managers
        self.roi_manager = ROIManager(
            self.viewer_model, 
            onToggleCallback=self.toggle_action_roi,
            onDataChanged=self.existe_poligono
        )

        self._connect_signals()

        # Flags
        self.archivo_cargado = False

    def toggle_action_roi(self, is_active: bool):
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
        self.toolbar.action_roi.triggered.connect(self.modo_roi)
        self.toolbar.action_analyze.triggered.connect(self.analizar_imagen)
        self.toolbar.action_reset.triggered.connect(self.reset)
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
            self.status_mgr.show_message("Imagen lista para analizar", TIMEOUT_LONG)


    def abrir_archivo(self):
        # 1. Seleccionar archivo primero (Mejor UX)
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Raster", "", "GeoTIFF (*.tif *.tiff)",
        )
        
        if not path:
            return # El usuario canceló el explorador

        # 2. Show custom dialog
        dialog = LoadDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            escala, use_gpu = dialog.get_values()
            self.cargar_en_visor(path, escala, use_gpu)
        else:
            print("Carga cancelada.")

    def input_dialog(self, titulo="", texto="", mode=QInputDialog.InputMode):
        dialog = QInputDialog(self)
        dialog.setInputMode(mode)
        dialog.setWindowTitle(titulo)
        dialog.setLabelText(texto)

        # Configuración según modo
        if mode == QInputDialog.InputMode.IntInput:
            dialog.setIntRange(DEFAULT_SCALE_FACTOR, 10)
            dialog.setIntValue(DEFAULT_SCALE_FACTOR)
        
        dialog.resize(300, 150)
        
        ok = dialog.exec()
        
        # Extraer el valor según el modo
        res = None
        if ok:
            self.toolbar.set_open_enabled(False)
            if mode == QInputDialog.InputMode.IntInput:
                res = dialog.intValue()
            elif mode == QInputDialog.InputMode.TextInput:
                res = dialog.textValue()
                
        return ok, res

    def cargar_en_visor(self, ruta_archivo, input_escala, use_gpu = False):
        self.archivo_cargado = False
        try:
            # --- limpiar visor ---
            self.limpiar_visor()
            
            # --- cargar la vista previa de la imagen ---
            print("Solicitando imagen al módulo Logic...")
            self.status_mgr.show_progress()
            self.status_mgr.update_progress(0, "Cargando Imagen")

            # Creamos el hilo
            self.worker = LoadWorker( ruta_archivo, loader=self.loader, escala=input_escala, unlock = use_gpu)

            self.worker.progress_update.connect(self.status_mgr.update_progress)
            # Conectamos la señal al nuevo método de ventana emergente
            self.worker.status_msg.connect(lambda msg: QMessageBox.warning(self, "Optimizacion de Escala", msg, QMessageBox.StandardButton.Ok) )

            # 1. ACTUALIZACIÓN INSTANTÁNEA: 
            # En cuanto el hilo abre el archivo (ms), cambia la barra de estado
            self.worker.metadata_ready.connect(
                lambda w, h: self.status_mgr.show_message(f"Procesando imagen de {w}x{h} px...")
            )

            # 2. CUANDO TERMINA EL PROCESO PESADO:
            self.worker.finished.connect(self.finalizar_carga_img)
            
            # 3. MANEJO DE ERRORES:
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
        self.viewer_model.add_image(img_data, name="PeruSat-1 Preview")
        self.status_mgr.show_message("Imagen cargada exitosamente", TIMEOUT_LONG)

        # --- visualizar la imagen ---
        self.viewer_model.add_image(
            img_data, 
            name='Vista Satelital',
            rgb=True
        )
        self.viewer_model.reset_view()

        # Actulizar flag
        self.archivo_cargado = True
        self.toolbar.set_open_enabled(True)
        print("Nueva imagen cargada correctamente.")

        self.status_mgr.hide_progress()
    
    def limpiar_visor(self):
        """Elimina todas las capas (Imagen y Shapes) y resetea la cámara"""
        # 1. Eliminar todas las capas (Imagen previa, ROIs, etiquetas, etc.)
        self.viewer_model.layers.clear()
        
        # 2. Resetear referencias internas
        self.roi_manager.limpiar()
            
        print("Visor limpiado.", flush=True)

    def modo_roi(self):
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
        try:
            x, y, w, h = self.roi_manager.rectangle_to_coords(
                layer = self.roi_manager.layer,
                scale_factor = self.loader.scale_factor
            )

            # Validar ROI
            es_valido, mensaje = self.roi_manager.validar_roi(
                x, y, w, h, 
                min_area_km2 = MIN_AREA_KM2, 
                original_shape = self.loader.original_shape
            )

            if not es_valido:
                if "pequeño" in mensaje:
                    # ROI pequeño → ofrecer continuar de todas formas
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
                self.workerTiler = LoadWorker(self.loader.path, coords=(x, y, w, h), mode='tiling', output_dir=analyze_dlg.selected_path)
                self.status_mgr.show_progress()
                self.workerTiler.progress_update.connect(self.status_mgr.update_progress)
                self.workerTiler.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
                self.workerTiler.finished.connect(lambda: self._mostrar_resultado_analisis(w, h))

                self.toolbar.set_all_enabled(False)

                self.workerTiler.start()

                print(f"Enviando a PyTorch región: x={x}, y={y}, w={w}, h={h}")

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

    def _mostrar_resultado_analisis(self, w: float, h: float) -> None:
        """Muestra el resultado del análisis al usuario."""
        QMessageBox.information(
            self, 
            "Análisis Completado", 
            f"Región analizada de {w}×{h} píxeles\n"
        )

        self.toolbar.set_all_enabled(True)
        self.status_mgr.hide_progress()

    def reset(self):
        self.roi_manager.limpiar()