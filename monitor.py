"""MonitorEmail — ingestão por e-mail (IMAP, micro-batch) com checkpoint.

Busca na INBOX os e-mails com o assunto combinado, identifica UIDs ainda
não processados (checkpoint em processed_uids.json) e entrega cada
mensagem para o pipeline. Também extrai os anexos de imagem.
"""
import email
import email.header
import email.message
import email.utils
import imaplib
import json
import re
from datetime import datetime
from pathlib import Path

from config import (
    ARQ_CHECKPOINT,
    ASSUNTO_INGESTAO,
    EMAIL_APP_PASSWORD,
    EMAIL_USER,
    IMAP_HOST,
)


class MonitorEmail:
    def __init__(self):
        self.uids_vistos = self._carregar_uids()

    # ----------------------------------------------------------- checkpoint
    @staticmethod
    def _carregar_uids() -> set:
        if ARQ_CHECKPOINT.exists():
            return set(json.loads(ARQ_CHECKPOINT.read_text(encoding="utf-8")))
        return set()

    def _salvar_uids(self) -> None:
        ARQ_CHECKPOINT.write_text(
            json.dumps(sorted(self.uids_vistos)), encoding="utf-8"
        )

    def marcar_processado(self, uid: str) -> None:
        """Registra o UID no checkpoint (chamado após CADA e-mail)."""
        self.uids_vistos.add(uid)
        self._salvar_uids()

    # ------------------------------------------------------------------ IMAP
    def buscar_novos(self) -> list[tuple[str, email.message.Message]]:
        """Retorna [(uid, mensagem)] apenas dos e-mails ainda não processados."""
        mail = imaplib.IMAP4_SSL(IMAP_HOST)
        try:
            mail.login(EMAIL_USER, EMAIL_APP_PASSWORD)
            mail.select("INBOX")

            _, dados = mail.uid("search", None, f'(SUBJECT "{ASSUNTO_INGESTAO}")')
            uids = [u.decode() for u in dados[0].split()]
            novos = [u for u in uids if u not in self.uids_vistos]

            if not novos:
                print(
                    f"[{datetime.now():%H:%M:%S}] Nenhum e-mail novo "
                    f"({len(uids)} já processados)."
                )

            mensagens = []
            for uid in novos:
                _, msg_data = mail.uid("fetch", uid, "(RFC822)")
                mensagens.append((uid, email.message_from_bytes(msg_data[0][1])))
            return mensagens
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    # ----------------------------------------------------------- validação
    @staticmethod
    def extrair_anexos(msg: email.message.Message) -> list[tuple[str, bytes]]:
        """Retorna [(nome, bytes)] dos anexos de imagem. Lista vazia = sem anexo."""
        anexos = []
        for i, parte in enumerate(msg.walk(), start=1):
            if parte.get_content_maintype() != "image":
                continue
            conteudo = parte.get_payload(decode=True)
            if not conteudo:
                continue
            nome = parte.get_filename()
            if nome:
                nome = str(email.header.make_header(email.header.decode_header(nome)))
            anexos.append((Path(nome or f"foto_{i}.jpg").name, conteudo))
        return anexos

    @staticmethod
    def extrair_cenario(msg: email.message.Message) -> str | None:
        """Lê a linha 'cenario: <nome>' do corpo do e-mail (ou None)."""
        for parte in msg.walk():
            if parte.get_content_type() != "text/plain" or parte.get_filename():
                continue
            texto = parte.get_payload(decode=True) or b""
            achado = re.search(
                r"cen[aá]rio\s*[:=]\s*([\w-]+)",
                texto.decode(parte.get_content_charset() or "utf-8", errors="replace"),
                re.IGNORECASE,
            )
            if achado:
                return achado.group(1).lower()
        return None

    @staticmethod
    def eh_resposta_automatica(msg: email.message.Message) -> bool:
        """True se a mensagem foi gerada por robô (evita loop de respostas)."""
        return msg.get("Auto-Submitted", "no").strip().lower() != "no"

    @staticmethod
    def remetente_de(msg: email.message.Message) -> str:
        return email.utils.parseaddr(msg.get("From", ""))[1]

    @staticmethod
    def assunto_de(msg: email.message.Message) -> str:
        bruto = msg.get("Subject", "")
        return str(email.header.make_header(email.header.decode_header(bruto)))
