"""Orquestração do lançamento de um CT-e de custo (porte de LancarCteCusto, em
MAIN_CUSTO.bas): simula e lança cada NF vinculada, lança a MIRO do CT-e e, se der
certo, busca e fornece as ordens de venda casadas ao pedido. Sempre registra o log
(regra de ouro: todo lançamento, de custo ou de despesa, precisa ficar registrado).
"""
from __future__ import annotations

import getpass
from datetime import datetime
from typing import Callable

from ..api_client import ApiClient
from ..models import Fornecimento, ResultadoCteCusto, ResultadoNota
from ..sap.custo import (
    buscar_ordens_venda_casada, fornecer_ordem_venda, lancar_miro_custo, lancar_nota,
    simular_fatura,
)
from ..sap.session import SapSession

TIPO_LANCAMENTO = "CUSTO"  # CT-e de frete usa "DESPESA" (services/lancamento.py)


class CteCustoService:
    def __init__(
        self,
        api: ApiClient,
        sap: SapSession,
        *,
        usuario: str | None = None,
        on_log: Callable[[str], None] | None = None,
        on_nota: Callable[[int, str, ResultadoNota | None, str], None] | None = None,
        on_fornecimento: Callable[[Fornecimento], None] | None = None,
    ):
        self.api = api
        self.sap = sap
        self.usuario = (usuario or getpass.getuser()).upper()
        self._log = on_log or (lambda msg: None)
        # (índice da NF, chave, resultado ou None se ainda "simulando/lançando", etapa)
        self._nota = on_nota or (lambda i, chave, resultado, etapa: None)
        self._fornecimento = on_fornecimento or (lambda f: None)

    def buscar_cte(self, chave: str) -> dict:
        if len(chave) != 44:
            raise ValueError("Chave de acesso inválida.")
        return self.api.buscar_cte_custo(chave)

    def lancar(self, chave: str) -> ResultadoCteCusto:
        cte: dict = {}
        resultado = ResultadoCteCusto()
        try:
            cte, resultado = self._processar(chave)
        except Exception as e:  # noqa: BLE001 - qualquer falha ainda precisa virar log
            resultado.mensagem = f"Erro crítico na execução: {e}"
            try:
                self.sap.recuperar()
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._registrar_log(chave, cte, resultado)
        return resultado

    # ------------------------------------------------------------ um CT-e
    def _processar(self, chave: str) -> tuple[dict, ResultadoCteCusto]:
        cte = self.buscar_cte(chave)
        chaves_nf: list[str] = list(cte["infCte"]["chaves"])
        resultado = ResultadoCteCusto()

        # 1) simula a fatura de cada NF antes de lançar qualquer coisa
        for i, chave_nf in enumerate(chaves_nf):
            self._nota(i, chave_nf, None, "simulando")
            self._log(f"Simulando fatura da NF {chave_nf}…")
            sim = simular_fatura(self.sap, chave_nf)
            if not sim.sucesso:
                resultado.mensagem = sim.mensagem
                self._nota(i, chave_nf, ResultadoNota(False, mensagem=sim.mensagem), "simulacao")
                return cte, resultado
            self._nota(i, chave_nf, ResultadoNota(True, mensagem="OK"), "simulacao")

        # 2) lança (MIGO+MIRO) cada NF
        for i, chave_nf in enumerate(chaves_nf):
            self._nota(i, chave_nf, None, "lancando")
            self._log(f"Lançando a NF {chave_nf}…")
            nota = lancar_nota(self.sap, chave_nf)
            self._nota(i, chave_nf, nota, "lancamento")
            if not nota.sucesso:
                resultado.mensagem = nota.mensagem
                return cte, resultado

        # 3) MIRO do CT-e de custo, referenciando todas as NFs
        self._log("Lançando a fatura do CT-e de custo…")
        miro = lancar_miro_custo(self.sap, cte)
        resultado.sucesso = miro.sucesso
        resultado.mensagem = miro.mensagem
        if not miro.sucesso:
            return cte, resultado

        # 4) busca e fornece as ordens de venda casadas ao pedido gerado
        self._log(f"Buscando ordens de venda vinculadas ao documento {miro.miro}…")
        ordens = buscar_ordens_venda_casada(self.sap, miro.miro)
        if not ordens:
            return cte, resultado

        self._log(f"Fornecendo {len(ordens)} ordem(ns) de venda…")
        fornecimentos = fornecer_ordem_venda(self.sap, ordens)
        resultado.fornecimentos = fornecimentos
        for f in fornecimentos:
            self._fornecimento(f)

        return cte, resultado

    # ----------------------------------------------------------------- log
    def _registrar_log(self, chave: str, cte: dict, resultado: ResultadoCteCusto) -> None:
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
            "excel_user": self.usuario,
            "sucesso": resultado.sucesso,
            "mensagem": resultado.mensagem,
            "dados_processados": cte or {"chave": chave},
            "tipo_lancamento": TIPO_LANCAMENTO,
            "mandante": mandante,
        }
        try:
            self.api.inserir_log(log)
        except Exception as e:  # noqa: BLE001 - falha de log não pode mascarar o resultado
            self._log(f"    ⚠ não foi possível registrar o log: {e}")
