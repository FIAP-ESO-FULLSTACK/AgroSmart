"""leitura (IMAP), envio (SMTP)
e o checkpoint de UIDs já processados.

O checkpoint (processados.txt) garante que um e-mail tratado nunca é
reprocessado, mesmo reiniciando o programa.
"""
import email
import html as html_mod
import imaplib
import os
import smtplib
from email.header import decode_header
from email.message import EmailMessage, Message
from email.utils import parseaddr

from agrosmart.config import (
    ARQUIVO_CHECKPOINT,
    ASSUNTO_FILTRO,
    EMAIL_APP_PASSWORD,
    EMAIL_USER,
    IMAP_HOST,
    SMTP_HOST,
)

class ServicoEmail:
    """Caixa de e-mail do AgroSmart: busca lotes novos e responde remetentes."""

    def __init__(self):
        self.imap: imaplib.IMAP4_SSL | None = None

    # ------------------------------------------------------------- conexão
    def conectar(self) -> None:
        self.imap = imaplib.IMAP4_SSL(IMAP_HOST)
        self.imap.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        self.imap.select("INBOX")

    def desconectar(self) -> None:
        if self.imap is not None:
            try:
                self.imap.logout()
            except Exception:
                pass
            self.imap = None

    # ------------------------------------------------------------- leitura
    def buscar_novos(self) -> list[tuple[str, Message]]:
        """[(uid, mensagem)] dos e-mails com o assunto-filtro ainda não
        processados. Quem marca como processado é o chamador, depois de
        tratar o e-mail com sucesso."""
        self.imap.noop()  # força o servidor a refletir chegadas recentes
        status, dados = self.imap.uid("search", None, f'SUBJECT "{ASSUNTO_FILTRO}"')
        if status != "OK":
            return []

        processados = self._carregar_processados()
        novos = []
        for uid_bytes in dados[0].split():
            uid = uid_bytes.decode()
            if uid in processados:
                continue
            status, partes = self.imap.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not partes or partes[0] is None:
                continue
            novos.append((uid, email.message_from_bytes(partes[0][1])))
        return novos

    @staticmethod
    def resumo(msg: Message) -> tuple[str, str]:
        """(remetente, assunto) legíveis de uma mensagem."""
        remetente = parseaddr(msg.get("From", ""))[1]
        return remetente, _decodificar(msg.get("Subject"))

    @staticmethod
    def eh_automatico(msg: Message) -> bool:
        """True para mensagens automáticas (respostas do próprio sistema,
        out-of-office etc.) — não devem ser processadas como lote."""
        auto = (msg.get("Auto-Submitted") or "").lower()
        return bool(auto) and auto != "no"

    @staticmethod
    def extrair_fotos(msg: Message) -> list[tuple[str, bytes]]:
        """[(nome_do_arquivo, conteúdo)] dos anexos de imagem."""
        fotos = []
        for parte in msg.walk():
            if parte.get_content_maintype() != "image":
                continue
            nome = _decodificar(parte.get_filename()) or f"foto_{len(fotos) + 1}"
            fotos.append((nome, parte.get_payload(decode=True)))
        return fotos

    # -------------------------------------------------------------- envio
    def notificar(
        self,
        destinatario: str,
        assunto: str,
        corpo: str,
        em_resposta_a: Message | None = None,
        nivel: str = "info",
    ) -> None:
        """Envia um e-mail (texto + versão HTML estilizada). Se `em_resposta_a`
        for passado, responde na MESMA conversa (In-Reply-To/References +
        assunto "Re: ..."). `nivel` define a cor do cabeçalho HTML:
        alerta (vermelho), aviso (laranja), ok (verde), info (cinza-azulado)."""
        msg = EmailMessage()
        msg["From"] = EMAIL_USER
        msg["To"] = destinatario
        # Marca como automático: a entrada ignora mensagens com este cabeçalho,
        # o que impede loops (ex.: sistema respondendo às próprias respostas).
        msg["Auto-Submitted"] = "auto-replied"

        if em_resposta_a is not None and em_resposta_a.get("Message-ID"):
            id_original = em_resposta_a["Message-ID"]
            assunto_original = _decodificar(em_resposta_a.get("Subject"))
            msg["In-Reply-To"] = id_original
            msg["References"] = (em_resposta_a.get("References", "") + " " + id_original).strip()
            msg["Subject"] = f"Re: {assunto_original}"
        else:
            msg["Subject"] = assunto

        # Texto simples (fallback) + alternativa HTML: clientes de e-mail
        # mostram o HTML; os dois carregam o mesmo conteúdo.
        msg.set_content(f"{assunto}\n\n{corpo}")
        msg.add_alternative(_corpo_html(assunto, corpo, nivel), subtype="html")

        with smtplib.SMTP_SSL(SMTP_HOST, 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_APP_PASSWORD)
            smtp.send_message(msg)

    def avisar_sem_anexo(
        self, destinatario: str, assunto_original: str, em_resposta_a: Message | None = None
    ) -> None:
        corpo = (
            f"Olá,\n"
            f"\n"
            f"Recebemos seu e-mail \"{assunto_original}\", mas ele não contém nenhuma foto em anexo.\n"
            f"\n"
            f"Para que o lote seja analisado, reenvie o e-mail com as fotos das frutas anexadas (jpg ou png).\n"
        )
        self.notificar(
            destinatario,
            "AgroSmart: lote rejeitado — e-mail sem fotos em anexo",
            corpo,
            em_resposta_a=em_resposta_a,
            nivel="aviso",
        )

    # --------------------------------------------------------- checkpoint
    @staticmethod
    def _carregar_processados() -> set[str]:
        if not os.path.exists(ARQUIVO_CHECKPOINT):
            return set()
        with open(ARQUIVO_CHECKPOINT, encoding="utf-8") as f:
            return set(f.read().split())

    @staticmethod
    def marcar_processado(uid: str) -> None:
        with open(ARQUIVO_CHECKPOINT, "a", encoding="utf-8") as f:
            f.write(uid + "\n")


