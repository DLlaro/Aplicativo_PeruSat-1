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
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            "Abrir Imagen",
            self,
        )

        self.action_roi_rect = QAction(
            QIcon(f"{settings.base_path}/assets/icons/rectangle.svg"),
            "Rectangulo", 
            self
        )
        
        self.action_roi_poly = QAction(
            QIcon(f"{settings.base_path}/assets/icons/polygon.svg"),
            "Polígono", 
            self
        )

        self.menu_roi = QMenu(self)
        self.menu_roi.addAction(self.action_roi_rect)
        self.menu_roi.addAction(self.action_roi_poly)

        self.roi_btn = QToolButton()
        self.roi_btn.setText("ROI")
        self.roi_btn.setMenu(self.menu_roi)
        self.roi_btn.setPopupMode(QToolButton.InstantPopup)

        self.roi_btn.setCheckable(True)

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
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
            "Resetear",
            self,
        )
        self.action_reset.setEnabled(False)

        self.action_config = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DriveCDIcon),
            "Configuracion",
            self,
        )
        self.action_config.setEnabled(True)

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

    def set_roi_checked(self, activo: bool):
        self.roi_btn.setChecked(activo)
        self.roi_btn.setText("ROI: Activo (Esc)" if activo else "Seleccionar ROI")

    def set_roi_enabled(self, activo: bool):
        self.roi_btn.setEnabled(activo)

    def set_analyze_enabled(self, enabled: bool):
        self.action_analyze.setEnabled(enabled)

    def set_open_enabled(self, enabled: bool):
        self.action_open.setEnabled(enabled)

    def set_reset_enabled(self, enabled: bool):
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
        self.action_reset.setEnabled(enabled)
        self.action_config.setEnabled(enabled)
        self.action_link_ccpp.setEnabled(enabled and self._link_enabled_requested)
