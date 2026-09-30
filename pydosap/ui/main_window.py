"""Janela principal."""
from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QMainWindow, QMessageBox, QTabWidget, QVBoxLayout

from ..api_client import ApiClient
from ..config import API_BASE_URL, API_TOKEN, APP_NAME, APP_VERSION, ASSETS_DIR
from .config_tab import ConfigTab
from .custo_tab import CustoTab
from .lancamento_tab import LancamentoTab
from .upload_tab import UploadTab
from .workers import Task, testar_sap


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — Escrituração de CT-es no SAP")
        self.resize(1440, 880)

        icone = ASSETS_DIR / "icon.png"
        if icone.exists():
            self.setWindowIcon(QIcon(str(icone)))

        self.api = ApiClient()

        self.aba_lancamento = LancamentoTab(self.api)
        self.aba_custo = CustoTab(self.api)
        self.aba_config = ConfigTab(self.api)
        self.aba_upload = UploadTab(self.api)

        abas = QTabWidget()
        abas.addTab(self.aba_lancamento, "Lançamento")
        abas.addTab(self.aba_custo, "CT-e de Custo")
        abas.addTab(self.aba_config, "Configurações de lançamento")
        abas.addTab(self.aba_upload, "Upload de XML")
        self.setCentralWidget(abas)
        self._abas = abas

        self.lbl_sap = QLabel("SAP: não verificado")
        self.lbl_api = QLabel("API: verificando…")
        self.statusBar().addPermanentWidget(self.lbl_sap)
        self.statusBar().addPermanentWidget(self.lbl_api)

        for aba in (self.aba_lancamento, self.aba_custo, self.aba_config, self.aba_upload):
            aba.mensagem.connect(self._mostrar_mensagem)

        # trava a troca de aba e o fechamento da janela enquanto algo está rodando
        for aba in (self.aba_lancamento, self.aba_custo, self.aba_upload):
            aba.execucao_alterada.connect(self._travar_abas)

        self._montar_menu()
        QTimer.singleShot(200, self.verificar_api)

    # ---------------------------------------------------------------- menu
    def _montar_menu(self) -> None:
        arquivo = self.menuBar().addMenu("&Arquivo")

        a_api = QAction("Verificar &API", self)
        a_api.setShortcut(QKeySequence("F5"))
        a_api.triggered.connect(self.verificar_api)
        arquivo.addAction(a_api)

        a_sap = QAction("Testar conexão com o &SAP", self)
        a_sap.triggered.connect(self.testar_sap)
        arquivo.addAction(a_sap)

        arquivo.addSeparator()
        a_sair = QAction("Sai&r", self)
        a_sair.setShortcut(QKeySequence.StandardKey.Quit)
        a_sair.triggered.connect(self.close)
        arquivo.addAction(a_sair)

        ajuda = self.menuBar().addMenu("A&juda")
        a_sobre = QAction("&Sobre", self)
        a_sobre.triggered.connect(self._sobre)
        ajuda.addAction(a_sobre)

    def _sobre(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Sobre o {APP_NAME}")
        lay = QVBoxLayout(dlg)

        banner = ASSETS_DIR / "logo_dark.png"
        if banner.exists():
            pix = QPixmap(str(banner))
            lbl_img = QLabel()
            lbl_img.setPixmap(pix)
            lbl_img.setStyleSheet("background: #000000; border-radius: 8px; padding: 12px;")
            lay.addWidget(lbl_img)

        texto = QLabel(
            f"<b>{APP_NAME}</b> {APP_VERSION}<br>"
            "Lançamento de CT-es (frete e custo) no SAP via SAP GUI Scripting.<br><br>"
            f"API: {API_BASE_URL}"
        )
        texto.setTextInteractionFlags(texto.textInteractionFlags() | texto.textInteractionFlags().TextSelectableByMouse)
        lay.addWidget(texto)
        dlg.exec()

    # ------------------------------------------------------------ status bar
    def _mostrar_mensagem(self, texto: str) -> None:
        self.statusBar().showMessage(texto)

    def _travar_abas(self, ocupado: bool) -> None:
        self._abas.tabBar().setEnabled(not ocupado)

    def verificar_api(self) -> None:
        self.lbl_api.setText("API: verificando…")
        tarefa = Task(self.api.status)
        tarefa.signals.result.connect(self._api_ok)
        tarefa.signals.error.connect(self._api_erro)
        QThreadPool.globalInstance().start(tarefa)

    def _api_ok(self, _texto: str) -> None:
        self.lbl_api.setText("API: online ✔")
        self.lbl_api.setToolTip(API_BASE_URL)

    def _api_erro(self, erro: str) -> None:
        aviso = " (token não configurado no .env)" if not API_TOKEN else ""
        self.lbl_api.setText(f"API: indisponível ✖{aviso}")
        self.lbl_api.setToolTip(erro)

    def testar_sap(self) -> None:
        self.lbl_sap.setText("SAP: verificando…")
        tarefa = Task(testar_sap)
        tarefa.signals.result.connect(self._sap_ok)
        tarefa.signals.error.connect(self._sap_erro)
        QThreadPool.globalInstance().start(tarefa)

    def _sap_ok(self, info: dict) -> None:
        self.lbl_sap.setText(f"SAP: {info['sistema']} · {info['usuario']} ✔")
        self.lbl_sap.setToolTip(f"Transação atual: {info['transacao']}")

    def _sap_erro(self, erro: str) -> None:
        self.lbl_sap.setText("SAP: sem conexão ✖")
        self.lbl_sap.setToolTip(erro)
        QMessageBox.warning(self, "SAP", erro)

    # --------------------------------------------------------------- encerrar
    def closeEvent(self, evento) -> None:
        em_execucao = (
            self.aba_lancamento.em_execucao()
            or self.aba_custo.em_execucao()
            or self.aba_upload.em_execucao()
        )
        if em_execucao:
            QMessageBox.warning(
                self, "Operação em andamento",
                "Há um lançamento/upload em andamento. Use “Parar” (quando disponível) e "
                "aguarde o término antes de fechar.",
            )
            evento.ignore()
            return
        super().closeEvent(evento)
