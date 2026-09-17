# -*- coding: utf-8 -*-
"""Utilitários Telegram compartilhados entre os agentes (mesmo padrão do
RV FiscalCheck Pro, agents/telegram_utils.py — reaproveita o mesmo bot)."""
import json, os, urllib.request, urllib.parse

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")


def _cfg() -> dict:
    # GitHub Actions: lê de variáveis de ambiente
    if os.environ.get("TELEGRAM_TOKEN"):
        return {
            "telegram_token":   os.environ["TELEGRAM_TOKEN"],
            "telegram_chat_id": int(os.environ["TELEGRAM_CHAT_ID"]),
        }
    # Local: lê do config.json
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def enviar(mensagem: str, parse_mode: str = "HTML") -> bool:
    cfg = _cfg()
    token = cfg["telegram_token"]
    chat_id = cfg["telegram_chat_id"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    dados = json.dumps({
        "chat_id": chat_id,
        "text": mensagem,
        "parse_mode": parse_mode,
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=dados,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"  [Telegram] Erro ao enviar: {e}")
        return False
