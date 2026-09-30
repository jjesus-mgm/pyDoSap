"""Lançamento da fatura na MIRO (porte de LANCAR_FATURA.bas)."""
from __future__ import annotations

from ..formatting import find_document_number, parse_sap_number, sap_date, sap_money
from ..models import Resp
from .pedido import alterar_fm_pedido
from .session import SapError, SapSession

TOLERANCIA_SALDO = 0.05
MAX_POPUPS = 20

# No VBA original a categoria da NF (J_1BNFTYPE) é preenchida com cfg["catMiro"] e, logo depois,
# sobrescrita por "Z7". O comportamento foi mantido; confirme se o segundo passo ainda é necessário.
CATEGORIA_NF_CTE = "Z7"


def lancar_fatura(sap: SapSession, cte: dict) -> Resp:
    """Executa a MIRO. Se sobrar saldo, troca o parceiro FM do pedido e refaz UMA vez."""
    while True:
        resp, refazer = _lancar_uma_vez(sap, cte)
        if not refazer:
            return resp


def _falha(mensagem: str) -> tuple[Resp, bool]:
    return Resp(sucesso=False, mensagem=mensagem, valor=""), False


def _lancar_uma_vez(sap: SapSession, cte: dict) -> tuple[Resp, bool]:
    cfg: dict = cte["cfgLancamento"]
    calc: dict = cte["calculos"]

    sap.start_transaction("miro")

    if sap.active_window_text() == "Entrar empresa":
        sap.fill_ctext("BKPF-BUKRS", cte.get("empresa"))
        sap.send_enter()

    sap.vkey(7)
    sap.fill_ctext("BKPF-BUKRS", cte.get("empresa"))
    sap.send_enter()
    sap.send_enter()

    sap.fill_ctext("INVFO-BLDAT", sap_date(cte.get("dataEmissao")))
    sap.send_enter()
    sap.send_enter()

    sap.fill_text("INVFO-XBLNR", cte.get("referencia"))
    sap.send_enter()

    # Data de lançamento (BUDAT): só é informada quando o usuário preencheu o campo.
    # (No VBA a variável de controle nunca era atribuída e a data informada era ignorada.)
    data_lancamento = sap_date(cte.get("dataLancamento"))
    if data_lancamento:
        sap.fill_ctext("INVFO-BUDAT", data_lancamento)
        sap.send_enter()
        sap.send_enter()

    sap.set_combo_key("RM08M-VORGANG", "1")  # garante que a operação seja Fatura
    sap.fill_ctext("INVFO-BUPLA", cte.get("localNegocios"))
    # (O VBA preenchia INVFO-SGTXT com calc("texto"), chave que não existe; o texto correto
    #  é informado mais adiante, depois de transferir o pedido.)
    sap.send_enter()
    sap.send_enter()

    sap.fill_text("INVFO-WRBTR", sap_money(cte.get("valorDocumento")))
    sap.send_enter()

    sap.set_combo_key("RM08M-REFERENZBELEGTYP", "1")

    sap.click_button("RM08M-XMSEL")
    sap.fill_ctext("RM08M-EBELN", cte.get("pedido"))
    sap.send_enter()  # validar

    if sap.active_window_name() == "wnd[1]":
        sap.vkey(8)

    if sap.active_window_name() == "wnd[1]":
        return _falha(sap.status_text())

    sap.fill_ctext("INVFO-SGTXT", calc.get("textoPedido"))
    sap.click_button("btn[0]")

    for _ in range(MAX_POPUPS):
        if sap.active_window_type() != "GuiModalWindow":
            break
        sap.send_enter()
    else:
        raise SapError("Pop-up do SAP não foi fechado após várias tentativas.")

    saldo = parse_sap_number(sap.get_text("RM08M-DIFFERENZ"))
    if abs(saldo) > TOLERANCIA_SALDO and not cte.get("fornecedorPedidoModificado"):
        alterar_fm_pedido(sap, cte)
        cte["fornecedorPedidoModificado"] = True
        return Resp(), True

    if sap.status_type() == "W":
        sap.send_enter()

    if sap.active_window_name() == "wnd[1]":
        return _falha(sap.status_text())

    sap.select_tab("HEADER_FI")
    sap.fill_ctext("INVFO-J_1BNFTYPE", cfg.get("catMiro"))
    sap.fill_text("INVFO-BKTXT", cte.get("chamado"))
    sap.send_enter()

    sbar = sap.status_text()
    if sbar.startswith("Verificar"):  # documento já lançado
        return _falha(sbar)

    sap.select_tab("HEADER_FI")
    sap.fill_ctext("INVFO-J_1BNFTYPE", CATEGORIA_NF_CTE)
    sap.fill_text("INVFO-BKTXT", cte.get("chamado"))

    sap.select_tab("HEADER_PAY")
    sap.fill_text("INVFO-ZBD1T", calc.get("diasVencimento"))
    sap.send_enter()

    sap.fill_ctext("INVFO-ZLSCH", "D")
    sap.send_enter()
    sap.vkey(21)
    sap.send_enter()

    sbar = sap.status_text()
    if sbar.startswith("Impossível"):
        return _falha(sbar)

    sap.select_tab("TAB8")
    sap.fill_text("J_1BNFE_DOCNUM9_DIVIDED-DOCNUM8", cte.get("aleatorio"))
    sap.fill_ctext("J_1BNFE_DOCNUM9_DIVIDED-TPEMIS", cte.get("tpEmis"))
    sap.fill_text("J_1BNFE_ACTIVE-CDV", cte.get("verificador"))
    sap.fill_text("J_1BDYDOC-AUTHCOD", cte.get("numeroProtocolo"))
    sap.fill_ctext("J_1BDYDOC-AUTHDATE", sap_date(cte.get("dataSefaz")))
    sap.fill_ctext("J_1BDYDOC-AUTHTIME", cte.get("horaSefaz"))
    sap.send_enter()

    if sap.status_type() == "E":
        return _falha(sap.status_text())

    sap.select_tab("TCTE")
    sap.fill_ctext("J_1BDYDOC-CTE_STRT_LCT", cte.get("munIni"))
    sap.fill_ctext("J_1BDYDOC-CTE_END_LCT", cte.get("munFim"))
    sap.send_enter()

    sap.vkey(3)
    if sap.status_text() == "Doc.faturamento ainda contém mensagens":
        sap.vkey(13)
        mensagens = _ler_mensagens_popup(sap)
        ultima = mensagens[-1] if mensagens else ""
        if "foram selecionados custos" in ultima:
            sap.send_enter()
        else:
            return _falha("\n".join(mensagens))

    sap.vkey(11)  # Salvar

    mensagem = sap.status_text()
    numero = find_document_number(mensagem)
    # (O VBA nunca marcava sucesso=True na MIRO; aqui é sucesso quando o nº do documento é identificado.)
    return Resp(sucesso=bool(numero), mensagem=mensagem, valor=numero), False


def _ler_mensagens_popup(sap: SapSession) -> list[str]:
    mensagens: list[str] = []
    for i in range(3, 11):
        try:
            texto = sap.label_text(f"wnd[1]/usr/lbl[5,{i}]").strip()
        except Exception:
            continue
        if texto:
            mensagens.append(texto)
    return mensagens
