from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QStyle, QToolBar, QToolButton

from logic.utils.config_manager import settings


class AppToolbar(QToolBar):
    def __init__(self, parent=None):
        super().__init__("Herramientas Principales", parent)
        self.setMovable(False)
        self.setIconSize(QSize(36, 18))
        self._link_enabled_requested = False

        self._build_actions()
        self._setup()

    def _build_actions(self):
        self.action_open = QAction(
            QIcon(f"{settings.base_path}/assets/icons/upload_raster.svg"),
            "Abrir Imagen",
            self,
        )

        self.action_roi_rect = QAction(
            QIcon(f"{settings.base_path}/assets/icons/rectangle.svg"),
            "Rectangulo", 
            self
        )
        self.action_roi_rect.setCheckable(True)
        
        self.action_roi_poly = QAction(
            QIcon(f"{settings.base_path}/assets/icons/polygon.svg"),
            "Polígono", 
            self
        )
        self.action_roi_poly.setCheckable(True)

        self.menu_roi = QMenu(self)
        self.menu_roi.addAction(self.action_roi_rect)
        self.menu_roi.addAction(self.action_roi_poly)

        self.roi_btn = QToolButton()
        self.roi_btn.setIcon(QIcon(f"{settings.base_path}/assets/icons/draw_roi.svg"))
        self.roi_btn.setText("ROI")
        self.roi_btn.setMenu(self.menu_roi)
        self.roi_btn.setPopupMode(QToolButton.InstantPopup)

        self.action_analyze = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight),
            "Analizar",
            self,
        )
        self.action_analyze.setEnabled(False)

        self.action_link_ccpp = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogYesButton),
            "Vincular con centros poblados",
            self,
        )
        self.action_link_ccpp.setEnabled(False)

        self.action_reset = QAction(
            QIcon(f"{settings.base_path}/assets/icons/reset.svg"),
            "Resetear",
            self,
        )
        self.action_reset.setEnabled(False)

        self.action_config = QAction(
            QIcon(f"{settings.base_path}/assets/icons/configuration.svg"),
            "Configuracion",
            self,
        )
        self.action_config.setEnabled(True)

        self.action_bond = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_CommandLink),
            "Relacionar", self
        )
        self.action_bond.setEnabled(True)

    def _setup(self):
        self.addAction(self.action_open)
        self.addSeparator()
        self.addWidget(self.roi_btn)
        self.addSeparator()
        self.addAction(self.action_analyze)
        self.addSeparator()
        self.addAction(self.action_link_ccpp)
        self.addSeparator()
        self.addAction(self.action_reset)
        self.addSeparator()
        self.addAction(self.action_config)

    def set_roi_opt_checked(self, activo: bool, option = "add_rectangle"):
        if activo:
            print(f"Activando modo ROI: {option}")
            if option == "add_rectangle":
                self.action_roi_rect.setChecked(activo)
                self.action_roi_poly.setChecked(not activo)
                self.action_roi_poly.setEnabled(not activo)
            elif option == "add_polygon":
                self.action_roi_rect.setChecked(not activo)
                self.action_roi_poly.setChecked(activo)
                self.action_roi_poly.setEnabled(activo)
        else:
            print("Desactivando modo ROI")
            self.action_roi_rect.setChecked(False)
            self.action_roi_rect.setEnabled(True)
            self.action_roi_poly.setChecked(False)
            self.action_roi_poly.setEnabled(True)
            

    def set_roi_enabled(self, activo: bool):
        self.roi_btn.setEnabled(activo)

    def set_analyze_enabled(self, enabled: bool):
        self.action_analyze.setEnabled(enabled)

    def set_open_enabled(self, enabled: bool):
        self.action_open.setEnabled(enabled)

    def set_reset_enabled(self, enabled: bool):
        self._reset_enabled_requested = enabled
        self.action_reset.setEnabled(enabled)

    def set_config_enabled(self, enabled: bool):
        self.action_config.setEnabled(enabled)

    def set_link_enabled(self, enabled: bool):
        self._link_enabled_requested = enabled
        self.action_link_ccpp.setEnabled(enabled)

    def set_all_enabled(self, enabled: bool):
        """
        Enable/disable all toolbar actions.
        Respeta el estado interno del boton de vinculacion.
        """
        self.action_open.setEnabled(enabled)
        self.roi_btn.setEnabled(enabled)
        self.action_analyze.setEnabled(enabled)
        self.action_config.setEnabled(enabled)
        self.action_reset.setEnabled(enabled and self._reset_enabled_requested)
        self.action_link_ccpp.setEnabled(enabled and self._link_enabled_requested)
