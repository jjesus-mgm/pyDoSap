"""Configuração da aplicação (variáveis de ambiente / arquivo .env).

Segredos (token da API) NUNCA ficam no código: use o .env.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

APP_NAME = "pyDoSap"
APP_VERSION = "0.3.0"

if getattr(sys, "frozen", False):  # Executável gerado pelo PyInstaller
    BASE_DIR = Path(sys.executable).resolve().parent
    # Diretório temporário interno onde o PyInstaller extrai os arquivos empacotados
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = BASE_DIR

ASSETS_DIR = Path(__file__).resolve().parent / "ui" / "assets"
USER_DIR = Path(os.getenv("APPDATA") or Path.home()) / APP_NAME

# Ordem de prioridade do .env:
# 1. .env interno embutido no executável (sys._MEIPASS)
# 2. .env ao lado do executável/projeto (BASE_DIR)
# 3. .env na pasta do usuário (USER_DIR / APPDATA)
load_dotenv(BUNDLE_DIR / ".env")
load_dotenv(BASE_DIR / ".env")
load_dotenv(USER_DIR / ".env")

# --------------------------------------------------------------- API REST
API_BASE_URL = os.getenv(
    "PYDOSAP_API_URL",
    "https://escrituracao-ctes-916208936979.southamerica-east1.run.app",
).rstrip("/")
API_TOKEN = os.getenv("PYDOSAP_API_TOKEN", "")

# (conexão, leitura) em segundos
API_TIMEOUT = (10, 120)
UPLOAD_TIMEOUT = (30, 900)

# As configurações de lançamento (config_lancamento, config_cte_custo,
# config_filiais, regioes_csc) são lidas e gravadas via API — GET/POST
# /cte/config/<ação>/<tabela> — que grava no BigQuery do lado do servidor.
# O cliente não precisa mais de credenciais do Google Cloud.