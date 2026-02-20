from PySide6.QtWidgets import QToolBar, QStyle
from PySide6.QtGui import QAction
from PySide6.QtCore import QSize

class AppToolbar(QToolBar):
    def __init__(self, parent=None):
        super().__init__("Herramientas Principales", parent)
        self.setMovable(False)
        self.setIconSize(QSize(36, 18))

        self._build_actions()
        self._setup()

    def _build_actions(self):
        # self.style() works because parent is set
        self.action_open = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            "Abrir Imagen", self
        )

        self.action_roi = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "Dibujar ROI (R)", self
        )
        self.action_roi.setCheckable(True)
        self.action_roi.setShortcut("R")

        self.action_analyze = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight),
            "Analizar", self
        )
        self.action_analyze.setEnabled(False)

        self.action_reset = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
            "Resetear", self
        )
        self.action_reset.setEnabled(False)

        self.action_config = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DriveCDIcon),
            "Configuración", self
        )
        self.action_config.setEnabled(True)

    def _setup(self):
        self.addAction(self.action_open)        # self IS the toolbar
        self.addSeparator()
        self.addAction(self.action_roi)
        self.addSeparator()
        self.addAction(self.action_analyze)
        self.addSeparator()
        self.addAction(self.action_reset)
        self.addSeparator()
        self.addAction(self.action_config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_roi_checked(self, activo: bool):
        self.action_roi.setChecked(activo)
        self.action_roi.setText("ROI: Activo (Esc)" if activo else "Seleccionar ROI")

    def set_roi_enabled(self, activo: bool):
        self.action_roi.setEnabled(activo)

    def set_analyze_enabled(self, enabled: bool):
        self.action_analyze.setEnabled(enabled)

    def set_open_enabled(self, enabled: bool):
        self.action_open.setEnabled(enabled)

    def set_reset_enabled(self, enabled: bool):
        self.action_reset.setEnabled(enabled)

    def set_config_enabled(self, enabled: bool):
        self.action_config.setEnabled(enabled)
    
    def set_all_enabled(self, enabled: bool):
        """Enable/disable all toolbar actions (e.g., during file loading)"""
        self.action_open.setEnabled(enabled)
        self.action_roi.setEnabled(enabled)
        self.action_analyze.setEnabled(enabled)
        self.action_reset.setEnabled(enabled)
        self.action_config.setEnabled(enabled)