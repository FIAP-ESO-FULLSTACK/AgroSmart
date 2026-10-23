"""AgroSmart — ponto de entrada.

Fluxo: INBOX (assunto FRUTAS) → UIDs novos → validações de entrada →
  V1 sem foto / V2 menos de MIN_FOTOS fotos:
      responde ao remetente pedindo o reenvio (lote NÃO é gravado);
  lote válido: ClassificadorFrutas (Databricks simulado) → MotorRegras
      (R1/R2/R3) → grava fotos + resultados no banco simulado → ExecutorAcoes.
A cada ciclo, a regra R4 alerta remetentes parados há mais de N dias.

O checkpoint de UIDs garante que e-mails já tratados NUNCA sejam
processados de novo, mesmo reiniciando o programa.

Uso: python main.py
"""
import time
from datetime import datetime

from acoes import ExecutorAcoes
from armazenamento import BancoSimulado
from classificador import CENARIOS, ClassificadorFrutas
from config import ASSUNTO_INGESTAO, DIAS_SEM_LOTE, INTERVALO_POLLING, MIN_FOTOS
from inatividade import VerificadorInatividade
from monitor import MonitorEmail
from notificador import Notificador
from regras import MotorRegras


class AgroSmart:
    def __init__(self):
        self.monitor = MonitorEmail()
        self.classificador = ClassificadorFrutas()
        self.regras = MotorRegras()
        self.acoes = ExecutorAcoes()
        self.banco = BancoSimulado()
        self.notificador = Notificador()
        self.inatividade = VerificadorInatividade()

    @staticmethod
    def _rejeitar(remetente: str, enviar_aviso) -> bool:
        """Responde ao remetente. True = UID pode ir para o checkpoint."""
        if not remetente:
            print("  Remetente desconhecido — não há para quem avisar.")
            return True
        return enviar_aviso()

    def processar_email(self, uid: str, msg) -> bool:
        """Trata um e-mail. Retorna True se o UID pode ir para o checkpoint."""
        lote_id = f"L{uid}"
        remetente = self.monitor.remetente_de(msg)
        assunto = self.monitor.assunto_de(msg)
        message_id = msg.get("Message-ID")
        print(f"\n[{datetime.now():%H:%M:%S}] Novo e-mail {lote_id} de {remetente}")

        if self.monitor.eh_resposta_automatica(msg):
            print("  Mensagem automática — ignorada.")
            return True

        # V1 — precisa ter foto anexada
        fotos = self.monitor.extrair_anexos(msg)
        if not fotos:
            print("  [V1] E-mail sem anexo de imagem — lote rejeitado.")
            return self._rejeitar(
                remetente,
                lambda: self.notificador.avisar_sem_anexo(remetente, assunto, message_id),
            )

        # V2 — amostra mínima
        if len(fotos) < MIN_FOTOS:
            print(f"  [V2] {len(fotos)} foto(s) < mínimo de {MIN_FOTOS} — lote rejeitado.")
            return self._rejeitar(
                remetente,
                lambda: self.notificador.avisar_amostra_insuficiente(
                    remetente, assunto, message_id, len(fotos), MIN_FOTOS
                ),
            )

        print(f"  {len(fotos)} foto(s) recebida(s)")

        # Classificação simulada (por cenário, se o e-mail indicar um)
        cenario = self.monitor.extrair_cenario(msg)
        if cenario and cenario not in CENARIOS:
            print(f"  Cenário '{cenario}' desconhecido — usando simulação por hash.")
            cenario = None
        origem = f"cenário {cenario}" if cenario else "por hash"
        print(f"  Classificação simulada ({origem}):")
        resultados = self.classificador.classificar_lote(fotos, cenario)
        for r in resultados:
            extra = f" ({r['doenca']})" if r["doenca"] else ""
            print(f"    {r['arquivo']}: {r['classe']}{extra} — confiança {r['confianca']:.0%}")

        # Regras (sobre o histórico anterior) → grava → executa ações
        resumo = self.regras.resumir_lote(resultados)
        acoes = self.regras.avaliar(resumo, self.banco.indice, remetente)
        registro = self.banco.salvar_lote(
            lote_id, remetente, assunto, fotos, resultados, resumo, acoes, cenario
        )
        print(
            f"  [BANCO] {registro['total_fotos']} foto(s) gravada(s) em "
            f"banco_simulado/{lote_id}/"
        )
        self.acoes.executar(lote_id, resumo, acoes)
        return True

    def checar_inatividade(self) -> None:
        """R4: alerta remetentes sem lote há mais de DIAS_SEM_LOTE dias."""
        for remetente, ultimo in self.inatividade.pendentes(
            self.banco.indice, datetime.now()
        ):
            print(f"  [R4] {remetente} sem lote desde {ultimo:%d/%m/%Y %H:%M}")
            if self.notificador.alertar_inatividade(remetente, ultimo, DIAS_SEM_LOTE):
                self.inatividade.marcar(remetente, ultimo)

    def ciclo(self) -> None:
        for uid, msg in self.monitor.buscar_novos():
            if self.processar_email(uid, msg):
                self.monitor.marcar_processado(uid)  # checkpoint após CADA e-mail
        self.checar_inatividade()

    def executar(self) -> None:
        print("AgroSmart — monitor IMAP iniciado (Ctrl+C para parar)")
        print(
            f"Filtro: assunto contendo '{ASSUNTO_INGESTAO}' · "
            f"polling {INTERVALO_POLLING}s"
        )
        while True:
            try:
                self.ciclo()
            except Exception as exc:
                print(f"[ERRO] {exc} — tentando de novo no próximo ciclo")
            time.sleep(INTERVALO_POLLING)


if __name__ == "__main__":
    AgroSmart().executar()
