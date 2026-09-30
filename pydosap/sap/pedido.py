"""Criação do pedido de frete na ME21N (porte de CRIAR_PEDIDO.bas).

Depende apenas da interface pública de SapSession (facilita testar com um SAP falso).
"""
from __future__ import annotations

from ..formatting import find_document_number
from ..models import Resp
from .session import SapSession

TABELA_PARCEIROS = "SAPLEKPATC_0111"
TABELA_ITENS = "SAPLMEGUITC_1211"


def _preencher_parceiro(sap: SapSession, cfg: dict, codigo) -> bool:
    """Preenche a primeira linha vazia (ou que já tenha 'FM') da tabela de parceiros."""
    tbl = sap.table(TABELA_PARCEIROS)
    for i in range(tbl.row_count):
        if tbl.get(i, 0) in ("FM", ""):
            tbl.set(i, 0, cfg.get("funcaoParceiro"))
            tbl.set(i, 2, codigo)
            return True
    return False


def criar_pedido_frete(sap: SapSession, cte: dict) -> Resp:
    cfg: dict = cte["cfgLancamento"]
    calc: dict = cte["calculos"]
    resp = Resp()

    sap.start_transaction("me21n")

    sap.set_combo_key("MEPO_TOPLINE-BSART", cfg.get("tipoPedido"))
    sap.fill_ctext("MEPO_TOPLINE-SUPERFIELD", cte.get("codFornecedor"))
    sap.send_enter()

    sap.select_tab("TABHDT8")
    sap.fill_ctext("MEPO1222-EKORG", cfg.get("orgCompras"))
    sap.fill_ctext("MEPO1222-EKGRP", cfg.get("grpCompradores"))
    sap.fill_ctext("MEPO1222-BUKRS", cte.get("empresa"))
    sap.send_enter()

    if sap.status_type() == "E" and sap.status_text() != "Inserir Cond.pgto.":
        return _finalizar(sap, resp)

    sap.fill_ctext("MEPO1226-ZTERM", calc.get("condicaoPagamento"))
    sap.send_enter()

    sap.select_tab("TABHDT6")
    _preencher_parceiro(sap, cfg, cte.get("codFornecedor"))
    sap.send_enter()

    sap.vkey(27)
    sap.vkey(29)
    sap.fill_ctext("MEPO1211-KNTTP", cfg.get("catContabil"))
    sap.fill_ctext("MEPO1211-EMATN", cfg.get("material"))
    sap.fill_text("MEPO1211-NETPR", calc.get("valorPedido"))
    sap.fill_text("MEPO1211-MENGE", cfg.get("qtdPedido"))
    sap.fill_text("MEPO1211-PEINH", cfg.get("multPedido"))
    sap.fill_ctext("MEPO1211-NAME1", cte.get("centro"))
    sap.send_enter()

    # erro de material. (No VBA os argumentos do InStr estavam invertidos e a
    # condição praticamente nunca era verdadeira; aqui a intenção foi implementada.)
    if sap.status_type() == "E" and "material" in sap.status_text().lower():
        return _finalizar(sap, resp)
    sap.vkey(28)

    sap.select_tab("TABIDT15")
    sap.fill_ctext("COBL-KOSTL", cte.get("centroCusto"))
    sap.send_enter()

    sap.select_tab("TABIDT8")
    sap.fill_ctext("MEPO1317-TXJCD", cte.get("munFim"))
    sap.fill_ctext("MEPO1317-MWSKZ", calc.get("ivaCalc"))
    sap.send_enter()

    sap.select_tab("TABIDT7")
    sap.set_checkbox("MEPO1313-WEPOS", False)

    # Repete para garantir: às vezes o SAP troca o valor pelo do último pedido em memória.
    sap.fill_text("MEPO1211-NETPR", calc.get("valorPedido"))
    sap.fill_text("MEPO1211-PEINH", cfg.get("multPedido"))
    sap.send_enter()

    if cte.get("possuiPedagio") and calc.get("considerarPedagio"):
        lancar_linha_pedagio(sap, cte, calc, cfg)

    sap.send_enter()

    if sap.status_type() != "E":
        sap.send_enter()
        sap.vkey(11)  # Salvar

    if sap.status_type() in ("S", ""):
        numero = find_document_number(sap.status_text())
        if numero:
            resp.valor = numero
            resp.sucesso = True

    return _finalizar(sap, resp)


def _finalizar(sap: SapSession, resp: Resp) -> Resp:
    resp.mensagem = sap.status_text()
    if not resp.sucesso:
        resp.valor = ""
    elif not resp.valor:
        resp.sucesso = False
    return resp


def alterar_fm_pedido(sap: SapSession, cte: dict) -> None:
    """Reabre o pedido criado e troca o parceiro FM (usado quando a MIRO fica com saldo)."""
    cfg: dict = cte["cfgLancamento"]
    calc: dict = cte["calculos"]

    sap.start_transaction("me21n")
    sap.vkey(17)  # outro documento
    sap.fill_ctext("MEPO_SELECT-EBELN", cte.get("pedido"))
    sap.send_enter()

    sap.vkey(7)
    sap.vkey(26)

    sap.select_tab("TABHDT6")
    _preencher_parceiro(sap, cfg, cte.get("centro"))
    sap.send_enter()

    sap.fill_text("MEPO1211-NETPR", calc.get("valorPedido"))
    sap.fill_text("MEPO1211-MENGE", cfg.get("qtdPedido"))
    sap.fill_text("MEPO1211-PEINH", cfg.get("multPedido"))
    sap.send_enter()
    sap.vkey(11)  # Salvar


def lancar_linha_pedagio(sap: SapSession, cte: dict, calc: dict, cfg: dict) -> None:
    """Segundo item do pedido, com o valor do pedágio."""
    tbl = sap.table(TABELA_ITENS)
    tbl.set(1, 2, cfg.get("catContabil"))
    tbl.set(1, 4, cfg.get("materialPedagio"))
    tbl.set(1, 6, cfg.get("qtdPedidoPedagio"))
    tbl.set(1, 10, calc.get("valorPedidoPedagio"))
    tbl.set(1, 12, cfg.get("multPedido"))
    tbl.set(1, 15, cte.get("centro"))
    sap.send_enter()

    sap.set_combo_key("DYN_6000-LIST", "   2")  # seleciona o item 20 do pedido
    sap.send_enter()

    sap.select_tab("TABIDT15")
    sap.fill_ctext("COBL-KOSTL", cte.get("centroCusto"))
    sap.send_enter()

    sap.select_tab("TABIDT8")
    sap.fill_ctext("MEPO1317-TXJCD", cte.get("munIni"))
    sap.fill_ctext("MEPO1317-MWSKZ", cfg.get("ivaPedagio"))
    sap.send_enter()

    sap.select_tab("TABIDT7")
    sap.set_checkbox("MEPO1313-WEPOS", False)

    # Repete para não aproveitar o valor em cache no item do pedágio.
    tbl = sap.table(TABELA_ITENS)
    tbl.set(1, 10, calc.get("valorPedidoPedagio"))
    tbl.set(1, 12, cfg.get("multPedido"))
    sap.send_enter()
