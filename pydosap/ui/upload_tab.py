"""Aba de upload de XMLs de CT-e para o TMS (equivale ao módulo CTE_UPLOAD)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..api_client import ApiClient
from ..services.upload import listar_xmls
from .styles import ALTURA_LINHA
from .workers import UploadWorker

Yes, No = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No


class UploadTab(QWidget):
    mensagem = Signal(str)
    execucao_alterada = Signal(bool)

    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._arquivos: list[Path] = []
        self._thread: QThread | None = None
        self._worker: UploadWorker | None = None

        raiz = QVBoxLayout(self)

        linha = QHBoxLayout()
        self.e_pasta = QLineEdit()
        self.e_pasta.setReadOnly(True)
        self.e_pasta.setPlaceholderText("Pasta com os XMLs de CT-e…")
        self.btn_pasta = QPushButton("Escolher pasta…")
        linha.addWidget(self.e_pasta, 1)
        linha.addWidget(self.btn_pasta)
        raiz.addLayout(linha)

        self.lbl = QLabel("Nenhuma pasta selecionada.")
        raiz.addWidget(self.lbl)

        self.chk_forcar = QCheckBox("Forçar integração (CT-es com mais de 90 dias)")
        self.chk_forcar.setToolTip(
            "A listagem do Lincros só traz os últimos 90 dias. Com esta opção o XML é enviado ao "
            "Lincros (upload síncrono) e o CT-e é gravado direto na base de lançamento, aparecendo "
            "na aba Lançamento. O XML precisa ser de CT-e autorizado (cStat 100)."
        )
        raiz.addWidget(self.chk_forcar)

        self.tabela = QTableWidget(0, 3)
        self.tabela.setHorizontalHeaderLabels(["Arquivo", "Resultado", "Resposta do servidor"])
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.verticalHeader().setDefaultSectionSize(ALTURA_LINHA)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        self.tabela.setColumnWidth(0, 380)
        self.tabela.setColumnWidth(1, 90)
        raiz.addWidget(self.tabela, 1)

        rodape = QHBoxLayout()
        self.progresso = QProgressBar()
        self.btn_parar = QPushButton("Parar")
        self.btn_parar.setProperty("danger", True)
        self.btn_parar.setEnabled(False)
        self.btn_enviar = QPushButton("Enviar XMLs")
        self.btn_enviar.setProperty("primary", True)
        self.btn_enviar.setEnabled(False)
        rodape.addWidget(self.progresso, 1)
        rodape.addWidget(self.btn_parar)
        rodape.addWidget(self.btn_enviar)
        raiz.addLayout(rodape)

        self.btn_pasta.clicked.connect(self._escolher_pasta)
        self.btn_enviar.clicked.connect(self._enviar)
        self.btn_parar.clicked.connect(self._parar)

    def em_execucao(self) -> bool:
        return self._thread is not None

    def _escolher_pasta(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Selecione a pasta com os XMLs de CT-e")
        if not pasta:
            return
        self.e_pasta.setText(pasta)
        self._arquivos = listar_xmls(pasta)
        self.lbl.setText(f"{len(self._arquivos)} arquivo(s) .xml encontrado(s).")
        self.tabela.setRowCount(0)
        self.progresso.setValue(0)
        self.btn_enviar.setEnabled(bool(self._arquivos))

    def _enviar(self) -> None:
        if self.em_execucao() or not self._arquivos:
            return
        forcar = self.chk_forcar.isChecked()
        extra = (
            "\n\nIntegração forçada: cada CT-e também será gravado na base de lançamento "
            "(ctes_api) e ficará disponível na aba Lançamento."
        ) if forcar else ""
        r = QMessageBox.question(
            self, "Enviar XMLs",
            f"Enviar {len(self._arquivos)} arquivo(s) para o TMS?\n\n"
            f"O processamento de cada arquivo é síncrono e pode demorar.{extra}", Yes | No, No,
        )
        if r != Yes:
            return

        self.tabela.setRowCount(0)
        self.progresso.setRange(0, len(self._arquivos))
        self.progresso.setValue(0)

        self._thread = QThread(self)
        self._worker = UploadWorker(self.api, list(self._arquivos), forcar)
        w = self._worker
        w.moveToThread(self._thread)
        self._thread.started.connect(w.run)
        w.progress.connect(self._on_progress)
        w.resultado.connect(self._on_resultado)
        w.concluido.connect(self._on_concluido)
        w.falhou.connect(self._on_falhou)
        w.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread_encerrada)

        self.btn_enviar.setEnabled(False)
        self.btn_pasta.setEnabled(False)
        self.chk_forcar.setEnabled(False)
        self.btn_parar.setEnabled(True)
        self.execucao_alterada.emit(True)
        self._thread.start()

    def _parar(self) -> None:
        if self._worker is not None:
            self._worker.parar()
            self.btn_parar.setEnabled(False)

    def _on_progress(self, atual: int, total: int) -> None:
        self.progresso.setValue(atual)
        self.mensagem.emit(f"Enviando XMLs: {atual}/{total}")

    def _on_resultado(self, arquivo: str, ok: bool, resposta: str) -> None:
        linha = self.tabela.rowCount()
        self.tabela.insertRow(linha)
        item_res = QTableWidgetItem("OK" if ok else "FALHA")
        item_res.setForeground(QColor("#067647" if ok else "#B42318"))
        item_res.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item_resp = QTableWidgetItem(resposta.replace("\n", " "))
        item_resp.setToolTip(resposta)
        self.tabela.setItem(linha, 0, QTableWidgetItem(arquivo))
        self.tabela.setItem(linha, 1, item_res)
        self.tabela.setItem(linha, 2, item_resp)
        self.tabela.scrollToBottom()

    def _on_concluido(self, ok: int, total: int) -> None:
        texto = f"{ok} de {total} arquivo(s) integrado(s) com sucesso."
        self.mensagem.emit(texto)
        QMessageBox.information(self, "Upload concluído", texto)

    def _on_falhou(self, erro: str) -> None:
        QMessageBox.critical(self, "Falha no upload", erro)

    def _thread_encerrada(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self.btn_pasta.setEnabled(True)
        self.chk_forcar.setEnabled(True)
        self.btn_parar.setEnabled(False)
        self.btn_enviar.setEnabled(bool(self._arquivos))
        self.execucao_alterada.emit(False)
