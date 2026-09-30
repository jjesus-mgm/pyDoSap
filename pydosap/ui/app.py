"""Ponto de entrada da interface."""
from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ..config import APP_NAME, ASSETS_DIR
from .main_window import MainWindow
from .styles import QSS, aplicar_paleta_escura


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    aplicar_paleta_escura(app)
    app.setStyleSheet(QSS)

    icone = ASSETS_DIR / "icon.png"
    if icone.exists():
        app.setWindowIcon(QIcon(str(icone)))

    janela = MainWindow()
    janela.showMaximized()
    return app.exec()
