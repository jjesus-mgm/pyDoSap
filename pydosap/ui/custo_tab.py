"""Aba de lançamento de CT-e de custo (equivalente ao "Assistente de entrada de
carregamento" da planilha ESCRITURACAO_CTES_CUSTO): busca o CT-e pela chave de
acesso, simula/lança cada NF vinculada, lança a MIRO do CT-e e fornece as ordens
de venda casadas ao pedido.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QThread, QThreadPool, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..api_client import ApiClient
from ..formatting import criar_referencia
from ..models import Fornecimento, ResultadoNota
from .styles import ALTURA_LINHA
from .workers import CustoWorker, Task

Yes, No = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No

COLS_NF = ["Num NF", "Chave", "Simulação", "MIGO", "MIRO", "Mensagem"]
COLS_FORN = ["Pedido", "Ordem", "Mensagem", "Remessa"]


class CustoTab(QWidget):
    mensagem = Signal(str)
    execucao_alterada = Signal(bool)

    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._thread: QThread | None = None
        self._worker: CustoWorker | None = None
        self._buscando = False

        self._montar()
        self._conectar()

    # ================================================================ layout
    def _montar(self) -> None:
        raiz = QVBoxLayout(self)

        busca = QHBoxLayout()
        self.e_chave = QLineEdit()
        self.e_chave.setPlaceholderText("Chave de acesso do CT-e (44 dígitos)")
        self.e_chave.setMaxLength(44)
        self.btn_buscar = QPushButton("Buscar")
        self.btn_buscar.setProperty("primary", True)
        busca.addWidget(QLabel("Chave:"))
        busca.addWidget(self.e_chave, 1)
        busca.addWidget(self.btn_buscar)
        raiz.addLayout(busca)

        raiz.addWidget(self._grupo_dados())

        divisor = QSplitter()
        divisor.addWidget(self._grupo_notas())
        divisor.addWidget(self._grupo_fornecimento())
        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 2)
        raiz.addWidget(divisor, 1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        self.log_view.setFixedHeight(110)
        self.log_view.setPlaceholderText("Log da execução…")
        raiz.addWidget(self.log_view)

        rodape = QHBoxLayout()
        self.btn_lancar = QPushButton("Lançar CT-e de custo no SAP")
        self.btn_lancar.setProperty("primary", True)
        self.btn_lancar.setEnabled(False)
        rodape.addStretch(1)
        rodape.addWidget(self.btn_lancar)
        raiz.addLayout(rodape)

    def _grupo_dados(self) -> QGroupBox:
        grupo = QGroupBox("Dados do CT-e")
        grade = QGridLayout(grupo)

        self.l_transportadora = QLabel("—")
        self.l_cnpj = QLabel("—")
        self.l_cte = QLabel("—")
        self.l_emissao = QLabel("—")
        self.l_valor = QLabel("—")
        self.l_valor.setObjectName("valorDestaque")
        self.l_integracao = QLabel("—")
        self.l_integracao.setObjectName("badge")
        self.l_integracao.setAlignment(Qt.AlignmentFlag.AlignCenter)

        grade.addWidget(QLabel("Transportadora"), 0, 0)
        grade.addWidget(self.l_transportadora, 0, 1)
        grade.addWidget(QLabel("CNPJ"), 0, 2)
        grade.addWidget(self.l_cnpj, 0, 3)
        grade.addWidget(QLabel("CT-e"), 1, 0)
        grade.addWidget(self.l_cte, 1, 1)
        grade.addWidget(QLabel("Emissão"), 1, 2)
        grade.addWidget(self.l_emissao, 1, 3)
        grade.addWidget(QLabel("Valor total"), 2, 0)
        grade.addWidget(self.l_valor, 2, 1)
        grade.addWidget(QLabel("Integração"), 2, 2)
        grade.addWidget(self.l_integracao, 2, 3)
        for c in (1, 3):
            grade.setColumnStretch(c, 1)
        return grupo

    def _grupo_notas(self) -> QGroupBox:
        grupo = QGroupBox("Notas fiscais vinculadas")
        lay = QVBoxLayout(grupo)
        self.tbl_notas = QTableWidget(0, len(COLS_NF))
        self.tbl_notas.setHorizontalHeaderLabels(COLS_NF)
        self.tbl_notas.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_notas.setAlternatingRowColors(True)
        self.tbl_notas.verticalHeader().setVisible(False)
        self.tbl_notas.verticalHeader().setDefaultSectionSize(ALTURA_LINHA)
        self.tbl_notas.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.tbl_notas)
        return grupo

    def _grupo_fornecimento(self) -> QGroupBox:
        grupo = QGroupBox("Fornecimento de ordens de venda")
        lay = QVBoxLayout(grupo)

        self.frame_resultado = QFrame()
        self.frame_resultado.setObjectName("bannerResultado")
        bl = QVBoxLayout(self.frame_resultado)
        self.l_resultado_titulo = QLabel("")
        f = QFont()
        f.setBold(True)
        self.l_resultado_titulo.setFont(f)
        self.l_resultado_msg = QLabel("")
        self.l_resultado_msg.setWordWrap(True)
        bl.addWidget(self.l_resultado_titulo)
        bl.addWidget(self.l_resultado_msg)
        self.frame_resultado.setVisible(False)
        lay.addWidget(self.frame_resultado)

        self.tbl_fornecimento = QTableWidget(0, len(COLS_FORN))
        self.tbl_fornecimento.setHorizontalHeaderLabels(COLS_FORN)
        self.tbl_fornecimento.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_fornecimento.setAlternatingRowColors(True)
        self.tbl_fornecimento.verticalHeader().setVisible(False)
        self.tbl_fornecimento.verticalHeader().setDefaultSectionSize(ALTURA_LINHA)
        self.tbl_fornecimento.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.tbl_fornecimento, 1)
        return grupo

    def _conectar(self) -> None:
        self.btn_buscar.clicked.connect(self.buscar)
        self.btn_lancar.clicked.connect(self.lancar)
        self.e_chave.returnPressed.connect(self.buscar)

    # =============================================================== busca
    def buscar(self) -> None:
        if self.em_execucao() or self._buscando:
            return
        chave = self.e_chave.text().strip()
        if len(chave) != 44 or not chave.isdigit():
            QMessageBox.warning(self, "Chave inválida", "Informe os 44 dígitos da chave de acesso do CT-e.")
            return

        self._buscando = True
        self._limpar_resultado()
        self.mensagem.emit(f"Buscando o CT-e {chave}…")
        self._atualizar_estado()

        tarefa = Task(self.api.buscar_cte_custo, chave)
        tarefa.signals.result.connect(self._busca_ok)
        tarefa.signals.error.connect(self._busca_erro)
        tarefa.signals.done.connect(self._busca_fim)
        QThreadPool.globalInstance().start(tarefa)

    def _busca_ok(self, cte: dict) -> None:
        emit = cte["infCte"]["emit"]
        ide = cte["infCte"]["ide"]
        vprest = cte["infCte"]["vPrest"]
        integracao = cte.get("integracao") or {}

        self.l_transportadora.setText(str(emit.get("xNome") or "—"))
        self.l_cnpj.setText(str(emit.get("CNPJ") or "—"))
        self.l_cte.setText(f"{int(ide.get('nCT', 0))}-{int(ide.get('serie', 0))}")
        self.l_emissao.setText(str(ide.get("dhEmi") or "")[:10] or "—")
        try:
            valor = float(str(vprest.get("vTPrest", 0)).replace(",", "."))
        except ValueError:
            valor = 0.0
        self.l_valor.setText(f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

        status = str(integracao.get("status") or "")
        msg_integracao = str(integracao.get("mensagem") or "")
        if status == "CONFIRMADO":
            self._badge(self.l_integracao, "Sucesso", "ok")
        elif "foram emitidos" in msg_integracao:
            self._badge(self.l_integracao, "Sucesso (bloqueio de emissão ignorado)", "ok")
        else:
            self._badge(self.l_integracao, msg_integracao or "Pendente", "erro")

        chaves_nf = list(cte["infCte"].get("chaves") or [])
        self.tbl_notas.setRowCount(len(chaves_nf))
        for i, chave_nf in enumerate(chaves_nf):
            self.tbl_notas.setItem(i, 0, QTableWidgetItem(criar_referencia(chave_nf)))
            self.tbl_notas.setItem(i, 1, QTableWidgetItem(chave_nf))
            for c in range(2, len(COLS_NF)):
                self.tbl_notas.setItem(i, c, QTableWidgetItem(""))
        self.tbl_notas.resizeColumnsToContents()

        self._log(f"CT-e {self.l_cte.text()} encontrado: {len(chaves_nf)} NF(s) vinculada(s).")
        self.mensagem.emit("CT-e encontrado.")
        self.btn_lancar.setEnabled(bool(chaves_nf))

    def _busca_erro(self, erro: str) -> None:
        self._log(f"Erro na busca: {erro}")
        self.mensagem.emit("Erro ao buscar o CT-e.")
        QMessageBox.critical(self, "Erro ao buscar o CT-e", erro)

    def _busca_fim(self) -> None:
        self._buscando = False
        self._atualizar_estado()

    def _limpar_resultado(self) -> None:
        for lbl in (self.l_transportadora, self.l_cnpj, self.l_cte, self.l_emissao, self.l_valor):
            lbl.setText("—")
        self._badge(self.l_integracao, "—", "")
        self.tbl_notas.setRowCount(0)
        self.tbl_fornecimento.setRowCount(0)
        self.frame_resultado.setVisible(False)
        self.btn_lancar.setEnabled(False)

    @staticmethod
    def _badge(label: QLabel, texto: str, classe: str) -> None:
        label.setText(texto)
        label.setProperty("status", classe)
        label.style().unpolish(label)
        label.style().polish(label)

    # ============================================================ lançamento
    def em_execucao(self) -> bool:
        return self._thread is not None

    def lancar(self) -> None:
        if self.em_execucao() or self._buscando:
            return
        chave = self.e_chave.text().strip()
        r = QMessageBox.question(
            self, "Confirmar lançamento",
            f"Lançar o CT-e de custo {self.l_cte.text()} ({self.tbl_notas.rowCount()} NF(s)) no SAP?\n\n"
            "O SAP precisa estar aberto e logado. Não use o SAP enquanto o robô estiver rodando.",
            Yes | No, No,
        )
        if r != Yes:
            return

        self.frame_resultado.setVisible(False)
        self.tbl_fornecimento.setRowCount(0)

        self._thread = QThread(self)
        self._worker = CustoWorker(self.api, chave)
        w = self._worker
        w.moveToThread(self._thread)
        self._thread.started.connect(w.run)
        w.log.connect(self._log)
        w.nota.connect(self._on_nota)
        w.fornecimento.connect(self._on_fornecimento)
        w.concluido.connect(self._on_concluido)
        w.falhou.connect(self._on_falhou)
        w.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread_encerrada)

        self._atualizar_estado()
        self.execucao_alterada.emit(True)
        self._log(f"Iniciando o lançamento do CT-e {chave}…")
        self._thread.start()

    def _linha_da_chave(self, chave_nf: str) -> int:
        for row in range(self.tbl_notas.rowCount()):
            item = self.tbl_notas.item(row, 1)
            if item and item.text() == chave_nf:
                return row
        return -1

    def _on_nota(self, indice: int, chave_nf: str, resultado: ResultadoNota | None, etapa: str) -> None:
        linha = self._linha_da_chave(chave_nf)
        if linha < 0:
            return
        if resultado is None:
            texto = "Simulando…" if etapa == "simulando" else "Lançando…"
            self.tbl_notas.setItem(linha, 2 if etapa == "simulando" else 5, QTableWidgetItem(texto))
            return

        if etapa == "simulacao":
            self.tbl_notas.setItem(linha, 2, QTableWidgetItem("OK" if resultado.sucesso else "Falhou"))
            if not resultado.sucesso:
                self.tbl_notas.setItem(linha, 5, QTableWidgetItem(resultado.mensagem))
        elif etapa == "lancamento":
            self.tbl_notas.setItem(linha, 3, QTableWidgetItem(resultado.migo))
            self.tbl_notas.setItem(linha, 4, QTableWidgetItem(resultado.miro))
            self.tbl_notas.setItem(linha, 5, QTableWidgetItem(resultado.mensagem))
        self.mensagem.emit(f"NF {criar_referencia(chave_nf)}: {resultado.mensagem}")

    def _on_fornecimento(self, fornecimento: Fornecimento) -> None:
        linha = self.tbl_fornecimento.rowCount()
        self.tbl_fornecimento.insertRow(linha)
        self.tbl_fornecimento.setItem(linha, 0, QTableWidgetItem(fornecimento.pedido))
        self.tbl_fornecimento.setItem(linha, 1, QTableWidgetItem(fornecimento.ordem))
        self.tbl_fornecimento.setItem(linha, 2, QTableWidgetItem(fornecimento.mensagem))
        self.tbl_fornecimento.setItem(linha, 3, QTableWidgetItem(fornecimento.remessa))

    def _on_concluido(self, resultado) -> None:
        self.frame_resultado.setVisible(True)
        if resultado.sucesso:
            self.l_resultado_titulo.setText("Lançamento concluído com sucesso")
            self.frame_resultado.setProperty("status", "ok")
        else:
            self.l_resultado_titulo.setText("Não foi possível lançar o documento")
            self.frame_resultado.setProperty("status", "erro")
        self.frame_resultado.style().unpolish(self.frame_resultado)
        self.frame_resultado.style().polish(self.frame_resultado)
        self.l_resultado_msg.setText(resultado.mensagem or "(sem mensagem)")
        self._log(f"Concluído: {resultado.mensagem}")
        self.mensagem.emit("Lançamento do CT-e de custo concluído.")

    def _on_falhou(self, erro: str) -> None:
        self._log(f"ERRO: {erro}")
        QMessageBox.critical(self, "Falha no lançamento", erro)

    def _thread_encerrada(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self._atualizar_estado()
        self.execucao_alterada.emit(False)

    # =============================================================== estado
    def _atualizar_estado(self) -> None:
        ocupado = self.em_execucao() or self._buscando
        self.btn_buscar.setEnabled(not ocupado)
        self.e_chave.setEnabled(not ocupado)
        self.btn_lancar.setEnabled(not ocupado and self.tbl_notas.rowCount() > 0)

    def _log(self, msg: str) -> None:
        self.log_view.appendPlainText(f"{datetime.now():%H:%M:%S}  {msg}")
