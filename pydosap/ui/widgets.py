"""Widgets reutilizáveis."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout,
)

from ..formatting import extrair_chaves


def validador_sem_aspas() -> QRegularExpressionValidator:
    """Bloqueia aspas, ';' e '\\' em campos que a API usa na montagem da consulta."""
    return QRegularExpressionValidator(QRegularExpression(r"""[^'";\\]*"""))


class OptionalDateEdit(QDateEdit):
    """QDateEdit que aceita 'sem data' (mostra '—'). Delete limpa o campo."""

    _VAZIO = QDate(2000, 1, 1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDisplayFormat("dd/MM/yyyy")
        self.setCalendarPopup(True)
        self.setMinimumDate(self._VAZIO)
        self.setSpecialValueText("—")
        self.setDate(self._VAZIO)

    def value(self) -> date | None:
        d = self.date()
        return None if d == self._VAZIO else d.toPython()

    def clear_value(self) -> None:
        self.setDate(self._VAZIO)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.clear_value()
            return
        super().keyPressEvent(event)


class ChavesDialog(QDialog):
    """Cola/edita a lista de chaves de acesso usada como filtro."""

    def __init__(self, chaves: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filtrar por chaves de acesso")
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Cole as chaves de acesso (uma por linha ou separadas por espaço, vírgula ou ponto e vírgula):"
        ))
        self.editor = QPlainTextEdit()
        self.editor.setPlainText("\n".join(chaves))
        layout.addWidget(self.editor, 1)

        self.contador = QLabel()
        layout.addWidget(self.contador)
        self.editor.textChanged.connect(self._atualizar)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        limpar = botoes.addButton("Limpar", QDialogButtonBox.ButtonRole.ResetRole)
        limpar.clicked.connect(self.editor.clear)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)
        self._atualizar()

    def _atualizar(self) -> None:
        validas, ignoradas = extrair_chaves(self.editor.toPlainText())
        texto = f"{len(validas)} chave(s) válida(s)"
        if ignoradas:
            texto += f" — {len(ignoradas)} item(ns) ignorado(s) (só letras e números são aceitos)"
        self.contador.setText(texto)

    def chaves(self) -> list[str]:
        return extrair_chaves(self.editor.toPlainText())[0]
