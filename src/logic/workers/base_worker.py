from PySide6.QtCore import QThread, Signal

class BaseWorker(QThread):
    progress_update = Signal(int, str, bool)
    status_msg = Signal(str)
    error = Signal(str)

    def progress(self, 
                 valor: int = 0, 
                 msg: str = "",
                 type: str = 'bar', 
                 infinite: bool = False) -> None:
        """
        Emite la señal a la barra de progreso y los mensajes del statusbar dependiendo del tipo.

        Parámetros
        ----------
        valor : int
            Valor establecido en la barra de progreso (0-100).
        msg : str
            Texto mostrado junto a la barra de progreso.
        type : str
            'bar'    → emite a la barra de progreso.
            'dialog' → emite al statusbar.
        infinite : bool
            True  → barra de carga infinita.
            False → barra de carga progresiva (por defecto).
        """
        if type == 'bar':
            self.progress_update.emit(valor, msg, infinite)
        elif type == 'dialog':
            self.status_msg.emit(msg)