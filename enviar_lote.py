"""Producer — envia um lote de fotos REAIS por e-mail para a própria caixa.

Coloque fotos de frutas (jpg/jpeg/png) na pasta amostras/ (ou passe
arquivos/pastas como argumento) e execute. O e-mail sai com o assunto
FRUTAS, que o monitor reconhece.

Com --cenario, o corpo do e-mail leva a linha "cenario: <nome>", que faz o
classificador simulado devolver o veredito daquele cenário — assim cada
decisão das regras pode ser demonstrada de forma controlada.

Uso:
    python enviar_lote.py                        # classificação por hash
    python enviar_lote.py --cenario infestacao   # simula uma decisão (lista: --ajuda-cenarios)
    python enviar_lote.py --sem-anexo            # e-mail SEM fotos (testa V1)
    python enviar_lote.py foto1.jpg foto2.png    # arquivos específicos (< 3 testa V2)
    python enviar_lote.py minha_pasta/           # todas as fotos de uma pasta
"""
import argparse
import mimetypes
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from classificador import CENARIOS, DESCRICAO_CENARIOS
from config import (
    ASSUNTO_INGESTAO,
    BASE,
    EMAIL_APP_PASSWORD,
    EMAIL_USER,
    SMTP_HOST,
    SMTP_PORT,
)

EXTENSOES = {".jpg", ".jpeg", ".png"}
DIR_AMOSTRAS = BASE / "amostras"


def coletar_fotos(argumentos: list[str]) -> list[Path]:
    if not argumentos:
        DIR_AMOSTRAS.mkdir(exist_ok=True)
        fontes = [DIR_AMOSTRAS]
    else:
        fontes = [Path(a) for a in argumentos]

    fotos = []
    for fonte in fontes:
        if fonte.is_dir():
            fotos += [p for p in sorted(fonte.iterdir()) if p.suffix.lower() in EXTENSOES]
        elif fonte.is_file() and fonte.suffix.lower() in EXTENSOES:
            fotos.append(fonte)
    return fotos


def enviar(fotos: list[Path], cenario: str | None = None) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"{ASSUNTO_INGESTAO} - lote {datetime.now():%d/%m %H:%M:%S}"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_USER
    corpo = f"Lote de monitoramento com {len(fotos)} amostras."
    if cenario:
        corpo += f"\ncenario: {cenario}"
    msg.set_content(corpo)

    for foto in fotos:
        tipo, _ = mimetypes.guess_type(foto.name)
        maintype, subtype = (tipo or "image/jpeg").split("/")
        msg.add_attachment(
            foto.read_bytes(), maintype=maintype, subtype=subtype, filename=foto.name
        )

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        smtp.send_message(msg)
    extra = f" (cenário: {cenario})" if cenario else ""
    print(f"Lote enviado para {EMAIL_USER} com {len(fotos)} foto(s){extra}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Envia um lote de teste do AgroSmart")
    parser.add_argument("fotos", nargs="*", help="fotos ou pastas (padrão: amostras/)")
    parser.add_argument("--cenario", choices=sorted(CENARIOS), help="simula uma decisão")
    parser.add_argument("--sem-anexo", action="store_true", help="e-mail sem nenhuma foto")
    parser.add_argument("--ajuda-cenarios", action="store_true", help="lista os cenários")
    args = parser.parse_args()

    if args.ajuda_cenarios:
        for nome, descricao in DESCRICAO_CENARIOS.items():
            print(f"{nome:<11}{descricao}")
        raise SystemExit

    if args.sem_anexo:
        enviar([])
        raise SystemExit

    fotos = coletar_fotos(args.fotos)
    if not fotos:
        raise SystemExit(
            f"Nenhuma foto encontrada. Coloque imagens em {DIR_AMOSTRAS}/ "
            "ou passe arquivos/pastas como argumento."
        )
    enviar(fotos, args.cenario)
