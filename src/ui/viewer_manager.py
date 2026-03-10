from napari.components import ViewerModel

class ViewerManager():
    def __init__(self):
        self.viewer_model = ViewerModel()
        self.viewer_model.theme = 'dark'
        self._layers: dict = {}

    @property
    def model(self) -> ViewerModel:
        return self.viewer_model  # ← expones solo lo que necesitas

    def preparar_capa(self, name: str, customize, on_data_changed):
        edge_color, face_color, edge_width = customize

        if name in self.viewer_model.layers:
            self._layers[name] = self.viewer_model.layers[name]
        else:
            self._layers[name] = self.viewer_model.add_shapes(
                name = name,
                edge_color=edge_color,
                face_color=face_color,
                edge_width=edge_width,
                ndim=2,
                visible=False
            )
        if on_data_changed is not None:
            try:
                self._layers[name].events.data.connect(on_data_changed)
            except Exception as e:
                print(f"Error al conectar evento en capa '{name}': {e}")

    def activar_capa(self, name, mode, initial_data) -> None:
        layer = self._layers.get(name)
        if layer is None:
            return
        layer.data = []
        layer.visible = True
        if initial_data is not None:
            layer.data = initial_data  # ROI ya calculó esto, solo lo dibuja
        else:
            layer.mode = mode
            self.viewer_model.cursor.style = 'crosshair'
            self.viewer_model.layers.selection.active = layer

    def desactivar_capa(self, name: str) -> None:
        layer = self._layers.get(name)
        if layer is None:
            return
            
        self.viewer_model.cursor.style = 'standard'
        self.viewer_model.layers.selection.clear()

    def limpiar_capa(self, name: str) -> None:
        layer = self._layers.get(name)
        if layer is None:
            return
        layer.data = []
        layer.visible = False