"""Execução em segundo plano (a interface nunca bloqueia em chamadas de rede ou de SAP)."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from ..api_client import ApiClient
from ..models import ControleLancamento, Fornecimento, ResultadoNota
from ..sap.session import SapSession, com_context
from ..services.custo import CteCustoService
from ..services.lancamento import LancamentoService
from ..services.upload import enviar_xmls


class TaskSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    done = Signal()


class Task(QRunnable):
    """Roda uma função no pool de threads e devolve o resultado por sinais."""

    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs
        self.signals = TaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            resultado = self._fn(*self._args, **self._kwargs)
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(str(e))
        else:
            self.signals.result.emit(resultado)
        finally:
            self.signals.done.emit()


def testar_sap() -> dict:
    """Conecta ao SAP GUI (sem maximizar a janela) e devolve usuário/sistema."""
    with com_context():
        sap = SapSession()
        sap.connect(maximizar=False)
        return {"usuario": sap.user(), "sistema": sap.system_name(), "transacao": sap.transaction()}


class LancamentoWorker(QObject):
    """Lançamento em lote. O COM do SAP é criado dentro da própria thread."""

    progress = Signal(int, int, str)
    status = Signal(int, str)
    resultado = Signal(int, str, str, bool)
    log = Signal(str)
    falhou = Signal(str)
    concluido = Signal(object)  # ResumoLancamento
    finished = Signal()

    def __init__(self, api: ApiClient, linhas: list[tuple[int, dict]], controle: ControleLancamento):
        super().__init__()
        self._api, self._linhas, self._controle = api, linhas, controle
        self._parar = threading.Event()

    def parar(self) -> None:
        self._parar.set()

    @Slot()
    def run(self) -> None:
        try:
            with com_context():
                sap = SapSession()
                sap.connect()
                try:
                    sap.end_transaction()
                except Exception:  # noqa: BLE001 - não impede o lote
                    pass
                servico = LancamentoService(
                    self._api, sap,
                    on_log=self.log.emit,
                    on_progress=self.progress.emit,
                    on_status=self.status.emit,
                    on_result=self.resultado.emit,
                    should_stop=self._parar.is_set,
                )
                resumo = servico.lancar(self._linhas, self._controle)
        except Exception as e:  # noqa: BLE001
            self.falhou.emit(str(e))
        else:
            self.concluido.emit(resumo)
        finally:
            self.finished.emit()


class CustoWorker(QObject):
    """Lançamento de um único CT-e de custo (várias NFs + MIRO + fornecimento)."""

    log = Signal(str)
    nota = Signal(int, str, object, str)  # índice, chave da NF, ResultadoNota|None, etapa
    fornecimento = Signal(object)         # Fornecimento
    concluido = Signal(object)            # ResultadoCteCusto
    falhou = Signal(str)
    finished = Signal()

    def __init__(self, api: ApiClient, chave: str):
        super().__init__()
        self._api, self._chave = api, chave

    @Slot()
    def run(self) -> None:
        try:
            with com_context():
                sap = SapSession()
                sap.connect()
                servico = CteCustoService(
                    self._api, sap,
                    on_log=self.log.emit,
                    on_nota=lambda i, chave, res, etapa: self.nota.emit(i, chave, res, etapa),
                    on_fornecimento=self.fornecimento.emit,
                )
                resultado = servico.lancar(self._chave)
        except Exception as e:  # noqa: BLE001
            self.falhou.emit(str(e))
        else:
            self.concluido.emit(resultado)
        finally:
            self.finished.emit()


class UploadWorker(QObject):
    progress = Signal(int, int)
    resultado = Signal(str, bool, str)  # arquivo, ok, resposta
    concluido = Signal(int, int)        # enviados com sucesso, total
    falhou = Signal(str)
    finished = Signal()

    def __init__(self, api: ApiClient, arquivos: list[Path], forcar_integracao: bool = False):
        super().__init__()
        self._api, self._arquivos = api, arquivos
        self._forcar = forcar_integracao
        self._parar = threading.Event()

    def parar(self) -> None:
        self._parar.set()

    @Slot()
    def run(self) -> None:
        try:
            def ao_enviar(n, total, res):
                self.resultado.emit(res.arquivo, res.ok, res.resposta)
                self.progress.emit(n, total)

            resultados = enviar_xmls(
                self._api, self._arquivos, forcar_integracao=self._forcar,
                on_result=ao_enviar, should_stop=self._parar.is_set,
            )
        except Exception as e:  # noqa: BLE001
            self.falhou.emit(str(e))
        else:
            self.concluido.emit(sum(r.ok for r in resultados), len(self._arquivos))
        finally:
            self.finished.emit()
