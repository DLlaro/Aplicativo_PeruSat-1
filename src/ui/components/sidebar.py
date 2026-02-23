from PySide6.QtWidgets import (QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QScrollArea, QFrame)
from PySide6.QtCore import Qt
from PySide6 import QtCore

class SideBarManager:
    def __init__(self):
        # The main container that the MainWindow sees
        self.sidebar = QFrame() 
        self.sidebar.setObjectName("sidebar")

        # Layout for the main container
        self.sidebar.setFixedWidth(280)
        self.layout = QVBoxLayout(self.sidebar)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self._header()
        self._scroll_content()

        self.sidebar.hide()

    def _header(self):
        self.header = QWidget()
        self.header_layout = QHBoxLayout(self.header)

        self.close_button = QPushButton("x")
        self.close_button.setObjectName("close_btn")

        self.close_button.setFixedSize(30, 30)
        self.close_button.clicked.connect(self.sidebar.hide) # Acción directa

        self.header_layout.addStretch()
        self.header_layout.addWidget(self.close_button)

        self.layout.addWidget(self.header)

    def _scroll_content(self):
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignTop)

        self.scroll.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll)

    def add_result(self, label_text, value_text):
        # The container frame
        entry = QFrame()
        entry.setObjectName("result") 
        # Force background painting for custom QFrames
        entry.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        l = QVBoxLayout(entry)
        l.setContentsMargins(10, 5, 10, 5)

        # Title Label
        title = QLabel(label_text.upper())
        title.setObjectName("title") # <--- Target this in QSS
        
        # Value Label
        val = QLabel(str(value_text))
        val.setObjectName("value") # <--- Target this in QSS
        val.setWordWrap(True)

        l.addWidget(title)
        l.addWidget(val)
        
        self.content_layout.addWidget(entry)
        self.sidebar.show()

    def limpiar(self):
        """
        Método 'Atómico': Reemplaza el contenedor completo.
        Esto evita que Python intente leer memoria (0x0000...1C) 
        de widgets que están siendo destruidos.
        """
        self.sidebar.hide()
        
        # Creamos un reemplazo limpio
        nuevo_content_widget = QWidget()
        self.content_layout = QVBoxLayout(nuevo_content_widget)
        self.content_layout.setAlignment(Qt.AlignTop)
        
        # Al setear el nuevo widget, Qt marca el viejo para borrarlo 
        # de forma segura en su propio ciclo interno.
        self.scroll.setWidget(nuevo_content_widget)
        self.content_widget = nuevo_content_widget
        
        print("Sidebar limpiado con éxito (Atomic Swap).")
        
        
    def show_sidebar(self):
        self.sidebar.show()

    def hide_sidebar(self):
        self.sidebar.hide()    