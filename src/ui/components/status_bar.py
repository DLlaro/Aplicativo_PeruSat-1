from PySide6.QtWidgets import (QLabel, QProgressBar, QStatusBar)

class StatusBarManager:
    def __init__(self, status_bar: QStatusBar):
        self.bar = status_bar
        self.lbl_coords = QLabel("Coords: - , -")
        self.lbl_coords_lat_lon = QLabel(" - , -")
        self.lbl_epsg = QLabel("<b>EPSG: -</b>")
        self.lbl_escala = QLabel("Escala: 1 : -")

        self.progressLabel = QLabel("")
        self.progress = QProgressBar(objectName="status_progress")
        self.progress.setMaximumHeight(25)
        self.progress.setMaximumWidth(200)

        self._setup()

    def _setup(self):
        self.bar.addPermanentWidget(self.lbl_coords)
        self.bar.addPermanentWidget(self.lbl_coords_lat_lon)
        self.bar.addPermanentWidget(self.lbl_epsg)
        self.bar.addPermanentWidget(self.lbl_escala)

        self.bar.addPermanentWidget(self.progressLabel)
        self.bar.addPermanentWidget(self.progress)

        self.progressLabel.hide()
        self.progress.hide()
        
    def update_coords(self, x_geo, y_geo, lat, lon):
        self.lbl_coords.setText(f" E: {x_geo:.2f}, N: {y_geo:.2f}")
        self.lbl_coords_lat_lon.setText(f" Lat: {lat:.6f}, Lon: {lon:.6f}")

    def setEPSG(self, crs):
        self.lbl_epsg.setText(str(crs))

    def setEscala(self, escala):
        self.lbl_escala.setText(f"Escala: 1 : {escala}")


    def update_rectangle_roi_area(self, dx, dy, area_km2):
        self.lbl_coords.setText(f"ROI - Ancho: {dx:.1f} x Alto: {dy:.1f} m | Área: {area_km2:.4f} km²")

    def show_message(self, msg, timeout=0):
        self.bar.showMessage(msg, timeout)

    def clear_message(self):
        self.bar.clearMessage()

    def show_progress(self):
        self.progressLabel.show()
        self.progress.show()
        self.progress.setRange(0, 100)

    def hide_progress(self):
        self.progressLabel.hide()
        self.progress.hide()
    
    def update_progress(self, value: int, label: str = None, bar_infinite = False):
        if bar_infinite:
            self.progress.setRange(0,0)
        else:
            self.progress.setRange(0,100)
            self.progress.setValue(value)
        if label is not None:
            self.progressLabel.setText(label)