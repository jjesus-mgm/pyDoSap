"""Definições de colunas do CT-e de despesa (frete), compartilhadas pelo modelo da
tabela (ui/cte_model.py) e pela exportação para Excel (services/exportacao.py).

Sem dependência de Qt: fica testável e reutilizável nos dois lugares.
"""
from __future__ import annotations

from typing import Iterable

COL_LANCAR = "lancar"
COL_LANCADO = "lancado"
COL_PEDIDO = "pedido"
COL_RESPOSTA = "resposta"

LINKS = {"z_dacte": "DACTE", "z_xml": "XML"}

ROTULOS = {
    COL_LANCAR: "Lançar", COL_LANCADO: "Lançado", COL_PEDIDO: "Pedido", COL_RESPOSTA: "Resposta",
    "codFornecedor": "Cód. fornecedor", "categoria": "Categoria", "centro": "Centro",
    "regiao": "Região", "chave": "Chave", "dataEmissao": "Emissão", "observacao": "Observação",
    "oidDocumento": "OID", "z_dacte": "DACTE", "z_xml": "XML",
    "numero": "Nº CT-e", "serie": "Série", "valor": "Valor", "miro": "MIRO",
    "nomeTransportadora": "Transportadora",
}

# Larguras de coluna (px) para os campos conhecidos do CT-e de despesa. O que não
# está aqui fica de fora e usa o ajuste automático (resizeColumnsToContents).
MUITO_PEQUENO, PEQUENO, PEQUENO_MEDIO, MEDIO, GRANDE = 48, 76, 108, 170, 340
LARGURAS = {
    COL_LANCADO: MUITO_PEQUENO,
    COL_LANCAR: MUITO_PEQUENO,
    "regiao": PEQUENO_MEDIO,
    "centro": PEQUENO,
    "dataEmissao": PEQUENO,
    "numero": PEQUENO,
    "serie": MUITO_PEQUENO,
    "valor": PEQUENO,
    "observacao": MEDIO,
    "z_dacte": PEQUENO,
    "z_xml": PEQUENO,
    COL_PEDIDO: PEQUENO,
    COL_RESPOSTA: GRANDE,
    "categoria": PEQUENO_MEDIO,
    "chave": MEDIO,
    "codFornecedor": PEQUENO_MEDIO,
    "miro": PEQUENO,
    "nomeTransportadora": MEDIO,
}

# Colunas alinhadas à esquerda (texto livre/longo); as demais ficam centralizadas,
# exceto números sem entrada aqui, que o modelo já alinha à direita.
ALINHAMENTO_ESQUERDA = {"observacao", COL_RESPOSTA, "nomeTransportadora"}

# Formatações especiais de valor (na tela e na exportação para Excel).
COLUNAS_DATA = {"dataEmissao"}
COLUNAS_MOEDA = {"valor"}

# Ordem de exibição para os campos conhecidos; o restante (não citado) entra
# depois, na ordem em que aparece na resposta da API.
ORDEM = [
    COL_LANCADO, COL_LANCAR, "regiao", "centro", "dataEmissao",
    "numero", "serie", "valor", "observacao",
    "z_dacte", "z_xml", COL_PEDIDO, COL_RESPOSTA, "categoria",
    "chave", "codFornecedor", "miro", "nomeTransportadora",
]


def ordenar_colunas(chaves_presentes: Iterable[str]) -> list[str]:
    """Aplica a ORDEM às colunas realmente presentes; o resto entra depois, na
    ordem em que já estava (ordem de inserção do iterável de entrada)."""
    presentes = list(dict.fromkeys(chaves_presentes))  # remove duplicatas, preserva ordem
    vistas = set(presentes)
    conhecidas = [c for c in ORDEM if c in vistas]
    resto = [c for c in presentes if c not in ORDEM]
    return conhecidas + resto


def rotulo(coluna: str) -> str:
    return ROTULOS.get(coluna, coluna)