_CORES_NIVEL = {
    "alerta": "#c0392b",  # vermelho
    "aviso": "#e67e22",   # laranja
    "ok": "#2e8b57",      # verde
    "info": "#34495e",    # cinza-azulado
}


def _corpo_html(titulo: str, corpo: str, nivel: str) -> str:
    """Monta a versão HTML da mensagem: um cartão com faixa colorida pelo
    nível, título e os parágrafos do corpo (estilos inline, como e-mail exige)."""
    cor = _CORES_NIVEL.get(nivel, _CORES_NIVEL["info"])
    paragrafos = "".join(
        f'<p style="margin:0 0 14px;color:#333;font-size:15px;line-height:1.5">'
        f"{html_mod.escape(p)}</p>"
        for p in corpo.split("\n\n")
        if p.strip()
    )
    return f"""\
<html>
  <body style="margin:0;padding:24px;background:#eef2ee;font-family:Segoe UI,Arial,sans-serif">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td align="center">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0"
               style="background:#fff;border-radius:10px;overflow:hidden;
                      box-shadow:0 2px 8px rgba(0,0,0,.08)">
          <tr>
            <td style="background:{cor};padding:16px 28px">
              <span style="color:#fff;font-size:18px;font-weight:bold">🌱 AgroSmart</span>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 28px">
              <h2 style="margin:0 0 16px;color:{cor};font-size:17px">{html_mod.escape(titulo)}</h2>
              {paragrafos}
            </td>
          </tr>
          <tr>
            <td style="padding:14px 28px;background:#f7f9f7;border-top:1px solid #e5e9e5">
              <span style="color:#889;font-size:12px">
                Mensagem automática do sistema AgroSmart — monitoramento de lavouras por e-mail.
              </span>
            </td>
          </tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
"""


def _decodificar(valor: str | None) -> str:
    """Cabeçalhos podem vir codificados (=?utf-8?...?=); decodifica tudo."""
    if not valor:
        return ""
    partes = []
    for texto, charset in decode_header(valor):
        if isinstance(texto, bytes):
            texto = texto.decode(charset or "utf-8", errors="replace")
        partes.append(texto)
    return "".join(partes)
