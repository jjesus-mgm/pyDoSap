"""Aba principal: buscar CT-es, revisar/editar e lançar no SAP (equivale à planilha MENU)."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSortFilterProxyModel, Qt, QThread, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter,
    QTableView, QVBoxLayout, QWidget,
)

from ..api_client import ApiClient
from ..models import ControleLancamento, FiltroCTE, ResumoLancamento
from ..services.exportacao import exportar_ctes_excel
from .cte_model import CteTableModel
from .widgets import ChavesDialog, OptionalDateEdit, validador_sem_aspas
from .workers import LancamentoWorker, Task

from .styles import ALTURA_LINHA

Yes, No = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No

ALTURA_LINHA_COMPACTA = 22


def _primario(botao: QPushButton) -> QPushButton:
    botao.setProperty("primary", True)
    return botao


def _perigo(botao: QPushButton) -> QPushButton:
    botao.setProperty("danger", True)
    return botao


class LancamentoTab(QWidget):
    mensagem = Signal(str)            # texto para a barra de status
    execucao_alterada = Signal(bool)  # True enquanto o lote está rodando

    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._chaves: list[str] = []
        self._thread: QThread | None = None
        self._worker: LancamentoWorker | None = None
        self._buscando = False

        self.model = CteTableModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)  # procura em todas as colunas

        self._montar()
        self._conectar()
        self._carregar_listas_filtro()

    # ================================================================ layout
    def _montar(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.addWidget(self._grupo_filtros())
        raiz.addWidget(self._grupo_parametros())
        raiz.addLayout(self._barra_tabela())

        self.tabela = QTableView()
        self.tabela.setModel(self.proxy)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tabela.setSortingEnabled(True)
        self.tabela.sortByColumn(-1, Qt.SortOrder.AscendingOrder)  # sem ordenação inicial
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.verticalHeader().setDefaultSectionSize(ALTURA_LINHA)
        cab = self.tabela.horizontalHeader()
        cab.setSectionsMovable(True)
        cab.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        cab.customContextMenuRequested.connect(self._menu_colunas)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setPlaceholderText("Log da execução…")

        divisor = QSplitter(Qt.Orientation.Vertical)
        divisor.addWidget(self.tabela)
        divisor.addWidget(self.log_view)
        divisor.setStretchFactor(0, 4)
        divisor.setStretchFactor(1, 1)
        raiz.addWidget(divisor, 1)

        raiz.addLayout(self._rodape())

    def _grupo_filtros(self) -> QGroupBox:
        grupo = QGroupBox("Filtros de busca")
        grade = QGridLayout(grupo)

        self.f_regiao = QComboBox()
        self.f_regiao.setEditable(True)
        self.f_regiao.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.f_regiao.lineEdit().setPlaceholderText("Todas")
        self.f_regiao.lineEdit().setValidator(validador_sem_aspas())
        self.f_centro = QComboBox()
        self.f_centro.setEditable(True)
        self.f_centro.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.f_centro.lineEdit().setPlaceholderText("Todos")
        self.f_centro.lineEdit().setValidator(validador_sem_aspas())
        self.f_inicio = OptionalDateEdit()
        self.f_fim = OptionalDateEdit()
        self.f_nao_lancados = QCheckBox("Somente não lançados")
        self.f_validados = QCheckBox("Somente validados")
        self.f_validados.setChecked(True)  # padrão ao abrir o app
        self.btn_chaves = QPushButton("Chaves de acesso (0)…")
        self.btn_limpar = QPushButton("Limpar filtros")
        self.btn_buscar = _primario(QPushButton("Buscar CT-es"))

        grade.addWidget(QLabel("Região"), 0, 0)
        grade.addWidget(self.f_regiao, 0, 1)
        grade.addWidget(QLabel("Centro"), 0, 2)
        grade.addWidget(self.f_centro, 0, 3)
        grade.addWidget(QLabel("Emissão de"), 0, 4)
        grade.addWidget(self.f_inicio, 0, 5)
        grade.addWidget(QLabel("até"), 0, 6)
        grade.addWidget(self.f_fim, 0, 7)

        grade.addWidget(self.f_nao_lancados, 1, 0, 1, 2)
        grade.addWidget(self.f_validados, 1, 2, 1, 2)
        grade.addWidget(self.btn_chaves, 1, 4, 1, 2)
        grade.addWidget(self.btn_limpar, 1, 6)
        grade.addWidget(self.btn_buscar, 1, 7)
        grade.setColumnStretch(1, 1)
        grade.setColumnStretch(3, 1)
        return grupo

    def _grupo_parametros(self) -> QGroupBox:
        grupo = QGroupBox("Parâmetros do lançamento")
        lay = QHBoxLayout(grupo)
        self.e_chamado = QLineEdit()
        self.e_chamado.setPlaceholderText("Nº do chamado (vai no texto do cabeçalho da MIRO)")
        self.e_data = OptionalDateEdit()
        self.e_data.setToolTip("Data de lançamento (BUDAT). Vazia = padrão do SAP.")
        self.chk_ignorar = QCheckBox("Ignorar validação de integração do Lincros")
        lay.addWidget(QLabel("Chamado"))
        lay.addWidget(self.e_chamado, 1)
        lay.addWidget(QLabel("Data de lançamento"))
        lay.addWidget(self.e_data)
        lay.addSpacing(16)
        lay.addWidget(self.chk_ignorar)
        return grupo

    def _barra_tabela(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Filtrar na tabela…")
        self.busca.setClearButtonEnabled(True)
        self.busca.setMaximumWidth(320)
        self.btn_marcar = QPushButton("Marcar visíveis")
        self.btn_desmarcar = QPushButton("Desmarcar visíveis")
        self.chk_compacta = QCheckBox("Visualização compacta")
        self.btn_exportar = QPushButton("Exportar para Excel")
        self.lbl_contagem = QLabel("Nenhuma busca realizada.")
        lay.addWidget(self.busca)
        lay.addWidget(self.btn_marcar)
        lay.addWidget(self.btn_desmarcar)
        lay.addWidget(self.chk_compacta)
        lay.addWidget(self.btn_exportar)
        lay.addStretch(1)
        lay.addWidget(self.lbl_contagem)
        return lay

    def _rodape(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        self.progresso = QProgressBar()
        self.progresso.setValue(0)
        self.btn_parar = _perigo(QPushButton("Parar"))
        self.btn_parar.setEnabled(False)
        self.btn_lancar = _primario(QPushButton("Lançar selecionados no SAP"))
        lay.addWidget(self.progresso, 1)
        lay.addWidget(self.btn_parar)
        lay.addWidget(self.btn_lancar)
        return lay

    def _conectar(self) -> None:
        self.btn_buscar.clicked.connect(self.buscar)
        self.btn_limpar.clicked.connect(self._limpar_filtros)
        self.btn_chaves.clicked.connect(self._editar_chaves)
        self.btn_lancar.clicked.connect(self.lancar)
        self.btn_parar.clicked.connect(self.parar)
        self.btn_marcar.clicked.connect(self._marcar_visiveis)
        self.btn_desmarcar.clicked.connect(self._desmarcar_visiveis)
        self.busca.textChanged.connect(self._filtrar_tabela)
        self.chk_compacta.toggled.connect(self._alternar_compacta)
        self.btn_exportar.clicked.connect(self.exportar_excel)
        self.chk_ignorar.toggled.connect(self._confirmar_ignorar)
        self.tabela.doubleClicked.connect(self._duplo_clique)
        self.model.dataChanged.connect(self._atualizar_contagem)
        self.model.modelReset.connect(self._atualizar_contagem)

    # ============================================================== filtros
    def _filtro(self) -> FiltroCTE:
        return FiltroCTE(
            regiao=self.f_regiao.currentText(),
            centro=self.f_centro.currentText(),
            data_inicio=self.f_inicio.value(),
            data_fim=self.f_fim.value(),
            somente_nao_lancados=self.f_nao_lancados.isChecked(),
            somente_validados=self.f_validados.isChecked(),
            chaves=list(self._chaves),
        )

    def _limpar_filtros(self) -> None:
        r = QMessageBox.question(
            self, "Apagar filtros", "Todos os filtros serão apagados.\n\nDeseja continuar?", Yes | No, No
        )
        if r != Yes:
            return
        self.f_regiao.setCurrentText("")
        self.f_centro.setCurrentText("")
        self.f_inicio.clear_value()
        self.f_fim.clear_value()
        self.f_nao_lancados.setChecked(False)
        self.f_validados.setChecked(False)
        self._chaves = []
        self._atualizar_botao_chaves()

    def _editar_chaves(self) -> None:
        dlg = ChavesDialog(self._chaves, self)
        if dlg.exec():
            self._chaves = dlg.chaves()
            self._atualizar_botao_chaves()

    def _atualizar_botao_chaves(self) -> None:
        self.btn_chaves.setText(f"Chaves de acesso ({len(self._chaves)})…")

    def _confirmar_ignorar(self, marcado: bool) -> None:
        if not marcado:
            return
        r = QMessageBox.warning(
            self, "Confirmar alteração",
            "Ao ativar esta opção, a automação irá ignorar a validação de integração do Lincros."
            "\n\nDeseja continuar?", Yes | No, No,
        )
        if r != Yes:
            self.chk_ignorar.blockSignals(True)
            self.chk_ignorar.setChecked(False)
            self.chk_ignorar.blockSignals(False)

    def _carregar_listas_filtro(self) -> None:
        """Preenche os combos de Região/Centro com os valores distintos de
        regioes_csc.regiao e config_filiais.centro (config_tab.TABELAS)."""
        tarefa_regiao = Task(self.api.buscar_configuracoes, "regioes_csc")
        tarefa_regiao.signals.result.connect(lambda linhas: self._preencher_combo(self.f_regiao, linhas, "regiao"))
        tarefa_regiao.signals.error.connect(lambda erro: self.mensagem.emit(f"Não foi possível carregar as regiões: {erro}"))
        QThreadPool.globalInstance().start(tarefa_regiao)

        tarefa_centro = Task(self.api.buscar_configuracoes, "config_filiais")
        tarefa_centro.signals.result.connect(lambda linhas: self._preencher_combo(self.f_centro, linhas, "centro"))
        tarefa_centro.signals.error.connect(lambda erro: self.mensagem.emit(f"Não foi possível carregar os centros: {erro}"))
        QThreadPool.globalInstance().start(tarefa_centro)

    @staticmethod
    def _preencher_combo(combo: QComboBox, linhas: list[dict], coluna: str) -> None:
        valores = sorted({str(r[coluna]) for r in linhas if r.get(coluna) not in (None, "")})
        atual = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("")
        combo.addItems(valores)
        combo.setCurrentText(atual)
        combo.blockSignals(False)

    # =============================================================== busca
    def buscar(self) -> None:
        if self.em_execucao() or self._buscando:
            return
        self._buscando = True
        self._atualizar_estado()
        self.mensagem.emit("Buscando CT-es…")

        tarefa = Task(self.api.buscar_ctes, self._filtro())
        tarefa.signals.result.connect(self._busca_ok)
        tarefa.signals.error.connect(self._busca_erro)
        tarefa.signals.done.connect(self._busca_fim)
        QThreadPool.globalInstance().start(tarefa)

    def _busca_ok(self, linhas: list) -> None:
        self.model.load(linhas)
        self._ajustar_colunas()
        self.progresso.setValue(0)
        # como na planilha: cada nova busca zera os parâmetros do lançamento
        self.e_chamado.clear()
        self.e_data.clear_value()
        self.chk_ignorar.setChecked(False)
        n = len(linhas)
        self._log(f"Busca concluída: {n} CT-e(s).")
        self.mensagem.emit(f"{n} CT-e(s) encontrado(s)." if n else "Nenhum CT-e encontrado para este filtro.")

    def _busca_erro(self, erro: str) -> None:
        self._log(f"Erro na busca: {erro}")
        self.mensagem.emit("Erro ao buscar CT-es.")
        QMessageBox.critical(self, "Erro ao buscar CT-es", erro)

    def _busca_fim(self) -> None:
        self._buscando = False
        self._atualizar_estado()

    # ============================================================== tabela
    def _ajustar_colunas(self) -> None:
        self.tabela.resizeColumnsToContents()
        for c, nome in enumerate(self.model.colunas()):
            largura = self.model.largura_coluna(nome)
            if largura is not None:
                self.tabela.setColumnWidth(c, largura)
            elif self.tabela.columnWidth(c) > 320:
                self.tabela.setColumnWidth(c, 320)

    def _alternar_compacta(self, compacta: bool) -> None:
        self.tabela.verticalHeader().setDefaultSectionSize(
            ALTURA_LINHA_COMPACTA if compacta else ALTURA_LINHA
        )

    def exportar_excel(self) -> None:
        if self.model.rowCount() == 0:
            QMessageBox.information(self, "Exportar para Excel", "Não há CT-es carregados para exportar.")
            return

        caminho, _ = QFileDialog.getSaveFileName(
            self, "Exportar relatório de CT-es", "ctes_despesa.xlsx", "Planilha do Excel (*.xlsx)",
        )
        if not caminho:
            return

        cabecalho = self.tabela.horizontalHeader()
        colunas_modelo = self.model.colunas()
        ordem_visual = sorted(range(len(colunas_modelo)), key=cabecalho.visualIndex)
        colunas = [colunas_modelo[i] for i in ordem_visual if not self.tabela.isColumnHidden(i)]

        linhas = [
            self.model.linha(self.proxy.mapToSource(self.proxy.index(r, 0)).row())
            for r in range(self.proxy.rowCount())
        ]
        try:
            exportar_ctes_excel(caminho, colunas, linhas)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Erro ao exportar", str(e))
            return

        self.mensagem.emit(f"Relatório exportado: {caminho}")
        QMessageBox.information(self, "Exportado", f"{len(linhas)} linha(s) exportada(s) para:\n{caminho}")

    def _filtrar_tabela(self, texto: str) -> None:
        self.proxy.setFilterFixedString(texto)
        self._atualizar_contagem()

    def _indices_visiveis(self) -> list[int]:
        return [
            self.proxy.mapToSource(self.proxy.index(r, 0)).row()
            for r in range(self.proxy.rowCount())
        ]

    def _marcar_visiveis(self) -> None:
        self.model.marcar(self._indices_visiveis(), True)

    def _desmarcar_visiveis(self) -> None:
        self.model.marcar(self._indices_visiveis(), False)

    def _atualizar_contagem(self, *_args) -> None:
        total = self.model.rowCount()
        if total == 0:
            self.lbl_contagem.setText("Nenhum CT-e carregado.")
            return
        visiveis = self.proxy.rowCount()
        txt = f"{total} CT-e(s)"
        if visiveis != total:
            txt += f" ({visiveis} visíveis)"
        self.lbl_contagem.setText(f"{txt} — {self.model.total_marcados()} marcado(s) para lançar")

    def _menu_colunas(self, pos) -> None:
        menu = QMenu(self)
        for c in range(self.model.columnCount()):
            nome = self.model.headerData(c, Qt.Orientation.Horizontal)
            acao = menu.addAction(str(nome))
            acao.setCheckable(True)
            acao.setChecked(not self.tabela.isColumnHidden(c))
            acao.toggled.connect(lambda visivel, col=c: self.tabela.setColumnHidden(col, not visivel))
        menu.exec(self.tabela.horizontalHeader().mapToGlobal(pos))

    def _duplo_clique(self, indice) -> None:
        url = self.model.url(self.proxy.mapToSource(indice))
        if url:
            QDesktopServices.openUrl(QUrl(url))

    # ============================================================ lançamento
    def em_execucao(self) -> bool:
        return self._thread is not None

    def lancar(self) -> None:
        if self.em_execucao() or self._buscando:
            return
        linhas = self.model.linhas_marcadas()
        if not linhas:
            QMessageBox.information(self, "Lançar CT-es", "Nenhum CT-e marcado na coluna “Lançar”.")
            return

        controle = ControleLancamento(
            chamado=self.e_chamado.text().strip(),
            data_lancamento=self.e_data.value(),
            ignorar_validacao=self.chk_ignorar.isChecked(),
        )
        data_txt = controle.data_lancamento.strftime("%d/%m/%Y") if controle.data_lancamento else "padrão do SAP"
        r = QMessageBox.question(
            self, "Confirmar lançamento",
            f"Lançar {len(linhas)} CT-e(s) no SAP?\n\n"
            f"Chamado: {controle.chamado or '(não informado)'}\n"
            f"Data de lançamento: {data_txt}\n"
            f"Ignorar validação de integração: {'SIM' if controle.ignorar_validacao else 'não'}\n\n"
            "O SAP precisa estar aberto e logado. Não use o SAP enquanto o robô estiver rodando.",
            Yes | No, No,
        )
        if r != Yes:
            return

        self.progresso.setRange(0, len(linhas))
        self.progresso.setValue(0)
        self.model.travar(True)

        self._thread = QThread(self)
        self._worker = LancamentoWorker(self.api, linhas, controle)
        w = self._worker
        w.moveToThread(self._thread)
        self._thread.started.connect(w.run)
        w.progress.connect(self._on_progress)
        w.status.connect(self._on_status)
        w.resultado.connect(self._on_resultado)
        w.log.connect(self._log)
        w.falhou.connect(self._on_falhou)
        w.concluido.connect(self._on_concluido)
        w.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread_encerrada)

        self._atualizar_estado()
        self.execucao_alterada.emit(True)
        self._log(f"Iniciando o lançamento de {len(linhas)} CT-e(s)…")
        self._thread.start()

    def parar(self) -> None:
        if self._worker is not None:
            self._worker.parar()
            self.btn_parar.setEnabled(False)
            self._log("Parada solicitada: o CT-e em andamento será concluído antes de encerrar.")

    def _on_progress(self, atual: int, total: int, msg: str) -> None:
        self.progresso.setMaximum(max(total, 1))
        self.progresso.setValue(atual)
        self.mensagem.emit(msg)

    def _on_status(self, linha: int, status: str) -> None:
        self.model.set_status(linha, status)
        if status == "processando":
            self.tabela.scrollTo(self.proxy.mapFromSource(self.model.index(linha, 0)))

    def _on_resultado(self, linha: int, pedido: str, resposta: str, ok: bool) -> None:
        self.model.set_resultado(linha, pedido, resposta, ok)

    def _on_falhou(self, erro: str) -> None:
        self._log(f"ERRO: {erro}")
        QMessageBox.critical(self, "Falha no lançamento", erro)

    def _on_concluido(self, resumo: ResumoLancamento) -> None:
        titulo = "Lançamento interrompido" if resumo.interrompido else "Lançamento concluído"
        texto = f"{resumo.sucesso} lançado(s) com sucesso e {resumo.falha} com falha (de {resumo.total})."
        self._log(f"{titulo}: {texto}")
        self.mensagem.emit(texto)
        QMessageBox.information(self, titulo, texto + "\n\nConfira a coluna “Resposta” de cada CT-e.")

    def _thread_encerrada(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self.model.travar(False)
        self._atualizar_estado()
        self.execucao_alterada.emit(False)

    # =============================================================== estado
    def _atualizar_estado(self) -> None:
        ocupado = self.em_execucao() or self._buscando
        for w in (self.btn_buscar, self.btn_lancar, self.btn_limpar):
            w.setEnabled(not ocupado)
        self.btn_parar.setEnabled(self.em_execucao())

    def _log(self, msg: str) -> None:
        self.log_view.appendPlainText(f"{datetime.now():%H:%M:%S}  {msg}")
