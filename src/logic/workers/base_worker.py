from PySide6.QtCore import QThread, Signal
from typing import Optional

class BaseWorker(QThread):
    progress_update = Signal(int, str, bool)
    status_msg = Signal(str)
    error = Signal(str)

    def progress(self, 
                 valor: int = 0, 
                 msg: str = "",
                 type: Optional[str] = 'bar', 
                 infinite: Optional[bool] = False) -> None:
        """
        Emite la señal a la barra de progreso y los mensajes del statusbar dependiendo del tipo.

        Args
        ----------
        valor : int
            Valor establecido en la barra de progreso (0-100).
        msg : str
            Texto mostrado junto a la barra de progreso.
        type : str
            - 'bar'    → emite la señal a la barra de progreso.
            - 'dialog' → emite la señal al statusbar.
        infinite : bool
            - True  → barra de carga infinita.
            - False → barra de carga progresiva (por defecto).

        Emit
        ----------
        :Signal(str)
            'bar' → Emite la señal para actualizar la barra de progreso
            'dialog' → Emite la señal para dibujar un mensaje en la StatusBar
        """
        if type == 'bar':
            self.progress_update.emit(valor, msg, infinite)
        elif type == 'dialog':
            self.status_msg.emit(msg)