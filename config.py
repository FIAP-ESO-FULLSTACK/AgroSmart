"""Configurações do AgroSmart — ingestão de fotos por e-mail."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Credenciais (definir no .env)
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
EMAIL_ALERTA_DESTINO = os.getenv("EMAIL_ALERTA_DESTINO", EMAIL_USER)

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

# Assunto que identifica e-mails de ingestão (filtra o resto da caixa).
# ATENÇÃO: a busca IMAP é "contém" e ignora maiúsculas/minúsculas, então
# nenhum e-mail automático enviado pelo sistema pode ter esta palavra no assunto.
ASSUNTO_INGESTAO = "FRUTAS"

# Intervalo de polling do monitor (segundos)
INTERVALO_POLLING = 30

# Validações de entrada
MIN_FOTOS = 3                  # V2: menos que isso = amostra insuficiente

# Regras de decisão
LIMIAR_PCT_DOENTES = 0.30      # R1/R3: > 30% de frutas doentes no lote
LIMIAR_CONFIANCA = 0.70        # R1: confiança média mínima do modelo
LIMIAR_CONFIANCA_ALTA = 0.90   # R3: confiança considerada muito alta
LIMIAR_PODRES_CRITICO = 0.50   # R3: > 50% podres = descarte
LOTES_SEGUIDOS_PRAGA = 3       # R2: mesma praga em N lotes seguidos
DIAS_SEM_LOTE = 3              # R4: dias sem lote de um remetente

# Caminhos
BASE = Path(__file__).parent
DIR_BANCO = BASE / "banco_simulado"           # simula o banco de dados
DIR_RELATORIOS = BASE / "relatorios"          # planos de controle e descartes
ARQ_INDICE = DIR_BANCO / "indice_lotes.json"  # metadados dos lotes salvos
ARQ_ESTADO_INATIVIDADE = DIR_BANCO / "estado_inatividade.json"
ARQ_CHECKPOINT = BASE / "processed_uids.json"

for d in (DIR_BANCO, DIR_RELATORIOS):
    d.mkdir(exist_ok=True)
