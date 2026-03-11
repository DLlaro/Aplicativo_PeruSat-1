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

    def activar_capa(self, name: str, mode: str, initial_data) -> None:
        layer = self._layers.get(name)
        if layer is None:
            return
        layer.data = []
        layer.visible = True
        if initial_data is not None:
            layer.data = initial_data  # ROI ya calculó esto, para el entire_image, solo lo dibuja
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

    def on_polygon_confirm(self):
        layer = self._layers.get('ROI')
        if layer.mode == "add_polygon":
            layer._finish_drawing()
        if len(layer.data) == 0:
            return None
        
        ultimo_poly = layer.data[-1]

        #verificar que tiene almenos 3 puntos
        if len(ultimo_poly)< 3:
            layer.data = layer.data[:-1] #eliminar el ultimo
            return None
        
        layer.data = [ultimo_poly]

        return ultimo_poly
    
    def tiene_datos(self, name) -> bool:
        return self._layers.get(name) is not None and len(self._layers.get(name).data) >0


    def limpiar_capa(self, name: str) -> None:
        layer = self._layers.get(name)
        if layer is None:
            return
        layer.data = []
        layer.visible = False