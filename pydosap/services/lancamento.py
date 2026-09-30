"""Orquestração do lançamento de CT-es (porte do fluxo LancarCTEs do MAIN.bas).

Para cada CT-e marcado: busca o CT-e completo na API -> valida integração ->
cria o pedido de frete (ME21N) -> lança a fatura (MIRO) -> registra o log.

Sem dependência de Qt: a interface se conecta pelos callbacks.
"""
from __future__ import annotations

import getpass
from datetime import datetime
from typing import Callable, Sequence

from ..api_client import ApiClient
from ..models import ControleLancamento, Resp, ResumoLancamento
from ..sap.fatura import lancar_fatura
from ..sap.pedido import criar_pedido_frete
from ..sap.session import SapSession

CFG_PEDIDO = (
    "tipoPedido", "orgCompras", "grpCompradores", "funcaoParceiro",
    "catContabil", "material", "qtdPedido", "multPedido",
)
CFG_PEDAGIO = ("materialPedagio", "qtdPedidoPedagio", "ivaPedagio")
CFG_MIRO = ("catMiro",)

TABELA_CONFIG = "config_lancamento"
TIPO_LANCAMENTO = "DESPESA"  # CT-e de frete; CT-e de custo usa "CUSTO" (services/custo.py)

STATUS_PROCESSANDO = "processando"
STATUS_OK = "ok"
STATUS_ERRO = "erro"


def montar_resposta(pedido: Resp, miro: Resp) -> str:
    partes = [m for m in (pedido.mensagem, miro.mensagem) if m]
    return "\n".join(partes).strip()


def _faltando(cfg: dict, chaves: Sequence[str]) -> list[str]:
    return [k for k in chaves if cfg.get(k) in (None, "")]


