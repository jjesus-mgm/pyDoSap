"""Lançamento de CT-e de custo (porte de MAIN_CUSTO.bas, LANCAR_NOTAS.bas,
LANCAR_FATURA.bas e FORNECER_ORDENS.bas do projeto ESCRITURACAO_CTES_CUSTO).

Fluxo (uma chave de CT-e pode ter várias NFs vinculadas em cte["chaves"]):
  1. simular_fatura      -> /FHEFI/NP01, para cada NF: confere se o valor bate
  2. lancar_nota          -> /FHEFI/NP01, para cada NF: gera MIGO + MIRO (ou reaproveita
                             se a NF já estava lançada)
  3. lancar_miro_custo    -> MIRO do próprio CT-e, referenciando todas as NFs
  4. buscar_ordens_venda_casada -> reabre a MIRO do CT-e e lê, por item, o pedido e a
                             ordem de venda vinculada (COBL-KDAUF)
  5. fornecer_ordem_venda -> para cada ordem de venda encontrada, roda o fornecimento
                             (VA02) e captura o número da remessa gerada

Diferente do fluxo de frete (sap/pedido.py, sap/fatura.py), aqui as telas usam grids
customizados (CC_GRID, GuiShell) que não se encaixam nos wrappers genéricos de
SapSession — por isso as funções abaixo usam `sap.raw`/`sap.find_id` diretamente,
como uma extensão fiel ao VBA original.
"""
from __future__ import annotations

from ..formatting import criar_referencia, parse_sap_number, sap_date
from ..models import Fornecimento, ResultadoMiroCusto, ResultadoNota, SimulacaoFatura
from .session import SapSession

TOLERANCIA_SALDO = 0.05
TRANSACAO_NP01 = "/FHEFI/NP01"

# A categoria de NF-e é sempre travada em "Z7" no cabeçalho FI da MIRO do CT-e de
# custo (igual ao fluxo de frete) — ver observação equivalente em sap/fatura.py.
CATEGORIA_NF_CTE = "Z7"


def _abrir_np01(sap: SapSession, chave_nf: str) -> str | None:
    """Abre a NP01 filtrada pela NF e seleciona a linha; devolve None se achou a NF
    ou uma mensagem de erro se não encontrou nenhuma."""
    sap.start_transaction(TRANSACAO_NP01)
    sap.click_button("%#AUTOTEXT001")
    sap.click_button("%#AUTOTEXT002")
    sap.set_checkbox("CHK_STPR_SUC", True)
    sap.fill_text("S_NFKEY-LOW", chave_nf)
    sap.vkey(8)

    janela = sap.raw.ActiveWindow
    if janela.Text == "Mensagens" or janela.Name == "wnd[1]":
        return "Nenhuma nota fiscal encontrada"

    tbl_notas = sap.find_name("CC_GRID", 50)
    grid = tbl_notas.FindById("shellcont/shell/shellcont[1]/shell")
    grid.SelectedRows = "0"
    grid.PressToolbarButton("PROC")
    return None


def simular_fatura(sap: SapSession, chave_nf: str) -> SimulacaoFatura:
    """Confere se o valor da fatura simulada bate com o valor da NF (tolerância de
    R$ 0,05). Não lança nada — só valida antes de processar o lote."""
    erro = _abrir_np01(sap, chave_nf)
    if erro:
        return SimulacaoFatura(sucesso=False, mensagem=erro)

    sap.click_button("BTN_SIMUL")
    vlr_nf = parse_sap_number(sap.get_text("G_TOT_SIMUL_NF"))
    vlr_fat = parse_sap_number(sap.get_text("G_TOT_SIMUL_FAT"))
    saldo = vlr_fat - vlr_nf

    if abs(saldo) > TOLERANCIA_SALDO:
        sap.end_transaction()
        return SimulacaoFatura(
            sucesso=False, saldo=saldo,
            mensagem=f"Diferença de R$ {saldo:.2f} encontrada na NF {criar_referencia(chave_nf)}",
        )
    return SimulacaoFatura(sucesso=True, saldo=saldo)


