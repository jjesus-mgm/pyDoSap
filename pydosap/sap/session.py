"""Sessão do SAP GUI Scripting (equivalente ao SAP.bas do projeto VBA).

Requisitos: SAP GUI aberto e logado, scripting habilitado (cliente e servidor) e pywin32.
COM é por thread: em threads secundárias use `com_context()` e crie o SapSession
DENTRO da própria thread.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from enum import IntEnum
from typing import Any

from ..formatting import to_sap


class SapError(Exception):
    """Erro de conexão/interação com o SAP GUI."""


class GuiType(IntEnum):
    """GuiComponentType usados em FindByNameEx."""

    TEXT_FIELD = 31
    C_TEXT_FIELD = 32
    COMBO_BOX = 34
    BUTTON = 40
    CHECK_BOX = 42
    TABLE_CONTROL = 80
    CUSTOM_CONTROL = 50
    TAB = 91


@contextmanager
def com_context():
    """Inicializa/finaliza o COM na thread atual (no-op fora do Windows)."""
    try:
        import pythoncom
    except ImportError:
        pythoncom = None
    if pythoncom:
        pythoncom.CoInitialize()
    try:
        yield
    finally:
        if pythoncom:
            pythoncom.CoUninitialize()


class SapTable:
    """Wrapper de um GuiTableControl (índices de linha/coluna começam em 0)."""

    def __init__(self, com_obj: Any):
        self._t = com_obj

    @property
    def row_count(self) -> int:
        return int(self._t.Rows.Count)

    def get(self, linha: int, coluna: int) -> str:
        return str(self._t.GetCell(linha, coluna).Text)

    def set(self, linha: int, coluna: int, valor: Any) -> None:
        self._t.GetCell(linha, coluna).Text = to_sap(valor)


class SapSession:
    def __init__(self) -> None:
        self._ses: Any = None

    # ------------------------------------------------------------- conexão
    @property
    def connected(self) -> bool:
        return self._ses is not None

    def connect(self, *, maximizar: bool = True, conexao: int = 0, sessao: int = 0) -> None:
        """SAPGUI -> Application -> Connection -> Session."""
        try:
            import win32com.client
        except ImportError as e:
            raise SapError(
                "O SAP GUI Scripting exige Windows e o pacote pywin32 (pip install pywin32)."
            ) from e
        try:
            app = win32com.client.GetObject("SAPGUI").GetScriptingEngine
            self._ses = app.Children(conexao).Children(sessao)
            if maximizar:
                self._ses.ActiveWindow.Maximize()
        except Exception as e:  # com_error
            self._ses = None
            raise SapError(
                "Não foi possível conectar ao SAP GUI. Verifique se o SAP está aberto, "
                f"logado e com o scripting habilitado. ({e})"
            ) from e

    def disconnect(self) -> None:
        self._ses = None

    @property
    def _s(self) -> Any:
        if self._ses is None:
            raise SapError("Sessão SAP não inicializada (chame connect()).")
        return self._ses

    # --------------------------------------------------------------- infos
    def user(self) -> str:
        return str(self._s.Info.User)

    def mandante(self) -> str:
        """Cliente SAP logado (GuiSessionInfo.Client) — grava na coluna 'mandante' do log."""
        return str(self._s.Info.Client)

    def system_name(self) -> str:
        return str(self._s.Info.SystemName)

    def transaction(self) -> str:
        return str(self._s.Info.Transaction)

    # ----------------------------------------------------------- utilitários
    def wait_ready(self, timeout: float = 120.0) -> None:
        inicio = time.monotonic()
        while self._s.Busy:
            if time.monotonic() - inicio > timeout:
                raise SapError("Tempo esgotado aguardando o SAP ficar disponível.")
            time.sleep(0.05)

    def _find(self, nome: str, tipo: GuiType) -> Any:
        try:
            return self._s.ActiveWindow.FindByNameEx(nome, int(tipo))
        except Exception as e:
            raise SapError(
                f"Elemento '{nome}' ({tipo.name}) não encontrado na tela atual "
                f"[transação {self.transaction()}]. {e}"
            ) from e

    # ------------------------------------------------------------ navegação
    def start_transaction(self, codigo: str) -> None:
        self._s.StartTransaction(codigo)
        self.wait_ready()

    def end_transaction(self) -> None:
        self._s.EndTransaction()
        self.wait_ready()

    def send_enter(self) -> None:
        self._s.FindById("wnd[0]").SendVKey(0)
        self.wait_ready()

    def vkey(self, tecla: int) -> None:
        self._s.ActiveWindow.SendVKey(tecla)
        self.wait_ready()

    def select_tab(self, nome: str) -> None:
        self._find(nome, GuiType.TAB).Select()

    def click_button(self, nome: str) -> None:
        self._find(nome, GuiType.BUTTON).Press()
        self.wait_ready()

    # --------------------------------------------------------------- campos
    def fill_text(self, nome: str, valor: Any) -> None:
        """GuiTextField (31)."""
        self._find(nome, GuiType.TEXT_FIELD).Text = to_sap(valor)

    def fill_ctext(self, nome: str, valor: Any) -> None:
        """GuiCTextField (32)."""
        self._find(nome, GuiType.C_TEXT_FIELD).Text = to_sap(valor)

    def get_text(self, nome: str) -> str:
        return str(self._find(nome, GuiType.TEXT_FIELD).Text)

    def get_ctext(self, nome: str) -> str:
        return str(self._find(nome, GuiType.C_TEXT_FIELD).Text)

    def set_combo_key(self, nome: str, chave: Any) -> None:
        self._find(nome, GuiType.COMBO_BOX).Key = to_sap(chave)

    def set_checkbox(self, nome: str, marcado: bool) -> None:
        self._find(nome, GuiType.CHECK_BOX).Selected = bool(marcado)

    def table(self, nome: str) -> SapTable:
        return SapTable(self._find(nome, GuiType.TABLE_CONTROL))

    def label_text(self, id_absoluto: str) -> str:
        return str(self._s.FindById(id_absoluto).Text)

    # ------------------------------------------------------ acesso bruto
    @property
    def raw(self) -> Any:
        """Objeto COM da sessão (GuiSession), para grids/controles customizados
        (ex.: o CC_GRID da NP01) que não se encaixam nos wrappers acima."""
        return self._s

    def find_id(self, caminho_absoluto: str) -> Any:
        """Componente por ID absoluto (ex.: 'wnd[1]/usr/cntlCC_DOC/shellcont/shell')."""
        return self._s.FindById(caminho_absoluto)

    def find_name(self, nome: str, tipo: int) -> Any:
        """Equivalente a FindByNameEx na janela ativa, com o inteiro do GuiComponentType."""
        return self._find(nome, GuiType(tipo))

    # --------------------------------------------------------- barra/janela
    def status_text(self) -> str:
        return str(self._s.FindById("wnd[0]/sbar").Text)

    def status_type(self) -> str:
        """S=sucesso, E=erro, W=aviso, I=informação, ''=sem mensagem."""
        return str(self._s.FindById("wnd[0]/sbar").MessageType)

    def active_window_name(self) -> str:
        return str(self._s.ActiveWindow.Name)

    def active_window_type(self) -> str:
        return str(self._s.ActiveWindow.Type)

    def active_window_text(self) -> str:
        return str(self._s.ActiveWindow.Text)

    def recuperar(self) -> None:
        """Melhor esforço para deixar o SAP utilizável após uma falha (fecha pop-ups)."""
        try:
            for _ in range(5):
                if self.active_window_name() == "wnd[0]":
                    break
                self._s.ActiveWindow.SendVKey(12)  # Cancelar
        except Exception:
            pass