class LancamentoService:
    def __init__(
        self,
        api: ApiClient,
        sap: SapSession,
        *,
        usuario: str | None = None,
        on_log: Callable[[str], None] | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
        on_status: Callable[[int, str], None] | None = None,
        on_result: Callable[[int, str, str, bool], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ):
        self.api = api
        self.sap = sap
        self.usuario = (usuario or getpass.getuser()).upper()
        self._log = on_log or (lambda msg: None)
        self._progress = on_progress or (lambda atual, total, msg: None)
        self._status = on_status or (lambda idx, status: None)
        self._result = on_result or (lambda idx, pedido, resposta, ok: None)
        self._stop = should_stop or (lambda: False)
        self.configs: list[dict] = []

    # ---------------------------------------------------------------- lote
    def lancar(self, linhas: Sequence[tuple[int, dict]], controle: ControleLancamento) -> ResumoLancamento:
        """`linhas`: (índice na tabela, dados da linha) apenas dos CT-es marcados para lançar."""
        resumo = ResumoLancamento(total=len(linhas))

        self._log("Carregando configurações de lançamento…")
        self.configs = self.api.buscar_configuracoes(TABELA_CONFIG)

        for n, (idx, base) in enumerate(linhas, start=1):
            if self._stop():
                resumo.interrompido = True
                self._log("Execução interrompida pelo usuário.")
                break

            rotulo = self._rotulo(base)
            self._progress(n - 1, resumo.total, f"Lançando {n}/{resumo.total}: {rotulo}")
            self._status(idx, STATUS_PROCESSANDO)
            self._log(f"[{n}/{resumo.total}] {rotulo}")

            pedido, miro, cte = self._processar(base, controle)
            self._registrar_log(base, cte, pedido, miro)

            ok = miro.sucesso
            resposta = montar_resposta(pedido, miro)
            self._status(idx, STATUS_OK if ok else STATUS_ERRO)
            self._result(idx, pedido.valor, resposta, ok)
            self._log(f"    {'OK' if ok else 'FALHA'}: {resposta or '(sem mensagem)'}")

            resumo.sucesso += int(ok)
            resumo.falha += int(not ok)

        self._progress(resumo.sucesso + resumo.falha, resumo.total, "Concluído")
        return resumo

    # ------------------------------------------------------------ um CT-e
    def _processar(self, base: dict, ctl: ControleLancamento) -> tuple[Resp, Resp, dict]:
        pedido, miro = Resp(), Resp()
        cte: dict = {}
        try:
            cte = self.api.buscar_cte_para_lancamento(str(base["oidDocumento"]))

            # dados informados pelo usuário na tabela / no formulário
            cte["codFornecedor"] = str(base.get("codFornecedor") or "").strip()
            cte["categoria"] = base.get("categoria")
            cte["chamado"] = ctl.chamado
            cte["dataLancamento"] = ctl.data_lancamento_iso
            cte["ignorarValidacao"] = ctl.ignorar_validacao

            if cte.get("possuiPendencia") and not ctl.ignorar_validacao:
                pedido = Resp(False, cte.get("mensagemIntegracao") or "Pendência de integração no Lincros.")
                return pedido, miro, cte

            erro = self._validar_entrada(cte, base)
            if erro:
                return Resp(False, erro), miro, cte

            pedido_existente = str(base.get("pedido") or "").strip()
            if pedido_existente:
                pedido = Resp(True, f"Já havia um pedido criado: {pedido_existente}", pedido_existente)
            else:
                pedido = criar_pedido_frete(self.sap, cte)

            if pedido.sucesso:
                cte["pedido"] = pedido.valor
                miro = lancar_fatura(self.sap, cte)
            else:
                self.sap.recuperar()

        except Exception as e:  # noqa: BLE001 - um CT-e com erro não pode derrubar o lote
            cte["erroExecucao"] = str(e)
            try:
                status = self.sap.status_text()
            except Exception:  # noqa: BLE001
                status = ""
            miro = Resp(False, f"Erro crítico na execução: {e} {status}".strip())
            try:
                self.sap.recuperar()
            except Exception:  # noqa: BLE001
                pass
        return pedido, miro, cte

    def _validar_entrada(self, cte: dict, base: dict) -> str:
        categoria = cte.get("categoria")
        cfg = next((c for c in self.configs if c.get("categoria") == categoria), None)
        if cfg is None:
            return f"Sem configuração de lançamento para a categoria '{categoria}'."
        cte["cfgLancamento"] = cfg

        if not str(base.get("pedido") or "").strip():
            if not cte["codFornecedor"]:
                return "Código do fornecedor não informado."
            faltam = _faltando(cfg, CFG_PEDIDO)
            if cte.get("calculos", {}).get("considerarPedagio"):
                faltam += _faltando(cfg, CFG_PEDAGIO)
            if faltam:
                return f"Configuração incompleta para '{categoria}': {', '.join(faltam)}."
        faltam = _faltando(cfg, CFG_MIRO)
        if faltam:
            return f"Configuração incompleta para '{categoria}': {', '.join(faltam)}."
        return ""

    # ----------------------------------------------------------------- log
    def _registrar_log(self, base: dict, cte: dict, pedido: Resp, miro: Resp) -> None:
        """Mesmo layout do log do VBA (tabela sapguibot_ctes.log)."""
        chave = cte.get("chave") or base.get("chave") or ""
        dados = cte or {
            k: base.get(k)
            for k in ("oidDocumento", "chave", "centro", "categoria", "codFornecedor", "pedido")
        }
        try:
            sap_user = self.sap.user()
        except Exception:  # noqa: BLE001
            sap_user = ""
        try:
            mandante = self.sap.mandante()
        except Exception:  # noqa: BLE001
            mandante = ""
        log = {
            "chave": f"chv{chave}",
            "data_hora": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "sap_user": sap_user,
            "excel_user": self.usuario,  # nome da coluna mantido por compatibilidade com o BigQuery
            "sucesso": miro.sucesso,
            "mensagem": montar_resposta(pedido, miro),
            "dados_processados": dados,
            "tipo_lancamento": TIPO_LANCAMENTO,
            "mandante": mandante,
        }
        try:
            self.api.inserir_log(log)
        except Exception as e:  # noqa: BLE001 - falha de log não interrompe o lote
            self._log(f"    ⚠ não foi possível registrar o log: {e}")

    @staticmethod
    def _rotulo(base: dict) -> str:
        chave = str(base.get("chave") or base.get("oidDocumento") or "?")
        return f"…{chave[-12:]}" if len(chave) > 14 else chave
