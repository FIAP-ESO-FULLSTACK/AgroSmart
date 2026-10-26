"""Configuração: lê credenciais do .env e define constantes do monitor."""
import os
from dotenv import load_dotenv

load_dotenv()

EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")

# Destinatário dos ALERTAS (R2 infestação / R3 plano de controle), ex.: o
# e-mail do agrônomo responsável. O remetente do lote sempre recebe a resposta
# na conversa; os alertas são ADICIONALMENTE comunicados a este endereço.
EMAIL_ALERTAS = os.environ.get("EMAIL_ALERTAS", "")

ASSUNTO_FILTRO = "Frutas para analise"
INTERVALO_POLLING = 30  # segundos entre cada checagem da caixa de entrada
ARQUIVO_CHECKPOINT = "processados.txt"
ARQUIVO_HISTORICO = "historico.jsonl"

# Parâmetros das regras de decisão
CONFIANCA_MINIMA = 0.60   # predição abaixo disso é descartada (foto ilegível)
LIMIAR_INFESTACAO = 0.30  # fração de fotos doentes que caracteriza infestação
LOTES_RECORRENCIA = 3     # mesma doença em N lotes seguidos → plano de controle