def lancar_nota(sap: SapSession, chave_nf: str) -> ResultadoNota:
    """Lança a entrada de mercadoria (MIGO) e a fatura (MIRO) de uma NF na NP01,
    ou recupera os números dos documentos se a NF já estava lançada."""
    erro = _abrir_np01(sap, chave_nf)
    if erro:
        return ResultadoNota(sucesso=False, mensagem=erro)

    sap.click_button("BTN_PROC")
    documentos = sap.find_id("wnd[1]/usr/cntlCC_DOC/shellcont/shell")

    migo = miro = ""
    try:
        migo = str(documentos.GetCellValue(0, "DOCNR"))
        miro = str(documentos.GetCellValue(1, "DOCNR"))
    except Exception:  # noqa: BLE001 - grid pode não ter as linhas ainda
        pass

    if migo and miro:
        return ResultadoNota(
            sucesso=True, migo=migo, miro=miro, mensagem="Nota fiscal já estava lançada",
        )

    commands = sap.find_name("shell", 50)
    if not migo:
        commands.SetCurrentCell(1, "EXEC_")
        commands.ClickCurrentCell()
        if sap.raw.ActiveWindow.Name == "wnd[2]":
            return ResultadoNota(sucesso=False, mensagem="Erro ao lançar a NF")
        migo = str(documentos.GetCellValue(0, "DOCNR"))

    if not miro:
        commands.SetCurrentCell(2, "EXEC_")
        commands.ClickCurrentCell()
        miro = str(documentos.GetCellValue(1, "DOCNR"))

    return ResultadoNota(
        sucesso=True, migo=migo, miro=miro,
        mensagem=f"Entrada da NF {criar_referencia(chave_nf)} realizada com sucesso",
    )


def _definir_importadora_ou_pular(sap: SapSession, cte: dict) -> None:
    """Fecha o popup de seleção de fornecedor (wnd[2]) escolhendo a importadora
    configurada para o CT-e, se aparecer; senão só confirma as mensagens."""
    while sap.raw.ActiveWindow.Name == "wnd[2]":
        if sap.raw.ActiveWindow.Text == "Selecionar fornecedor":
            importadora = str(cte.get("importadora") or "")
            tbl = sap.find_name("SAPLMR1MTC_MSEL_VEN", 80)
            achou = False
            for j in range(tbl.RowCount):
                linha = tbl.GetAbsoluteRow(j)
                if str(linha.ElementAt(1).Text) == importadora:
                    linha.Selected = True
                    sap.send_enter()
                    sap.vkey(8)
                    achou = True
                    break
            if not achou:
                sap.send_enter()
        else:
            sap.send_enter()


