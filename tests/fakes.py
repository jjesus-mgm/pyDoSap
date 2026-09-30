"""SAP e API falsos para testar os fluxos sem SAP GUI nem rede."""
from __future__ import annotations

import copy


class FakeTable:
    def __init__(self, linhas):
        self.linhas = linhas

    @property
    def row_count(self):
        return len(self.linhas)

    def get(self, r, c):
        return self.linhas[r][c]

    def set(self, r, c, v):
        self.linhas[r][c] = v


class FakeSap:
    """Registra as chamadas e devolve mensagens de status conforme regras simples."""

    def __init__(self, *, ao_teclar=None, textos=None):
        self.chamadas: list[tuple] = []
        self.status = ("", "")
        self.ao_teclar = ao_teclar or {}          # {tecla: (tipo, texto)}
        self.textos = {k: list(v) for k, v in (textos or {}).items()}
        self.tabelas: dict[str, FakeTable] = {}
        self.campos: dict[str, object] = {}
        self.recuperou = 0

    def _reg(self, nome, *args):
        self.chamadas.append((nome, *args))

    # navegação
    def start_transaction(self, c): self._reg("tx", c)
    def end_transaction(self): self._reg("end_tx")
    def send_enter(self): self._reg("enter")
    def vkey(self, k):
        self._reg("vkey", k)
        if k in self.ao_teclar:
            self.status = self.ao_teclar[k]
    def select_tab(self, n): self._reg("tab", n)
    def click_button(self, n): self._reg("click", n)
    # campos
    def fill_text(self, n, v): self.campos[n] = v; self._reg("text", n, v)
    def fill_ctext(self, n, v): self.campos[n] = v; self._reg("ctext", n, v)
    def set_combo_key(self, n, v): self._reg("combo", n, v)
    def set_checkbox(self, n, v): self._reg("check", n, v)
    def get_text(self, n):
        fila = self.textos.get(n, [])
        return fila.pop(0) if len(fila) > 1 else (fila[0] if fila else "")
    def get_ctext(self, n): return str(self.campos.get(n, ""))
    def table(self, nome):
        return self.tabelas.setdefault(
            nome, FakeTable([["FM", "", "X"] + [""] * 13, [""] * 16])
        )
    def label_text(self, i): raise RuntimeError("sem label")
    # status / janela
    def status_text(self): return self.status[1]
    def status_type(self): return self.status[0]
    def active_window_name(self): return "wnd[0]"
    def active_window_type(self): return "GuiMainWindow"
    def active_window_text(self): return ""
    def user(self): return "SAPUSER"
    def mandante(self): return "100"
    def recuperar(self): self.recuperou += 1

    def transacoes(self):
        return [c[1] for c in self.chamadas if c[0] == "tx"]


CFG = {
    "categoria": "FRETE",
    "tipoPedido": "ZFRE", "orgCompras": "1000", "grpCompradores": "100", "funcaoParceiro": "FM",
    "catContabil": "K", "material": "MAT1", "qtdPedido": 1, "multPedido": 10000,
    "materialPedagio": "PED1", "qtdPedidoPedagio": 1, "ivaPedagio": "I0", "catMiro": "Z1",
}

CTE = {
    "numero": 123, "serie": 1, "referencia": "000000123-1", "empresa": "1000", "centro": "2005",
    "centroCusto": "CC1", "localNegocios": "2005", "oid": "abc", "chave": "35" + "1" * 42,
    "dataEmissao": "2026-09-01T10:00:00", "dataSefaz": "2026-09-01", "horaSefaz": "10:05:00",
    "numeroProtocolo": "1234567890", "verificador": "7", "aleatorio": "12345678", "tpEmis": "1",
    "valorDocumento": 1500.5, "munIni": "3550308", "munFim": "3304557", "possuiPedagio": False,
    "possuiPendencia": False, "mensagemIntegracao": None,
    "calculos": {
        "ivaCalc": "IB", "valorPedido": 12345678, "condicaoPagamento": "CTE1", "diasVencimento": 35,
        "textoPedido": "FRETES - 05/10/2026", "considerarPedagio": False, "valorPedidoPedagio": 0,
    },
}


def novo_cte(**extra):
    d = copy.deepcopy(CTE)
    d.update(extra)
    return d


class FakeApi:
    def __init__(self, cte=None, configs=None, falha_cte=None):
        self.cte = cte if cte is not None else novo_cte()
        self.configs = configs if configs is not None else [copy.deepcopy(CFG)]
        self.falha_cte = falha_cte
        self.logs: list[dict] = []
        self.buscados: list[str] = []

    def buscar_configuracoes(self, tabela=None): return self.configs

    def buscar_cte_para_lancamento(self, oid):
        self.buscados.append(oid)
        if self.falha_cte and oid in self.falha_cte:
            raise RuntimeError(self.falha_cte[oid])
        return copy.deepcopy(self.cte)

    def inserir_log(self, log): self.logs.append(log)
