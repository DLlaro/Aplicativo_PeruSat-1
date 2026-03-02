from napari.components import ViewerModel  # <--- LOGICA PURA (Sin GUI)
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QFileDialog, QMessageBox, QDialog)
from PySide6.QtGui import QIcon
import gc

# Importar la logica
from logic.image_loader import SatelliteLoader
from logic.workers import LoadImageWorker, MetadataWorker, TilingWorker
from logic.utils.config_manager import settings
from logic.modelo.model_utils import cargar_recargar_modelo

from ui.roi_manager import ROIManager
from ui.dialogs import (AnalyzeDialog, LoadDialog, SettingsDialog)
from ui.components import (ViewerPanel, AppToolbar, StatusBarManager, SideBarManager)
from ui.handlers import (MouseHandler, KeyboardHandler)

from constants import (DEFAULT_WINDOW_HEIGHT, DEFAULT_WINDOW_WIDTH, MSG_ROI_ACTIVE, 
                       MSG_ROI_READY, TIMEOUT_MEDIUM, TIMEOUT_LONG, MIN_AREA_KM2)

class MainWindow(QMainWindow):
    def __init__(self):
        """
        Ventana principal del aplicativo.
        Instacia el image loader, viewer loader.
        Crea los componentes Viewer Panel, Toolbar, StatusBar, SideBar.
        Instancia el ROI Manager.
        Instancia el MouseHandler, KeyboardHandler.
        Conecta las señales y setea los flags.
        """
        super().__init__()
        self.setWindowTitle("PeruSat-1 Modular v0.2")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        self.setWindowIcon(QIcon(settings.logo_path))

        # Logica
        self.loader = SatelliteLoader()
        self.viewer_model= ViewerModel()
        
        # Contenedor principal
        self.container = QWidget()
        self.main_layout = QHBoxLayout(self.container)
        self.main_layout.setContentsMargins(0,0,0,0)
        self.main_layout.setSpacing(0)
        self.setCentralWidget(self.container)

        # Componentes
        self.viewer_panel = ViewerPanel(self.viewer_model)
        self.toolbar = AppToolbar(parent=self)
        self.addToolBar(self.toolbar)
        self.status_mgr = StatusBarManager(self.statusBar())
        self.sidebar_mgr = SideBarManager()

        self.main_layout.addWidget(self.viewer_panel)
        self.main_layout.addWidget(self.sidebar_mgr.sidebar)
        self.main_layout.setStretch(0, 1) # Viewer expands
        self.main_layout.setStretch(1, 0) # Sidebar stays fixed
        
        # Managers que depende de UI
        self.roi_manager = ROIManager(
            self.viewer_model, 
            onToggleCallback=self.toggle_checked_roi,
            onDataChanged=self.existe_poligono
        )

        # Handlers
        self.mouse_handler = MouseHandler(self)        # mouse callbacks
        self.keyboard_handler = KeyboardHandler(self)  # shortcuts

        # Señales
        self._connect_signals()

        # Flags y estado inicial
        self.archivo_cargado = False
        self.modelo_cargado = False

        self.model = None

        exito, self.model , msg = cargar_recargar_modelo()
        self.modelo_cargado = exito
        self.status_mgr.show_message(msg, TIMEOUT_LONG if exito else TIMEOUT_MEDIUM)

    def toggle_checked_roi(self, is_active: bool) -> None:
        """
        Alterna entre marcar y desmarcar la opcion de ROI

        Args
        ----------
        is_active: bool
            - True → Esta marcado el boton de ROI
            - False → Esta desmarcado el boton de ROI
        """
        self.toolbar.set_roi_checked(is_active)        # setText happens inside here
        if is_active:
            self.status_mgr.show_message(MSG_ROI_ACTIVE)

    def existe_poligono(self, tiene_datos: bool) -> None:
        """
        Este método recibe True o False desde el ROIManager
        Habilita o deshabilita el boton analizar si hay poligono

        Args
        ----------
        tiene_datos: bool
            La capa de datos tiene una área de interés dibujada?
        """
        self.toolbar.set_analyze_enabled(tiene_datos)
        self.toolbar.set_reset_enabled(tiene_datos)
        if tiene_datos:
            self.status_mgr.show_message(MSG_ROI_READY, TIMEOUT_MEDIUM)

    def _connect_signals(self) -> None:
        self.toolbar.action_open.triggered.connect(self.abrir_archivo)
        self.toolbar.action_roi_rect.triggered.connect(lambda: self.toggle_modo_roi(mode="add_rectangle"))
        self.toolbar.action_roi_poly.triggered.connect(lambda: self.toggle_modo_roi(mode="add_polygon"))
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

    def actualizar_disponibilidad_ui(self, habilitado) -> None:
        """
        Activar o deshabilitar botones si se ha cargado un archivo

        Args
        ----------
        habilitado: bool
            - True → Archivo cargado en el visor
            - False → No hay archivo cargado en el visor
        """
        self.toolbar.set_roi_enabled(habilitado)
        if habilitado:
            self.status_mgr.setEPSG(self.loader.crs)
            self.toolbar.set_open_enabled(True)
            self.status_mgr.setEscala(f"{1/self.loader.scale_factor:.1f}")
            self.status_mgr.hide_progress()

    @property
    def modelo_cargado(self):
        return self._modelo_cargado

    @modelo_cargado.setter
    def modelo_cargado(self, valor):
        self._modelo_cargado = valor
        #self.toolbar.set_config_enabled = valor


    def abrir_archivo(self) -> None:
        """
        Abre un explorador de archivos para seleccionar el tif.
        Instancia un worker para cargar la metadata de la imagen.
        """
        raster_path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Raster","", "GeoTIFF (*.tif *.tiff)",
        )
        
        if not raster_path:
            return # El usuario canceló el explorador
        
        self.workerMetadata = MetadataWorker(loader = self.loader, file_path = raster_path)
        self.workerMetadata.finished.connect(lambda shape: self.mostrar_load_dialog(shape))
        self.workerMetadata.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
        self.workerMetadata.start()
        
    def mostrar_load_dialog(self, shape : tuple) -> None:
        """
        Mostrar cuadro de dialogo con la configuracion para cargar el raster.

        Args
        ----------
        shape: tuple
            Contiene el alto y ancho del raster H x W  
        """

        dialog = LoadDialog(self, shape)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            escala = dialog.get_values()

            self.status_mgr.show_message(f"Procesando imagen de {shape[1]}x{shape[0]}px  → {(shape[1]*(escala/100)):.0}x{(shape[0]*(escala/100)):.0}px ...")

            self.cargar_en_visor(escala)
        else:
            print("Carga cancelada.")

    def cargar_en_visor(self, input_escala) -> None:
        """
        Instancia un ImageWorker para cargar en un hilo aparte la imagen.

        Args
        ----------
        input_escala: int
            Valor ingresado por el usuario 0-100 para la reduccion de la imagen al cargar en el visor
        """
        self.archivo_cargado = False
        try:
            self.limpiar_visor()
            
            print("Solicitando imagen al módulo Logic...")
            self.status_mgr.show_progress()
            self.status_mgr.update_progress(0, "Cargando Imagen")

            self.worker = LoadImageWorker(loader = self.loader, escala = input_escala)
            
            self.worker.progress_update.connect(self.status_mgr.update_progress)
            self.worker.status_msg.connect(lambda msg: QMessageBox.warning(self, "Optimizacion de Escala", msg, QMessageBox.StandardButton.Ok) )
            self.worker.finished.connect(self.finalizar_carga_img)
            self.worker.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
            self.toolbar.set_all_enabled(False)
            self.worker.start()
            
        except Exception as e:
            print(f"Error UI: {e}", flush=True)
            # Opcional: Mostrar alerta visual
            # QMessageBox.critical(self, "Error", str(e))

    def finalizar_carga_img(self, img_data) -> None:
        """
        Añade la imagen al visor de napari.
        """
        # Añadimos a Napari
        self.viewer_model.add_image(img_data, name='Preview', contrast_limits=[0, 1])
        self.status_mgr.show_message("Imagen cargada exitosamente", TIMEOUT_LONG)
        self.viewer_model.reset_view()# Centrar y ajustar zoom

        # Actulizar flag
        self.archivo_cargado = True

        # La imagen cargó. Cambiamos el stack para mostrar el visor (Índice 1) en vez del logo.
        self.viewer_panel.show_viewer()
        self.toolbar.set_config_enabled(True)
        print("Nueva imagen cargada correctamente.")
    
    def limpiar_visor(self) -> None:
        self.viewer_model.layers.clear()
        self.roi_manager.limpiar()
        
        # Esto ahora es seguro y no causará Access Violation
        self.sidebar_mgr.limpiar()
        
        # Opcional: solo si ves que la RAM no baja tras muchas imágenes
        gc.collect()

    def toggle_modo_roi(self, activar: bool | None = None, mode: str = "add_rectangle" ) -> None:
        """Alternar el modo de dibujo de ROI."""
        if not self.archivo_cargado:
            QMessageBox.warning(self, "Cargar Imagen", "Carga una imagen para trazar el ROI.")
            self.status_mgr.show_message("No hay imagen cargada.")
            return

        self.roi_manager.activar_herramienta(activar, mode)
    
    def analizar_imagen(self)  -> None:
        """
        Analiza la región de interés (ROI) seleccionada:
        1. Valida que exista un ROI
        2. Extrae coordenadas y datos
        3. Ejecuta inferencia con PyTorch
        """
        try:
            es_valido, mensaje = self.roi_manager.validar_roi(
                self.loader.transform,
                min_area_km2 = MIN_AREA_KM2, 
                original_shape = self.loader.get_original_shape()
            )

            if not es_valido:
                if not self._handle_roi_invalido(mensaje):
                    return

            if not self.modelo_cargado:
                self.settings()
                return

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
                    return
                
                self.status_mgr.show_progress()
                self.toolbar.set_all_enabled(False)
                self.toggle_modo_roi(False)

                self.workerTiler = TilingWorker(loader = self.loader,
                                                coords=self.roi_manager.coords,
                                                modelo = self.model, 
                                                output_dir=analyze_dlg.selected_path)
                self.workerTiler.progress_update.connect(self.status_mgr.update_progress)
                self.workerTiler.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
                self.workerTiler.finished.connect(self._mostrar_resultado_analisis)
                self.workerTiler.start()

        except Exception as e:
            QMessageBox.critical(self, "Error de Análisis", 
                            f"Error durante el análisis:\n{str(e)}")
    
    def _handle_roi_invalido(self, mensaje: str) -> bool:
        """
        Maneja los errores de validación del ROI.

        Retorna
        -------
        bool
            True  → continuar con el análisis.
            False → cancelar.
        """
        if "insuficiente" in mensaje:
            msgBox = QMessageBox(self)
            msgBox.setIcon(QMessageBox.Icon.Warning)
            msgBox.setWindowTitle("ROI Pequeño")
            msgBox.setText(mensaje)
            msgBox.setStandardButtons(QMessageBox.StandardButton.Cancel)
            btn_continuar = msgBox.addButton("Continuar de todas formas", QMessageBox.ButtonRole.AcceptRole)
            msgBox.exec()

            return msgBox.clickedButton() == btn_continuar

        QMessageBox.warning(self, "ROI Inválido", mensaje)
        self.status_mgr.show_message("ROI inválido - ajusta la selección")
        return False

    def select_directory(self, titulo="Seleccionar Carpeta", ruta_inicial="") -> str | None:
        """
        Abre un diálogo para seleccionar una carpeta.
        Retorna la ruta seleccionada o None si se cancela.

        Args
        ----------
        titulo: str
            Titulo del explorador de archivos
        ruta_inicial: str
            Ruta inicial donde abrira el explorador de archivos

        Return
        ----------
        : str | None
            Ruta de la carpeta seleccionada por el usuario
        """
        folder_path = QFileDialog.getExistingDirectory(
            self,
            titulo,
            ruta_inicial
        )

        if folder_path:
            print(folder_path)
            return folder_path
        return

    def _mostrar_resultado_analisis(self, shape_data: object) -> None:
        """
        Muestra el resultado del análisis al usuario.
        Habilita toolbar y oculta el progress bar.
        
        Args
        ----------
        shape_data :dict
            - 'type': 'shapes'
            - 'data': list[np.ndarray] — coordenadas en píxeles (row, col) de cada polígono, listas para Napari.
            - 'shape_type': 'polygon'
        """
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

        #self.sidebar_mgr.show_sidebar()

    def reset(self) -> None:
        """Limpia la capa ROI"""
        self.roi_manager.limpiar()

    def settings(self) -> None:
        """
        Abrir el menú de configuración
        """
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            print("Configuración actualizada, recargando modelo...")
            exito, self.model , msg = cargar_recargar_modelo(self.model)
            self.modelo_cargado = exito
            self.status_mgr.show_message(msg, TIMEOUT_LONG if exito else TIMEOUT_MEDIUM)