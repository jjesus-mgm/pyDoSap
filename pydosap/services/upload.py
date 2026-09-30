"""Envio de XMLs de CT-e para o TMS via API (porte do CTE_UPLOAD.bas / EnviarXMLsUmPorUm)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from ..api_client import ApiClient


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


def enviar_xmls(
    api: ApiClient,
    arquivos: Sequence[Path],
    *,
    on_result: Callable[[int, int, ResultadoUpload], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[ResultadoUpload]:
    """Envia um arquivo por vez (o processamento no TMS é síncrono e demorado)."""
    resultados: list[ResultadoUpload] = []
    for n, caminho in enumerate(arquivos, start=1):
        if should_stop and should_stop():
            break
        try:
            resposta = api.upload_xml(caminho.name, caminho.read_bytes())
            res = ResultadoUpload(caminho.name, True, resposta.strip())
        except Exception as e:  # noqa: BLE001
            res = ResultadoUpload(caminho.name, False, str(e))
        resultados.append(res)
        if on_result:
            on_result(n, len(arquivos), res)
    return resultados
