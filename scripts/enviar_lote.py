"""Gerador de dados do AgroSmart: simula um produtor enviando um lote de fotos.

Monta um e-mail com o assunto que o monitor escuta ("Frutas para analise"),
anexa fotos de uma subpasta de amostras/ e envia via SMTP para a própria
caixa monitorada — simulando a chegada de dados novos no fluxo.

Uso:
    uv run python scripts/enviar_lote.py <subpasta> [quantidade]

Exemplos:
    uv run python scripts/enviar_lote.py sarna_da_maca        # todas as fotos
    uv run python scripts/enviar_lote.py saudaveis 3          # 3 fotos
    uv run python scripts/enviar_lote.py --listar             # mostra as opções
    uv run python scripts/enviar_lote.py sem_anexo            # lote sem fotos
"""
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from agrosmart.config import ASSUNTO_FILTRO, EMAIL_APP_PASSWORD, EMAIL_USER, SMTP_HOST

AMOSTRAS = Path(__file__).resolve().parents[1] / "amostras"


def listar() -> None:
    print("Subpastas disponíveis em amostras/:")
    for pasta in sorted(p for p in AMOSTRAS.iterdir() if p.is_dir()):
        print(f"  {pasta.name} ({len(list(pasta.glob('*.jpg')))} foto(s))")
    print("  sem_anexo (envia e-mail sem fotos, para testar a validação)")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] == "--listar":
        listar()
        return

    cenario = sys.argv[1]
    lote_id = f"lote {datetime.now():%d/%m/%Y %H:%M}"

    msg = EmailMessage()
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_USER
    msg["Subject"] = f"{ASSUNTO_FILTRO} - {lote_id} - {cenario}"
    msg.set_content(f"Fotos do {lote_id} ({cenario}).")

    if cenario != "sem_anexo":
        pasta = AMOSTRAS / cenario
        if not pasta.is_dir():
            print(f"Subpasta '{cenario}' não existe em amostras/.")
            listar()
            sys.exit(1)
        fotos = sorted(pasta.glob("*.jpg"))
        if len(sys.argv) > 2:
            fotos = fotos[: int(sys.argv[2])]
        for foto in fotos:
            msg.add_attachment(
                foto.read_bytes(), maintype="image", subtype="jpeg",
                filename=foto.name,
            )
        print(f"Enviando {lote_id}: {len(fotos)} foto(s) de {cenario}/")
    else:
        print(f"Enviando {lote_id}: SEM anexos (teste de validação)")

    with smtplib.SMTP_SSL(SMTP_HOST, 465) as smtp:
        smtp.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        smtp.send_message(msg)
    print(f"Enviado para {EMAIL_USER} — o monitor deve captar no próximo ciclo.")


if __name__ == "__main__":
    main()