def lancar_miro_custo(sap: SapSession, cte: dict) -> ResultadoMiroCusto:
    """MIRO do CT-e de custo, referenciando (via 'Mais de uma alocação') todas as
    NFs de mercadoria já lançadas na NP01."""
    filial = cte["filial"]
    prot = cte["cteProt"]["infProt"]
    inf_cte = cte["infCte"]
    ide = inf_cte["ide"]
    vprest = inf_cte["vPrest"]
    calculos = cte["calculos"]
    integracao = cte["integracao"]
    chaves: list[str] = list(inf_cte["chaves"])

    integrado = integracao.get("status") == "CONFIRMADO" or "foram emitidos" in str(
        integracao.get("mensagem") or ""
    )
    if not integrado:
        return ResultadoMiroCusto(sucesso=False, mensagem=str(integracao.get("mensagem") or ""))

    sap.start_transaction("miro")

    if sap.raw.ActiveWindow.Text == "Entrar empresa":
        sap.fill_ctext("BKPF-BUKRS", filial.get("empresa"))
        sap.send_enter()

    sap.vkey(7)
    sap.fill_ctext("BKPF-BUKRS", filial.get("empresa"))
    sap.send_enter()

    sap.fill_ctext("INVFO-BLDAT", sap_date(ide.get("dhEmi")))
    sap.send_enter()

    sap.fill_text("INVFO-XBLNR", criar_referencia(prot["chCTe"], manter_zeros=True))
    sap.send_enter()

    sap.find_id("wnd[0]/usr/cmbRM08M-VORGANG").Key = "3"

    sap.fill_text("INVFO-WRBTR", float(str(vprest["vTPrest"]).replace(".", ",").replace(",", ".")))
    sap.fill_ctext("INVFO-BUPLA", filial.get("localneg"))
    sap.fill_ctext("INVFO-SGTXT", "LANCADO VIA AUTOMACAO RPA")
    sap.set_combo_key("RM08M-REFERENZBELEGTYP", "2")
    sap.click_button("RM08M-XMSEL")

    tbl = sap.find_name("SAPLMR1MTC_MSEL_LIFS", 80)
    for i, chave_nf in enumerate(chaves):
        tbl = sap.find_name("SAPLMR1MTC_MSEL_LIFS", 80)
        tbl.GetAbsoluteRow(i).Item(0).Text = criar_referencia(chave_nf, manter_zeros=True)
        tbl.VerticalScrollbar.Position = i + 1
        _definir_importadora_ou_pular(sap, cte)

    _definir_importadora_ou_pular(sap, cte)
    sap.send_enter()
    _definir_importadora_ou_pular(sap, cte)

    sap.vkey(8)
    sap.send_enter()
    while sap.raw.ActiveWindow.Text == "Informação":
        sap.send_enter()

    tbl = sap.find_name("SAPLMR1MTC_MR1M", 80)
    for i in range(tbl.RowCount):
        try:
            tbl = sap.find_name("SAPLMR1MTC_MR1M", 80)
            if tbl.GetAbsoluteRow(i).Item(0).Text == "":
                break
            tbl.GetAbsoluteRow(i).Item(8).Key = calculos.get("iva_calculado")
            tbl.VerticalScrollbar.Position = i
        except:
            break
    
    sap.send_enter()

    sap.select_tab("HEADER_FI")
    sap.fill_text("INVFO-BEZNK", calculos.get("valor_liquido"))
    sap.fill_ctext("INVFO-J_1BNFTYPE", CATEGORIA_NF_CTE)

    sap.find_name("INVFO-LIFRE", 32).SetFocus()
    sap.vkey(4)
    sap.select_tab("TAB006")
    sap.fill_text("G_SELFLD_TAB-LOW", inf_cte["emit"].get("CNPJ"))
    sap.send_enter()
    sap.send_enter()
    sap.send_enter()
    if sap.raw.ActiveWindow.Name == "wnd[1]":
        sap.send_enter()

    sap.click_button("SELECT_ALL")
    while sap.raw.ActiveWindow.Name == "wnd[1]":
        sap.send_enter()
    sap.send_enter()

    sap.vkey(21)
    status = sap.status_text()
    if status.startswith("Impossível"):
        return ResultadoMiroCusto(sucesso=False, mensagem=status)
    sap.send_enter()

    chave_cte = prot["chCTe"]
    sap.select_tab("TAB8")
    sap.fill_text("J_1BDYDOC-AUTHCOD", prot.get("nProt"))
    sap.fill_ctext("J_1BDYDOC-AUTHDATE", sap_date(prot.get("dhRecbto")))
    sap.fill_ctext("J_1BDYDOC-AUTHTIME", str(prot.get("dhRecbto") or "")[11:19])
    sap.fill_text("J_1BNFE_DOCNUM9_DIVIDED-DOCNUM8", chave_cte[35:43])
    sap.fill_text("J_1BNFE_ACTIVE-CDV", chave_cte[-1])
    sap.fill_ctext("J_1BNFE_DOCNUM9_DIVIDED-TPEMIS", chave_cte[34:35])
    sap.send_enter()

    sap.select_tab("TCTE")
    sap.fill_ctext("J_1BDYDOC-CTE_STRT_LCT", f"{ide.get('UFIni')} {ide.get('cMunIni')}")
    sap.fill_ctext("J_1BDYDOC-CTE_END_LCT", f"{ide.get('UFFim')} {ide.get('cMunFim')}")
    sap.send_enter()

    tbl = sap.find_name("SAPLJ1BB2CTE_TAB_CONTROL", 80)
    for i, chave_nf in enumerate(chaves):
        tbl = sap.find_name("SAPLJ1BB2CTE_TAB_CONTROL", 80)
        linha = tbl.GetAbsoluteRow(i)
        linha.ElementAt(0).Text = chave_nf[0:2]
        linha.ElementAt(1).Text = chave_nf[2:4]
        linha.ElementAt(2).Text = chave_nf[4:6]
        linha.ElementAt(3).Text = chave_nf[6:20]
        linha.ElementAt(4).Text = chave_nf[20:22]
        linha.ElementAt(5).Text = chave_nf[22:25]
        linha.ElementAt(6).Text = chave_nf[25:34]
        linha.ElementAt(7).Text = chave_nf[34:35]
        linha.ElementAt(8).Text = chave_nf[35:43]
        linha.ElementAt(9).Text = chave_nf[-1]
        tbl.VerticalScrollbar.Position = i
    sap.vkey(3)

    saldo = parse_sap_number(sap.get_text("RM08M-DIFFERENZ"))
    if abs(saldo) > TOLERANCIA_SALDO:
        return ResultadoMiroCusto(
            sucesso=False, mensagem=f"Não foi possível lançar a fatura. Saldo de R$ {saldo:.2f}",
        )

    custo_composto = float(calculos.get("valor_liquido") or 0) + saldo
    sap.select_tab("HEADER_FI")
    sap.fill_text("INVFO-BEZNK", custo_composto)
    sap.send_enter()

    sap.vkey(11)  # Salvar
    mensagem = sap.status_text()
    if "criado" in mensagem:
        # "Documento nº 5106412878 foi criado" -> extrai o número entre "nº" e "foi"
        try:
            numero = mensagem.split("nº", 1)[1].split("foi", 1)[0].strip()
        except IndexError:
            numero = ""
        return ResultadoMiroCusto(sucesso=bool(numero), miro=numero, mensagem=mensagem)
    return ResultadoMiroCusto(sucesso=False, mensagem=mensagem)


