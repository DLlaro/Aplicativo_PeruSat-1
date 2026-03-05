import gc
import os

import numpy as np
from napari.components import ViewerModel
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QWidget

from constants import (
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MIN_AREA_KM2,
    MSG_ROI_ACTIVE,
    MSG_ROI_READY,
    TIMEOUT_LONG,
    TIMEOUT_MEDIUM,
)
from logic.image_loader import SatelliteLoader
from logic.modelo.model_utils import cargar_recargar_modelo
from logic.utils.config_manager import settings
from logic.workers import CCPPLinkWorker, LoadImageWorker, MetadataWorker, TilingWorker
from ui.components import AppToolbar, SideBarManager, StatusBarManager, ViewerPanel
from ui.dialogs import AnalyzeDialog, LoadDialog, SettingsDialog
from ui.handlers import KeyboardHandler, MouseHandler
from ui.roi_manager import ROIManager

from logic.prediccion import load_vector_to_napari


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PeruSat-1 Modular v0.2")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setWindowIcon(QIcon(settings.logo_path))

        self.loader = SatelliteLoader()
        self.viewer_model = ViewerModel()
        self.viewer_model.theme = 'light'

        self.container = QWidget()
        self.main_layout = QHBoxLayout(self.container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.setCentralWidget(self.container)

        self.viewer_panel = ViewerPanel(self.viewer_model)
        self.toolbar = AppToolbar(parent=self)
        self.addToolBar(self.toolbar)
        self.status_mgr = StatusBarManager(self.statusBar())
        self.sidebar_mgr = SideBarManager()

        self.main_layout.addWidget(self.viewer_panel)
        self.main_layout.addWidget(self.sidebar_mgr.sidebar)
        self.main_layout.setStretch(0, 1)
        self.main_layout.setStretch(1, 0)

        self.roi_manager = ROIManager(
            self.viewer_model,
            onToggleCallback=self.toggle_checked_roi,
            onDataChanged=self.existe_poligono,
        )

        self.mouse_handler = MouseHandler(self)
        self.keyboard_handler = KeyboardHandler(self)

        self._connect_signals()

        self.archivo_cargado = False
        self.modelo_cargado = False

        self.model = None
        self.last_buildings_gpkg_path = None
        self.last_prediction_output_dir = None

        exito, self.model, msg = cargar_recargar_modelo()
        self.modelo_cargado = exito
        self.status_mgr.show_message(msg, TIMEOUT_LONG if exito else TIMEOUT_MEDIUM)

    def toggle_checked_roi(self, is_active: bool) -> None:
        self.toolbar.set_roi_checked(is_active)
        if is_active:
            self.status_mgr.show_message(MSG_ROI_ACTIVE)

    def existe_poligono(self, tiene_datos: bool) -> None:
        self.toolbar.set_analyze_enabled(self.archivo_cargado)
        self.toolbar.set_reset_enabled(tiene_datos)
        if tiene_datos:
            self.status_mgr.show_message(MSG_ROI_READY, TIMEOUT_MEDIUM)

    def _connect_signals(self) -> None:
        self.toolbar.action_open.triggered.connect(self.abrir_archivo)
        self.toolbar.action_roi_rect.triggered.connect(lambda: self.toggle_modo_roi(mode="add_rectangle"))
        self.toolbar.action_roi_poly.triggered.connect(lambda: self.toggle_modo_roi(mode="add_polygon"))
        self.toolbar.action_analyze.triggered.connect(self.analizar_imagen)
        self.toolbar.action_link_ccpp.triggered.connect(self.vincular_centros_poblados)
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
        self.actualizar_disponibilidad_ui(valor)

    def actualizar_disponibilidad_ui(self, habilitado) -> None:
        self.toolbar.set_roi_enabled(habilitado)
        self.toolbar.set_analyze_enabled(habilitado)
        if not habilitado:
            self.toolbar.set_link_enabled(False)
            return

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

    def abrir_archivo(self) -> None:
        raster_path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir Raster",
            "",
            "GeoTIFF (*.tif *.tiff)",
        )
        if not raster_path:
            return

        self.workerMetadata = MetadataWorker(loader=self.loader, file_path=raster_path)
        self.workerMetadata.finished.connect(lambda shape: self.mostrar_load_dialog(shape))
        self.workerMetadata.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
        self.workerMetadata.start()

    def mostrar_load_dialog(self, shape: tuple) -> None:
        dialog = LoadDialog(self, shape)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            escala = dialog.get_values()
            self.status_mgr.show_message(
                f"Procesando imagen: {shape[1]} x {shape[0]} px a "
                f"{shape[1]*(escala/100):.0f} x {shape[0]*(escala/100):.0f} px..."
            )
            self.cargar_en_visor(escala)
        else:
            print("Carga cancelada.")

    def cargar_en_visor(self, input_escala) -> None:
        self.archivo_cargado = False
        try:
            self.limpiar_visor()
            self.status_mgr.show_progress()
            self.status_mgr.update_progress(0, "Cargando Imagen")

            self.worker = LoadImageWorker(loader=self.loader, escala=input_escala)
            self.worker.progress_update.connect(self.status_mgr.update_progress)
            self.worker.status_msg.connect(
                lambda msg: QMessageBox.warning(
                    self,
                    "Optimizacion de Escala",
                    msg,
                    QMessageBox.StandardButton.Ok,
                )
            )
            self.worker.finished.connect(self.finalizar_carga_img)
            self.worker.error.connect(self._on_worker_error)
            self.toolbar.set_all_enabled(False)
            self.worker.start()

        except Exception as e:
            print(f"Error UI: {e}", flush=True)

    def finalizar_carga_img(self, img_data) -> None:
        self.viewer_model.add_image(img_data, name="Preview", contrast_limits=[0, 1])
        self.status_mgr.show_message("Imagen cargada exitosamente", TIMEOUT_LONG)
        self.viewer_model.reset_view()

        self.archivo_cargado = True
        self.viewer_panel.show_viewer()
        self.toolbar.set_config_enabled(True)
        self.toolbar.set_all_enabled(True)
        print("Nueva imagen cargada correctamente.")

    def limpiar_visor(self) -> None:
        self.viewer_model.layers.clear()
        self.roi_manager.limpiar()
        self.last_buildings_gpkg_path = None
        self.last_prediction_output_dir = None
        self.toolbar.set_link_enabled(False)
        self.sidebar_mgr.limpiar()
        gc.collect()

    def toggle_modo_roi(self, activar: bool | None = None, mode: str = "add_rectangle") -> None:
        if not self.archivo_cargado:
            QMessageBox.warning(self, "Cargar Imagen", "Carga una imagen para trazar el ROI.")
            self.status_mgr.show_message("No hay imagen cargada.")
            return
        self.roi_manager.activar_herramienta(activar, mode)

    def analizar_imagen(self) -> None:
        try:
            if not self.modelo_cargado:
                self.settings()
                return

            has_roi = self.roi_manager.tiene_datos()
            area = self.roi_manager.area_km2 if has_roi else self.loader.get_image_area_km2()
            analyze_dlg = AnalyzeDialog(
                self, 
                self.loader,
                area,
                lambda: self.select_directory(ruta_inicial=self.loader.path),
                has_roi=has_roi,
            )
            ok = analyze_dlg.exec()
            if not ok:
                return

            if not analyze_dlg.selected_path:
                QMessageBox.warning(self, "Path invalido", "Directorio inexistente")
                self.status_mgr.show_message("Carpeta invalida")
                return

            process_full = analyze_dlg.process_full_image
            if process_full:
                self.roi_manager.coords_roi = self.loader.get_image_coords()
            else:
                if not has_roi:
                    QMessageBox.warning(
                        self,
                        "ROI requerido",
                        "Debes dibujar un ROI o activar 'Procesar toda la imagen'.",
                    )
                    return
                es_valido, mensaje = self.roi_manager.validar_roi(
                    min_area_km2=MIN_AREA_KM2,
                    shape=self.loader.get_original_shape(),
                )
                if not es_valido and not self._handle_roi_invalido(mensaje):
                    return
                #polygon = self.roi_manager.polygon

            self.status_mgr.show_progress()
            self.toolbar.set_all_enabled(False)
            self.toggle_modo_roi(False)

            self.workerTiler = TilingWorker(loader = self.loader,
                                                coords=self.roi_manager.coords_roi,
                                                modelo = self.model, 
                                                output_dir=analyze_dlg.selected_path)
            self.workerTiler.progress_update.connect(self.status_mgr.update_progress)
            self.workerTiler.error.connect(self._on_worker_error)
            self.workerTiler.finished.connect(self._mostrar_resultado_analisis)
            self.workerTiler.start()

        except Exception as e:
            QMessageBox.critical(self, "Error de Analisis", f"Error durante el analisis:\n{str(e)}")

    def _handle_roi_invalido(self, mensaje: str) -> bool:
        if "insuficiente" in mensaje:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("ROI Pequeno")
            msg_box.setText(mensaje)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Cancel)
            btn_continuar = msg_box.addButton(
                "Continuar de todas formas",
                QMessageBox.ButtonRole.AcceptRole,
            )
            msg_box.exec()
            return msg_box.clickedButton() == btn_continuar

        QMessageBox.warning(self, "ROI Invalido", mensaje)
        self.status_mgr.show_message("ROI invalido - ajusta la seleccion")
        return False

    def select_directory(self, titulo="Seleccionar Carpeta", ruta_inicial="") -> str | None:
        folder_path = QFileDialog.getExistingDirectory(self, titulo, ruta_inicial)
        if folder_path:
            return folder_path
        return None

    def select_vector_file(self, titulo="Seleccionar capa vectorial", ruta_inicial="") -> str | None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            titulo,
            ruta_inicial,
            "Vector files (*.gpkg *.shp *.geojson *.json)",
        )
        return path or None

    def vincular_centros_poblados(self) -> None:
        if not self.last_buildings_gpkg_path or not os.path.exists(self.last_buildings_gpkg_path):
            QMessageBox.warning(
                self,
                "Sin buildings",
                "Primero debes ejecutar una prediccion de buildings.",
            )
            return

        ccpp_path = self.select_vector_file(
            titulo="Seleccionar capa de viviendas de centros poblados",
            ruta_inicial=os.path.dirname(self.last_buildings_gpkg_path),
        )
        if not ccpp_path:
            return

        output_dir = self.select_directory(
            titulo="Seleccionar carpeta de exportacion",
            ruta_inicial=self.last_prediction_output_dir or os.path.dirname(self.last_buildings_gpkg_path),
        )
        if not output_dir:
            return

        self.status_mgr.show_progress()
        self.toolbar.set_all_enabled(False)
        print(self.roi_manager.coords_roi)
        self.workerLink = CCPPLinkWorker(
            buildings_path=self.last_buildings_gpkg_path,
            ccpp_points_path=ccpp_path,
            output_dir=output_dir,
            coords = self.roi_manager.coords_roi,
            prediction_raster_path=self.loader.path
        )
        self.workerLink.progress_update.connect(self.status_mgr.update_progress)
        self.workerLink.error.connect(self._on_worker_error)
        self.workerLink.finished.connect(self._mostrar_resultado_vinculacion)
        self.workerLink.start()

    def _on_worker_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Error", msg)
        self.toolbar.set_all_enabled(True)
        self.status_mgr.hide_progress()

    def _add_shape_layer(self, layer_name: str, shape_data: dict) -> None:
        if not shape_data or shape_data.get("type") != "shapes":
            return
        kwargs = {
            "name": layer_name,
            "shape_type": shape_data.get("shape_type", "polygon"),
        }
        if "face_color" in shape_data:
            kwargs["face_color"] = shape_data["face_color"]
        if "edge_color" in shape_data:
            kwargs["edge_color"] = shape_data["edge_color"]
        self.viewer_model.add_shapes(shape_data.get("data", []), **kwargs)

    def _mostrar_resultado_analisis(self, result_payload: object) -> None:
        if isinstance(result_payload, dict) and "shape" in result_payload:
            shape_data = result_payload["shape"]
            self.last_buildings_gpkg_path = result_payload.get("buildings_gpkg")
            self.last_prediction_output_dir = result_payload.get("base_output")
        else:
            shape_data = result_payload

        if shape_data and shape_data.get("type") == "shapes":
            self._add_shape_layer("Poligonos Detectados", shape_data)

        if self.last_buildings_gpkg_path and os.path.exists(self.last_buildings_gpkg_path):
            self.toolbar.set_link_enabled(True)

        QMessageBox.information(self, "Analisis completado", "Capa vectorial anadida con exito")
        self.toolbar.set_all_enabled(True)
        self.status_mgr.hide_progress()

    def _mostrar_resultado_vinculacion(self, result_payload: dict) -> None:
        try:
            output_gpkg = result_payload["output_gpkg"]
            dissolved_layer = result_payload["dissolved_layer"]
            voronoi_layer = result_payload.get("voronoi_layer")
            distance_crs = result_payload["distance_crs"]

            dissolved_shape = load_vector_to_napari(
                output_gpkg,
                self.loader,
                color_field="UBIGEO_CCPP_CONFIRMADO",
                neutral_value="0",
                layer=dissolved_layer,
            )
            self._add_shape_layer("CCPP Vinculados", dissolved_shape)

            self.status_mgr.show_message(f"CRS de distancias usado: {distance_crs}", TIMEOUT_LONG)
            QMessageBox.information(
                self,
                "Vinculacion completada",
                (
                    "Se genero la vinculacion con centros poblados.\n"
                    f"Archivo exportado: {output_gpkg}\n"
                    f"Capa Voronoi: {voronoi_layer}\n"
                    f"CRS de distancias: {distance_crs}"
                ),
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo mostrar la vinculacion:\n{str(e)}")
        finally:
            self.toolbar.set_all_enabled(True)
            self.status_mgr.hide_progress()

    def reset(self) -> None:
        self.roi_manager.limpiar()

    def settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            print("Configuracion actualizada, recargando modelo...")
            exito, self.model, msg = cargar_recargar_modelo(self.model)
            self.modelo_cargado = exito
            self.status_mgr.show_message(msg, TIMEOUT_LONG if exito else TIMEOUT_MEDIUM)
