"""Abas de configuração (config_lancamento, config_cte_custo, config_filiais,
regioes_csc): lê e grava via API (GET/POST /cte/config/<ação>/<tabela>).

Importante: "Salvar" substitui a tabela inteira pelo conteúdo atual da grade (o
backend faz um `CREATE OR REPLACE TABLE ... AS SELECT * FROM data`, não um update
por linha) — por isso sempre enviamos todas as linhas carregadas, não só as
editadas. "Reverter" restaura o backup feito automaticamente na última gravação.
"""
from __future__ import annotations

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QLabel, QHBoxLayout, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from ..api_client import ApiClient
from ..formatting import converter_como_original
from .styles import ALTURA_LINHA
from .workers import Task

Yes, No = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No
COR_ALTERADA = QColor("#332B14")

TABELAS = (
    ("Lançamento (frete)", "config_lancamento"),
    ("CT-e de custo", "config_cte_custo"),
    ("Filiais", "config_filiais"),
    ("Regiões CSC", "regioes_csc"),
)


class ConfigTableTab(QWidget):
    """Editor genérico de uma tabela de configuração do BigQuery, via API."""

    mensagem = Signal(str)

    def __init__(self, api: ApiClient, tabela: str, parent=None):
        super().__init__(parent)
        self.api = api
        self.tabela = tabela
        self._linhas: list[dict] = []
        self._colunas: list[str] = []
        self._dirty: set[int] = set()
        self._carregando = False

        raiz = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.btn_carregar = QPushButton("Carregar")
        self.btn_carregar.setProperty("primary", True)
        self.btn_salvar = QPushButton("Salvar alterações")
        self.btn_salvar.setEnabled(False)
        self.btn_reverter = QPushButton("Reverter última gravação")
        self.btn_reverter.setProperty("danger", True)
        self.lbl = QLabel("Clique em Carregar para começar.")
        topo.addWidget(self.btn_carregar)
        topo.addWidget(self.btn_salvar)
        topo.addWidget(self.btn_reverter)
        topo.addWidget(self.lbl, 1)
        raiz.addLayout(topo)

        self.tabela_widget = QTableWidget()
        self.tabela_widget.setAlternatingRowColors(True)
        self.tabela_widget.verticalHeader().setVisible(False)
        self.tabela_widget.verticalHeader().setDefaultSectionSize(ALTURA_LINHA)
        raiz.addWidget(self.tabela_widget, 1)

        self.btn_carregar.clicked.connect(self.carregar)
        self.btn_salvar.clicked.connect(self.salvar)
        self.btn_reverter.clicked.connect(self.reverter)
        self.tabela_widget.itemChanged.connect(self._on_item_changed)

    # ================================================================ carga
    def carregar(self) -> None:
        if self._dirty and not self._confirmar_descarte():
            return
        self._definir_ocupado(True)
        self.mensagem.emit(f"Carregando '{self.tabela}'…")
        tarefa = Task(self.api.buscar_configuracoes, self.tabela)
        tarefa.signals.result.connect(self._ok)
        tarefa.signals.error.connect(self._erro)
        tarefa.signals.done.connect(lambda: self._definir_ocupado(False))
        QThreadPool.globalInstance().start(tarefa)

    def _confirmar_descarte(self) -> bool:
        r = QMessageBox.question(
            self, "Descartar alterações",
            "Há alterações não salvas nesta tabela. Recarregar vai descartá-las.\n\n"
            "Deseja continuar?", Yes | No, No,
        )
        return r == Yes

    def _ok(self, linhas: list) -> None:
        colunas: list[str] = []
        for r in linhas:
            for k in r:
                if k not in colunas:
                    colunas.append(k)

        self._linhas = [dict(r) for r in linhas]
        self._colunas = colunas
        self._dirty = set()
        self._preencher_tabela()

        self.lbl.setText(f"{len(linhas)} linha(s) carregada(s) de '{self.tabela}'.")
        self.mensagem.emit(f"'{self.tabela}' carregada.")
        self.btn_salvar.setEnabled(False)

    def _preencher_tabela(self) -> None:
        self._carregando = True
        self.tabela_widget.setSortingEnabled(False)
        self.tabela_widget.clear()
        self.tabela_widget.setColumnCount(len(self._colunas))
        self.tabela_widget.setRowCount(len(self._linhas))
        self.tabela_widget.setHorizontalHeaderLabels(self._colunas)

        for i, linha in enumerate(self._linhas):
            for j, coluna in enumerate(self._colunas):
                valor = linha.get(coluna)
                item = QTableWidgetItem("" if valor is None else str(valor))
                self.tabela_widget.setItem(i, j, item)
        self.tabela_widget.resizeColumnsToContents()
        self.tabela_widget.setSortingEnabled(True)
        self._carregando = False

    def _erro(self, erro: str) -> None:
        self.lbl.setText(f"Erro: {erro}")
        self.mensagem.emit(f"Erro ao carregar '{self.tabela}'.")

    def _definir_ocupado(self, ocupado: bool) -> None:
        self.btn_carregar.setEnabled(not ocupado)
        self.btn_reverter.setEnabled(not ocupado)
        self.btn_salvar.setEnabled(not ocupado and bool(self._dirty))

    # ============================================================== edição
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._carregando:
            return
        linha, coluna = item.row(), item.column()
        nome_coluna = self._colunas[coluna]

        original = self._linhas[linha].get(nome_coluna)
        novo_valor = converter_como_original(item.text(), original)
        if novo_valor == original:
            return

        self._linhas[linha][nome_coluna] = novo_valor
        self._dirty.add(linha)
        for c in range(self.tabela_widget.columnCount()):
            self.tabela_widget.item(linha, c).setBackground(COR_ALTERADA)
        self.btn_salvar.setEnabled(True)
        self.lbl.setText(f"{len(self._dirty)} linha(s) alterada(s) — Salvar grava a tabela inteira.")

    # =============================================================== salvar
    def salvar(self) -> None:
        if not self._dirty:
            return
        n = len(self._dirty)
        r = QMessageBox.question(
            self, "Salvar no BigQuery",
            f"Gravar '{self.tabela}' com {len(self._linhas)} linha(s) ({n} alterada(s))?\n\n"
            "Isso substitui a tabela inteira e afeta todos os usuários do pyDoSap.",
            Yes | No, No,
        )
        if r != Yes:
            return

        self._definir_ocupado(True)
        self.mensagem.emit(f"Salvando '{self.tabela}'…")
        tarefa = Task(self.api.atualizar_configuracoes, self.tabela, list(self._linhas))
        tarefa.signals.result.connect(self._salvar_ok)
        tarefa.signals.error.connect(self._salvar_erro)
        tarefa.signals.done.connect(lambda: self._definir_ocupado(False))
        QThreadPool.globalInstance().start(tarefa)

    def _salvar_ok(self, mensagem: str) -> None:
        self._dirty.clear()
        for i in range(self.tabela_widget.rowCount()):
            for j in range(self.tabela_widget.columnCount()):
                self.tabela_widget.item(i, j).setBackground(QColor("transparent"))
        self.lbl.setText(f"{len(self._linhas)} linha(s) carregada(s) de '{self.tabela}'.")
        self.mensagem.emit(mensagem)
        QMessageBox.information(self, "Salvo", mensagem)

    def _salvar_erro(self, erro: str) -> None:
        self.mensagem.emit(f"Erro ao salvar '{self.tabela}'.")
        QMessageBox.critical(self, "Erro ao salvar", erro)

    # ============================================================== reverter
    def reverter(self) -> None:
        r = QMessageBox.warning(
            self, "Reverter última gravação",
            f"Restaurar '{self.tabela}' para o estado anterior à última gravação feita "
            "por qualquer usuário do pyDoSap?\n\nAlterações feitas depois dessa gravação "
            "(inclusive as desta tela) serão perdidas.",
            Yes | No, No,
        )
        if r != Yes:
            return
        self._definir_ocupado(True)
        self.mensagem.emit(f"Revertendo '{self.tabela}'…")
        tarefa = Task(self.api.reverter_configuracao, self.tabela)
        tarefa.signals.result.connect(self._reverter_ok)
        tarefa.signals.error.connect(self._salvar_erro)
        tarefa.signals.done.connect(lambda: self._definir_ocupado(False))
        QThreadPool.globalInstance().start(tarefa)

    def _reverter_ok(self, mensagem: str) -> None:
        self.mensagem.emit(mensagem)
        QMessageBox.information(self, "Revertido", mensagem)
        self.carregar()


class ConfigTab(QWidget):
    """Contêiner com uma sub-aba por tabela de configuração."""

    mensagem = Signal(str)

    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)

        abas = QTabWidget()
        for titulo, tabela in TABELAS:
            sub = ConfigTableTab(api, tabela)
            sub.mensagem.connect(self.mensagem)
            abas.addTab(sub, titulo)
        raiz.addWidget(abas)