def buscar_ordens_venda_casada(sap: SapSession, miro: str) -> list[dict]:
    """Reabre a MIRO lançada e lê, item a item, o pedido e a ordem de venda vinculada."""
    sap.start_transaction("miro")
    if sap.raw.ActiveWindow.Text == "Entrar empresa":
        sap.fill_ctext("BKPF-BUKRS", "2000")
        sap.send_enter()

    sap.vkey(34)  # Exibir/alterar documento
    sap.fill_ctext("RBKPV-BELNR", miro)
    sap.fill_ctext("RBKPV-GJAHR", "")
    sap.send_enter()

    resultado: list[dict] = []
    pedido_anterior = ""
    tbl = sap.find_name("SAPLMR1MTC_MR1M", 80)
    for i in range(tbl.RowCount):
        tbl = sap.find_name("SAPLMR1MTC_MR1M", 80)
        tbl.VerticalScrollbar.Position = i
        tbl = sap.find_name("SAPLMR1MTC_MR1M", 80)
        linha = tbl.GetAbsoluteRow(i)

        try:
            pedido = str(linha.ElementAt(5).Text).strip()
        except Exception:  # noqa: BLE001 - fim das linhas válidas da grid
            break

        if not pedido or pedido == pedido_anterior:
            continue
        pedido_anterior = pedido

        ordem = ""
        try:
            linha.ElementAt(5).SetFocus()
            sap.vkey(2)
            sap.select_tab("TABIDT15")
            ordem = sap.get_ctext("COBL-KDAUF").strip()
        except Exception:  # noqa: BLE001
            pass

        item = {"pedido": pedido, "ordem": ordem}
        if not ordem:
            item["mensagem"] = "Carga para estoque"
        resultado.append(item)
        sap.vkey(3)

    return resultado


def fornecer_ordem_venda(sap: SapSession, ordens: list[dict]) -> list[Fornecimento]:
    """Para cada ordem de venda casada com um pedido, executa o fornecimento (VA02)."""
    resultado: list[Fornecimento] = []

    for item in ordens:
        pedido = str(item.get("pedido") or "")
        ordem = str(item.get("ordem") or "")
        mensagem = str(item.get("mensagem") or "")
        remessa = ""

        if mensagem != "Carga para estoque":
            sap.start_transaction("VA02")
            sap.fill_ctext("VBAK-VBELN", ordem)
            sap.send_enter()

            try:
                sap.find_id("wnd[0]/mbar/menu[0]/menu[7]").Select()
                sap.find_id("wnd[0]/tbar[0]/btn[11]").Press()
                mensagem = sap.status_text()
            except Exception as e:  # noqa: BLE001
                mensagem = f"Erro ao fornecer a ordem {ordem}: {e}"

            if "gravado" in mensagem.lower():
                partes = mensagem.split(" ")
                remessa = partes[1] if len(partes) > 1 else ""

        resultado.append(Fornecimento(pedido=pedido, ordem=ordem, mensagem=mensagem, remessa=remessa))

    return resultado
