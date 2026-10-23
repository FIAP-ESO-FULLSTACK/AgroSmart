"""Notificador — e-mails automáticos do sistema (respostas e alertas).

Todo e-mail enviado aqui leva o cabeçalho Auto-Submitted e NUNCA pode ter a
palavra de ingestão (FRUTAS) no assunto, senão o monitor leria a própria
mensagem como um novo lote e entraria em loop.
"""
import smtplib
from email.message import EmailMessage

from config import (
    ASSUNTO_INGESTAO,
    EMAIL_ALERTA_DESTINO,
    EMAIL_APP_PASSWORD,
    EMAIL_USER,
    SMTP_HOST,
    SMTP_PORT,
)

_RODAPE = "\n\nMensagem automática do AgroSmart."


class Notificador:
    @staticmethod
    def _enviar(destinatario: str, assunto: str, corpo: str, message_id: str | None = None) -> bool:
        assert ASSUNTO_INGESTAO.lower() not in assunto.lower(), "assunto geraria loop"
        msg = EmailMessage()
        msg["Subject"] = assunto
        msg["From"] = EMAIL_USER
        msg["To"] = destinatario
        msg["Auto-Submitted"] = "auto-replied"
        if message_id:
            msg["In-Reply-To"] = message_id
            msg["References"] = message_id
        msg.set_content(corpo + _RODAPE)
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.login(EMAIL_USER, EMAIL_APP_PASSWORD)
                smtp.send_message(msg)
        except Exception as exc:
            print(f"  [E-MAIL] Falha ao enviar para {destinatario}: {exc}")
            return False
        print(f"  [E-MAIL] Enviado para {destinatario}: {assunto}")
        return True

    # ------------------------------------------- respostas ao remetente (V1-V2)
    @classmethod
    def avisar_sem_anexo(cls, destinatario, assunto_original, message_id) -> bool:
        return cls._enviar(
            destinatario,
            "[AgroSmart] Seu e-mail não continha fotos anexadas",
            f'Recebemos seu e-mail "{assunto_original}", mas ele não tinha nenhuma '
            "foto anexada, então o lote não foi processado.\n\n"
            "Reenvie o e-mail com as fotos em anexo (JPG ou PNG), mantendo a "
            "palavra combinada no assunto.",
            message_id,
        )

    @classmethod
    def avisar_amostra_insuficiente(cls, destinatario, assunto_original, message_id, recebidas, minimo) -> bool:
        return cls._enviar(
            destinatario,
            "[AgroSmart] Amostra insuficiente — reenvie o lote",
            f'Seu e-mail "{assunto_original}" trouxe {recebidas} foto(s), mas o '
            f"mínimo para análise é {minimo}. O lote não foi processado.\n\n"
            f"Reenvie com pelo menos {minimo} fotos do talhão.",
            message_id,
        )

    # ----------------------------------------------------------------- alertas
    @classmethod
    def alertar(cls, assunto: str, corpo: str) -> bool:
        return cls._enviar(EMAIL_ALERTA_DESTINO, assunto, corpo)

    @classmethod
    def alertar_inatividade(cls, remetente: str, ultimo_lote, dias: float) -> bool:
        # Assunto fixo: o remetente pode conter a palavra de ingestão e geraria loop.
        return cls._enviar(
            EMAIL_ALERTA_DESTINO,
            "[ALERTA AgroSmart] Monitoramento interrompido",
            f"{remetente} não envia lotes há mais de {dias:g} dia(s).\n"
            f"Último lote recebido: {ultimo_lote:%d/%m/%Y %H:%M}\n\n"
            "Verifique se o envio de fotos foi interrompido.",
        )
