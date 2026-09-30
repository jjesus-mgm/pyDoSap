"""Conversões entre os formatos da API/Python e os formatos esperados pelo SAP GUI (pt-BR)."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

_RE_DOCUMENTO = re.compile(r"(?<!\d)\d{10}(?!\d)")
_FORMATOS_DATA = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y")


def to_sap(valor: Any) -> str:
    """Texto que o SAP espera num campo (vírgula decimal, sem notação científica)."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "X" if valor else ""
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        if valor.is_integer():
            return str(int(valor))
        return f"{valor:.4f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(valor)


def sap_money(valor: Any) -> str:
    """Valor monetário com 2 casas e vírgula decimal, sem separador de milhar."""
    return f"{float(valor or 0):.2f}".replace(".", ",")


def parse_sap_number(texto: str | None) -> float:
    """'1.234,56-' -> -1234.56 (o SAP coloca o sinal negativo à direita)."""
    s = (texto or "").strip().replace(" ", "")
    if not s:
        return 0.0
    negativo = s.endswith("-") or s.startswith("-")
    s = s.strip("-").replace(".", "").replace(",", ".")
    try:
        numero = float(s)
    except ValueError as e:
        raise ValueError(f"Número SAP inválido: {texto!r}") from e
    return -numero if negativo else numero


def parse_date(valor: Any) -> date:
    """Aceita date/datetime, ISO 8601, dd/mm/aaaa, dd.mm.aaaa e aaaammdd."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    s = str(valor or "").strip()
    if not s:
        raise ValueError("Data vazia")
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for formato in _FORMATOS_DATA:
        try:
            return datetime.strptime(s[:10], formato).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida: {valor!r}")


def sap_date(valor: Any) -> str:
    """Data no formato dd.MM.yyyy. Vazio/None -> ''."""
    if valor is None or str(valor).strip() == "":
        return ""
    return parse_date(valor).strftime("%d.%m.%Y")


def data_br(valor: Any) -> str:
    """Data no formato dd/MM/yyyy (exibição em tela/relatórios). Vazio/None -> ''."""
    if valor is None or str(valor).strip() == "":
        return ""
    try:
        return parse_date(valor).strftime("%d/%m/%Y")
    except ValueError:
        return str(valor)


def moeda_brl(valor: Any) -> str:
    """Valor no formato contábil brasileiro: 'R$ 1.234,56'. Vazio/None -> ''."""
    if valor is None or str(valor).strip() == "":
        return ""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        try:
            numero = float(str(valor).replace(".", "").replace(",", "."))
        except ValueError:
            return str(valor)
    texto = f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def criar_referencia(chave: str, manter_zeros: bool = False) -> str:
    """'numero-série' extraído da chave de acesso (44 dígitos), ex.: '253266-1'.

    Sem manter_zeros, os zeros à esquerda do número e da série são removidos
    (como o CStr(Int(...)) do VBA) — usado como texto de referência (XBLNR/SGTXT).
    Com manter_zeros=True, mantém os 9 dígitos do número da NF (usado para
    preencher campos de tabela do SAP que exigem o tamanho fixo).
    """
    numero = chave[25:34]
    serie = str(int(chave[22:25]))
    if not manter_zeros:
        numero = str(int(numero))
    return f"{numero}-{serie}"


def find_document_number(texto: str | None) -> str:
    """Primeiro número de 10 dígitos da mensagem da barra de status (nº do pedido/documento)."""
    m = _RE_DOCUMENTO.search(texto or "")
    return m.group(0) if m else ""


def extrair_chaves(texto: str | None) -> tuple[list[str], list[str]]:
    """Separa chaves de acesso coladas pelo usuário (espaço, vírgula, ';' ou quebra de linha).

    Retorna (válidas sem duplicatas, ignoradas). Só letras e números são aceitos: a API monta
    a consulta SQL com esses valores, então aspas e outros símbolos nunca devem chegar até lá.
    """
    validas: list[str] = []
    ignoradas: list[str] = []
    vistas: set[str] = set()
    for token in re.split(r"[\s,;]+", texto or ""):
        if not token:
            continue
        if not re.fullmatch(r"[A-Za-z0-9]+", token):
            ignoradas.append(token)
        elif token not in vistas:
            vistas.add(token)
            validas.append(token)
    return validas, ignoradas


def converter_como_original(texto: str, original):
    """Converte o texto editado (ex.: numa célula de tabela) de volta ao tipo do
    valor original, para que o dado enviado adiante (ex.: parâmetro do BigQuery)
    bata com o tipo esperado."""
    texto = texto.strip()
    if isinstance(original, bool):
        return texto.lower() in ("sim", "true", "1", "x", "verdadeiro")
    if isinstance(original, int):
        try:
            return int(texto)
        except ValueError:
            return texto
    if isinstance(original, float):
        try:
            return float(texto.replace(",", "."))
        except ValueError:
            return texto
    return texto
