"""Envio de XMLs de CT-e para o TMS via API (porte do CTE_UPLOAD.bas / EnviarXMLsUmPorUm).

O upload é síncrono e de um arquivo por vez: o retorno já diz se o Lincros integrou o documento.
Com `forcar_integracao` o CT-e também é gravado direto na base de lançamento (ctes_api), o que
permite lançar CT-es com mais de 90 dias, que a listagem do Lincros não traz.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from ..api_client import ApiClient

STATUS_FORCADA_OK = ("INTEGRADO", "JA_INTEGRADO")


@dataclass(slots=True)
class ResultadoUpload:
    arquivo: str
    ok: bool
    resposta: str


def listar_xmls(pasta: str | Path) -> list[Path]:
    return sorted(
        (p for p in Path(pasta).iterdir() if p.is_file() and p.suffix.lower() == ".xml"),
        key=lambda p: p.name.lower(),
    )


def interpretar_upload(texto: str) -> tuple[bool, str]:
    """Lê a resposta do /cte/upload. Integrado = o Lincros devolveu o oid do documento; um
    'CONFIRMADO' só com protocolo significa que o documento não chegou a ser criado."""
    try:
        dados = json.loads(texto)
        lincros = dados.get("resposta_lincros") or {}
    except (ValueError, AttributeError):
        return True, texto.strip()  # formato desconhecido: mantém o comportamento anterior
    oid, protocolo, status = lincros.get("oidCte"), lincros.get("protocolo"), lincros.get("status")
    if oid:
        return True, f"Integrado no Lincros (oid {oid}, protocolo {protocolo})."
    return False, (
        f"Lincros respondeu {status or 'sem status'} (protocolo {protocolo}), mas não retornou o oid: "
        "o CT-e NÃO foi integrado."
    )


def _situacao_lancamento(d: dict) -> str:
    if not d.get("naView"):
        return d.get("observacao") or "CT-e fora da view de lançamento."
    if d.get("lancado"):
        return f"já lançado (MIRO {d.get('miro')})"
    if d.get("lancar"):
        return f"PARA LANCAR — centro {d.get('centro')}, {d.get('tipo')}/{d.get('categoria')}"
    return f"BLOQUEADO — {d.get('observacao')}"


def interpretar_integracao(d: dict) -> tuple[bool, str]:
    """Lê a resposta do /cte/forcar-integracao."""
    status = str(d.get("status") or "")
    if status == "INTEGRADO":
        return True, f"Integrado (oid {d.get('oidDocumento')}). No pyDoSap: {_situacao_lancamento(d)}"
    if status == "JA_INTEGRADO":
        return True, f"Já estava integrado (oid {d.get('oidDocumento')}). No pyDoSap: {_situacao_lancamento(d)}"
    return False, f"{status or 'ERRO'}: {d.get('detalhes') or d}"


def enviar_xmls(
    api: ApiClient,
    arquivos: Sequence[Path],
    *,
    forcar_integracao: bool = False,
    on_result: Callable[[int, int, ResultadoUpload], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[ResultadoUpload]:
    """Envia um arquivo por vez (o processamento no TMS é síncrono e demorado)."""
    resultados: list[ResultadoUpload] = []
    for n, caminho in enumerate(arquivos, start=1):
        if should_stop and should_stop():
            break
        try:
            xml = caminho.read_bytes()
            if forcar_integracao:
                ok, texto = interpretar_integracao(api.forcar_integracao(caminho.name, xml))
            else:
                ok, texto = interpretar_upload(api.upload_xml(caminho.name, xml))
            res = ResultadoUpload(caminho.name, ok, texto)
        except Exception as e:  # noqa: BLE001
            res = ResultadoUpload(caminho.name, False, str(e))
        resultados.append(res)
        if on_result:
            on_result(n, len(arquivos), res)
    return resultados
