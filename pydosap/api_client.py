"""Cliente HTTP da API escrituracao-ctes (equivalente ao cRequests.cls do projeto VBA)."""
from __future__ import annotations

import json
from typing import Any

import requests

from .config import API_BASE_URL, API_TIMEOUT, API_TOKEN, UPLOAD_TIMEOUT
from .models import FiltroCTE


class ApiError(Exception):
    def __init__(self, mensagem: str, status: int | None = None):
        super().__init__(mensagem)
        self.status = status


def _erro_da_resposta(r: requests.Response) -> str:
    try:
        corpo = r.json()
        if isinstance(corpo, dict):
            return str(corpo.get("erro") or corpo.get("detalhes") or corpo)
    except ValueError:
        pass
    return (r.text or r.reason or f"HTTP {r.status_code}")[:500]


class ApiClient:
    def __init__(self, base_url: str = API_BASE_URL, token: str = API_TOKEN):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    # ------------------------------------------------------------------ infra
    def _request(self, metodo: str, caminho: str, *, timeout=API_TIMEOUT, **kw) -> requests.Response:
        url = f"{self.base_url}{caminho}"
        try:
            r = self._session.request(metodo, url, timeout=timeout, **kw)
        except requests.RequestException as e:
            raise ApiError(f"Falha de comunicação com a API: {e}") from e
        if r.status_code >= 400:
            raise ApiError(_erro_da_resposta(r), r.status_code)
        return r

    @staticmethod
    def _json(r: requests.Response) -> Any:
        try:
            return r.json()
        except ValueError as e:
            raise ApiError("Resposta inválida da API (não é JSON).") from e

    @staticmethod
    def _lista(dados: Any) -> list[dict]:
        if isinstance(dados, dict) and "erro" in dados:
            raise ApiError(str(dados["erro"]))
        if not isinstance(dados, list):
            raise ApiError("Formato inesperado na resposta da API (esperada uma lista).")
        return dados

    # -------------------------------------------------------------- endpoints
    def status(self) -> str:
        return self._request("GET", "/status", timeout=(5, 15)).text

    def buscar_ctes(self, filtro: FiltroCTE) -> list[dict]:
        """POST /cte/bot/buscar"""
        r = self._request("POST", "/cte/bot/buscar", json=filtro.to_payload())
        return self._lista(self._json(r))

    def buscar_configuracoes(self, tabela: str) -> list[dict]:
        """GET /cte/config/buscar/<tabela> — ex.: 'config_lancamento', 'config_filiais',
        'config_cte_custo', 'regioes_csc'."""
        return self._lista(self._json(self._request("GET", f"/cte/config/buscar/{tabela}")))

    def atualizar_configuracoes(self, tabela: str, linhas: list[dict]) -> str:
        """POST /cte/config/atualizar/<tabela> — substitui a tabela inteira pelo array
        enviado (não é um update por linha: envie sempre o conteúdo completo da tabela)."""
        corpo = json.dumps(linhas, ensure_ascii=False, default=str).encode("utf-8")
        r = self._request(
            "POST", f"/cte/config/atualizar/{tabela}", data=corpo, timeout=UPLOAD_TIMEOUT,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        dados = self._json(r)
        if isinstance(dados, dict):
            return str(dados.get("detalhes") or dados.get("status") or "Configurações atualizadas.")
        return "Configurações atualizadas."

    def reverter_configuracao(self, tabela: str) -> str:
        """GET /cte/config/reverter/<tabela> — restaura o backup da última atualização."""
        r = self._request("GET", f"/cte/config/reverter/{tabela}")
        try:
            dados = r.json()
        except ValueError:
            return "Configuração revertida."
        if isinstance(dados, dict):
            return str(dados.get("detalhes") or dados.get("status") or "Configuração revertida.")
        return "Configuração revertida."

    def buscar_cte_custo(self, chave: str) -> dict:
        """GET /cte/custo/buscarCteJson/<chave> - CT-e de custo completo, com as NFs vinculadas."""
        dados = self._json(self._request("GET", f"/cte/custo/buscarCteJson/{chave}"))
        if not isinstance(dados, dict):
            raise ApiError("Formato inesperado ao buscar o CT-e de custo.")
        erro = str(dados.get("erro") or "").strip()
        if erro:
            raise ApiError(erro)
        return dados

    def buscar_cte_para_lancamento(self, oid: str) -> dict:
        """GET /cte/buscarParaLancamento/<oid> - CT-e completo + cálculos + validação."""
        dados = self._json(self._request("GET", f"/cte/buscarParaLancamento/{oid}"))
        if not isinstance(dados, dict):
            raise ApiError("Formato inesperado ao buscar o CT-e para lançamento.")
        if "erro" in dados:  # a API devolve HTTP 200 com {"erro", "detalhe"}
            detalhe = f" {dados['detalhe']}" if dados.get("detalhe") else ""
            raise ApiError(f"{dados['erro']}{detalhe}")
        return dados

    def inserir_log(self, log: dict) -> None:
        """POST /log/inserir (tabela sapguibot_ctes.log)."""
        corpo = json.dumps(log, ensure_ascii=False, default=str).encode("utf-8")
        self._request(
            "POST", "/log/inserir", data=corpo,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    def upload_xml(self, nome_arquivo: str, xml: bytes) -> str:
        """POST /cte/upload - XML puro no corpo, nome do arquivo no header X-File-Name."""
        nome = nome_arquivo.encode("latin-1", "replace").decode("latin-1")
        r = self._request(
            "POST", "/cte/upload", data=xml, timeout=UPLOAD_TIMEOUT,
            headers={"Content-Type": "application/xml; charset=utf-8", "X-File-Name": nome},
        )
        return r.text
