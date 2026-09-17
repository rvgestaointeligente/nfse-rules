# -*- coding: utf-8 -*-
"""
Vigia LC116/NBS/cClassTrib — Sistema Nacional NFS-e (gov.br/nfse)
Roda diariamente via GitHub Actions.

REGRA DE OURO (mesma do vigia_confaz.py do RV FiscalCheck Pro): este agente
SÓ ALERTA. NUNCA baixa/aplica a tabela nova sozinho — atualizar
tabela-lc116-nbs.json neste repo exige revisão humana (conferir o que
mudou no anexo antes de publicar, já que os clientes do RV Emissor NFS-e
recebem essa tabela automaticamente assim que ela muda aqui, ver
backend/src/services/atualizadorTabela.js do produto).

O que faz:
  1. Baixa as 2 páginas de listagem do gov.br/nfse onde os arquivos vivem
     ("Produção Restrita" pro ANEXO_B, "RTC" pro pacote XSD) — são páginas
     HTML normais, sem bloqueio de WAF (confirmado: o bloqueio que a gente
     tomou antes era só pra download direto de binário .zip/.xlsx, não pra
     essas páginas de listagem).
  2. Extrai do HTML o NOME do arquivo do ANEXO_B (lista de serviço nacional
     NBS/LC116) e do pacote de esquemas XSD — o nome já contém a data de
     versão (ex: "...-v1-01-20260122.xlsx"), sinal mais preciso que hash da
     página inteira (evita falso positivo por banner/menu mudando).
  3. Compara com o nome salvo da rodada anterior. Mudou → alerta Telegram
     com o link direto e o lembrete do passo manual. Não mudou → heartbeat
     diário (prova que o vigia está rodando de verdade).
  4. NÃO baixa nem aplica nada sozinho — é aviso pra revisão humana.

Urgência (contexto pro alerta): a partir de janeiro/2027 esses dados passam
a ser obrigatórios nas notas — tabela desatualizada pode virar multa pro
cliente do RV Emissor NFS-e.
"""
import json, os, re, sys, urllib.request
from datetime import datetime

# ─── Caminhos ──────────────────────────────────────────────────────────────────
_AGENTS = os.path.dirname(os.path.abspath(__file__))
_ESTADO = os.path.join(_AGENTS, "ultimo_anexo_b.json")

sys.path.insert(0, _AGENTS)
import telegram_utils as tg

# ANEXO_B (tabela LC116/NBS) fica na página "Produção Restrita"; o pacote de
# esquemas XSD fica um nível acima, na página "RTC" — confirmado ao vivo em
# 17/09/2026 que são páginas diferentes (o ANEXO_B não aparece em /rtc, o
# XSD não aparece em /producao-restrita).
_URL_ANEXO_B = "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita"
_URL_XSD = "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc"

_PADRAO_ANEXO_B = re.compile(r'href="[^"]*/(anexo_b-nbs2-lista_servico_nacional[^"]*\.xlsx)"', re.IGNORECASE)
_PADRAO_XSD = re.compile(r'href="[^"]*/(nfse-esquemas_xsd[^"]*\.zip)"', re.IGNORECASE)


def _baixar(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 RVEmissorNfseMonitor/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  [ERRO download] {url}: {e}")
        return None


def _carregar_estado() -> dict:
    if os.path.exists(_ESTADO):
        with open(_ESTADO, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _salvar_estado(estado: dict):
    with open(_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)


def verificar():
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"\n{'='*60}")
    print(f"  Vigia LC116/NBS (gov.br/nfse) — {agora}")
    print(f"{'='*60}\n")

    html_anexo_b = _baixar(_URL_ANEXO_B)
    html_xsd = _baixar(_URL_XSD)

    if html_anexo_b is None and html_xsd is None:
        tg.enviar(
            f"⚠️ <b>Vigia LC116/NBS — não consegui acessar o gov.br/nfse</b>\n<i>{agora}</i>\n\n"
            f"Falha ao baixar as duas páginas monitoradas. Pode ser instabilidade "
            f"temporária — não é necessariamente uma mudança na tabela. Vou tentar "
            f"de novo amanhã."
        )
        print("  [Telegram] Aviso de falha de acesso enviado.")
        return

    m_anexo_b = _PADRAO_ANEXO_B.search(html_anexo_b) if html_anexo_b else None
    m_xsd = _PADRAO_XSD.search(html_xsd) if html_xsd else None

    if not m_anexo_b:
        tg.enviar(
            f"⚠️ <b>Vigia LC116/NBS — não encontrei o ANEXO_B na página</b>\n<i>{agora}</i>\n\n"
            f"A página {_URL_ANEXO_B} respondeu, mas o padrão esperado do nome do "
            f"arquivo não bateu — pode ser que o gov.br tenha reorganizado a "
            f"página. Precisa checar manualmente."
        )
        print("  [Telegram] Aviso de padrão não encontrado enviado.")
        return

    anexo_b_atual = m_anexo_b.group(1)
    xsd_atual = m_xsd.group(1) if m_xsd else None

    estado_ant = _carregar_estado()
    anexo_b_ant = estado_ant.get("anexo_b")
    xsd_ant = estado_ant.get("xsd")

    mudancas = []
    if anexo_b_ant is not None and anexo_b_ant != anexo_b_atual:
        mudancas.append(("Tabela LC116/NBS (ANEXO_B)", anexo_b_ant, anexo_b_atual))
    if xsd_atual and xsd_ant is not None and xsd_ant != xsd_atual:
        mudancas.append(("Esquemas XSD (estrutura do XML)", xsd_ant, xsd_atual))

    _salvar_estado({"anexo_b": anexo_b_atual, "xsd": xsd_atual, "verificado_em": agora})

    if mudancas:
        linhas = []
        for nome, antigo, novo in mudancas:
            linhas.append(f"  • <b>{nome}</b>\n    Era: {antigo}\n    Agora: {novo}")
        corpo = "\n".join(linhas)
        msg = (
            f"🚨 <b>Vigia LC116/NBS — MUDANÇA DETECTADA no gov.br/nfse</b>\n"
            f"<i>{agora}</i>\n\n{corpo}\n\n"
            f"⚠️ <b>Nada foi alterado automaticamente.</b> Os clientes do RV Emissor "
            f"NFS-e recebem a tabela publicada aqui automaticamente assim que ela "
            f"mudar no repo — a partir de jan/2027 esses dados são obrigatórios nas "
            f"notas.\n\n"
            f"<b>Próximos passos:</b>\n"
            f"  1. Baixar o arquivo novo em {_URL_ANEXO_B} (ou {_URL_XSD} se foi o XSD)\n"
            f"  2. Conferir o que mudou e regenerar tabela-lc116-nbs.json (bump de versão)\n"
            f"  3. Subir pro repo nfse-rules — a distribuição pros clientes já é automática"
        )
        tg.enviar(msg)
        print("\n  [Telegram] ALERTA de mudança enviado.")
    else:
        msg = (
            f"✅ <b>Vigia LC116/NBS — sem mudanças</b>\n<i>{agora}</i>\n\n"
            f"ANEXO_B (tabela LC116/NBS) e esquemas XSD verificados no gov.br/nfse — "
            f"nenhuma alteração hoje.\n"
            f"ANEXO_B atual: {anexo_b_atual}\n"
            f"XSD atual: {xsd_atual or '(não encontrado nesta rodada)'}"
        )
        tg.enviar(msg)
        print("\n  [Telegram] Heartbeat diário enviado.")

    print()


if __name__ == "__main__":
    verificar()
