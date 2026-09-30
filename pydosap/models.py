"""Estruturas de dados compartilhadas."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class Resp:
    """Resultado padrão de uma operação no SAP (equivalente ao tResp do VBA)."""

    sucesso: bool = False
    mensagem: str = ""
    valor: str = ""


@dataclass(slots=True)
class FiltroCTE:
    """Filtros da busca de CT-es (payload de POST /cte/bot/buscar)."""

    regiao: str = ""
    centro: str = ""
    data_inicio: date | None = None
    data_fim: date | None = None
    somente_nao_lancados: bool = False
    somente_validados: bool = False
    chaves: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        filtros: dict = {}
        if self.regiao.strip():
            filtros["regiao"] = self.regiao.strip()
        if self.centro.strip():
            filtros["centro"] = self.centro.strip()
        if self.data_inicio:
            filtros["dataInicio"] = self.data_inicio.strftime("%Y-%m-%d")
        if self.data_fim:
            filtros["dataFim"] = self.data_fim.strftime("%Y-%m-%d")
        if self.somente_nao_lancados:
            filtros["somenteNaoLancados"] = True
        if self.somente_validados:
            filtros["somenteValidados"] = True
        if self.chaves:
            filtros["chaves"] = list(self.chaves)
        return {"filtros": filtros}


@dataclass(slots=True)
class ControleLancamento:
    """Dados informados pelo usuário para o lote (chamado, data, validação)."""

    chamado: str = ""
    data_lancamento: date | None = None
    ignorar_validacao: bool = False

    @property
    def data_lancamento_iso(self) -> str:
        return self.data_lancamento.strftime("%Y-%m-%d") if self.data_lancamento else ""


@dataclass(slots=True)
class ResumoLancamento:
    total: int = 0
    sucesso: int = 0
    falha: int = 0
    interrompido: bool = False


# ------------------------------------------------------- CT-e de custo
@dataclass(slots=True)
class SimulacaoFatura:
    """Diferença entre o valor da NF e o valor simulado da fatura (transação /FHEFI/NP01)."""

    sucesso: bool = False
    saldo: float = 0.0
    mensagem: str = ""


@dataclass(slots=True)
class ResultadoNota:
    """Entrada de mercadoria (MIGO) + fatura (MIRO) de uma NF vinculada ao CT-e de custo."""

    sucesso: bool = False
    migo: str = ""
    miro: str = ""
    mensagem: str = ""


@dataclass(slots=True)
class ResultadoMiroCusto:
    """MIRO do próprio CT-e de custo (transação MIRO, várias NFs de referência)."""

    sucesso: bool = False
    miro: str = ""
    mensagem: str = ""


@dataclass(slots=True)
class Fornecimento:
    """Uma linha do fornecimento de ordem de venda casada (pedido -> ordem -> remessa)."""

    pedido: str = ""
    ordem: str = ""
    mensagem: str = ""
    remessa: str = ""


@dataclass(slots=True)
class ResultadoCteCusto:
    sucesso: bool = False
    mensagem: str = ""
    notas: list[ResultadoNota] = field(default_factory=list)
    fornecimentos: list[Fornecimento] = field(default_factory=list)
