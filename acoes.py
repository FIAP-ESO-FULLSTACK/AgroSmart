"""ExecutorAcoes — ações automatizadas disparadas pelas regras.

- alerta_email   (R1): e-mail de alerta de infestação via SMTP.
- plano_controle (R2): relatório de intervenção salvo em .txt.
- descarte       (R3): recomendação de descarte registrada em .txt.
"""
from datetime import datetime

from classificador import ClassificadorFrutas
from config import DIR_RELATORIOS
from notificador import Notificador


class ExecutorAcoes:
    def executar(self, lote_id: str, resumo: dict, acoes: list[dict]) -> None:
        if not acoes:
            print("  Regras avaliadas: nenhuma disparou — lote dentro da normalidade.")
            return
        for acao in acoes:
            print(f"  [{acao['regra']}] disparada: {acao['motivo']}")
            if acao["acao"] == "alerta_email":
                self._alerta_infestacao(lote_id, resumo, acao["motivo"])
            elif acao["acao"] == "plano_controle":
                self._plano_controle(lote_id, acao["praga"])
            elif acao["acao"] == "descarte":
                self._descarte(lote_id, resumo, acao["motivo"])

    # ------------------------------------------------------------------ R1
    @staticmethod
    def _alerta_infestacao(lote_id: str, resumo: dict, motivo: str) -> None:
        Notificador.alertar(
            f"[ALERTA AgroSmart] Infestação detectada — lote {lote_id}",
            f"Data: {datetime.now():%d/%m/%Y %H:%M}\n"
            f"Lote: {lote_id}\n\n"
            f"Motivo: {motivo}\n\n"
            f"Frutas analisadas: {resumo['total']}\n"
            f"Doentes: {resumo['pct_doentes']:.0%}\n"
            f"Podres: {resumo['pct_podres']:.0%}\n"
            f"Confiança média do modelo: {resumo['confianca_media']:.0%}\n"
            f"Pragas detectadas: {', '.join(resumo['pragas_detectadas']) or 'nenhuma'}\n\n"
            "Recomenda-se inspeção presencial do talhão nas próximas 24h.",
        )

    # ------------------------------------------------------------------ R2
    @staticmethod
    def _plano_controle(lote_id: str, praga: str) -> None:
        arquivo = DIR_RELATORIOS / f"plano_controle_{praga}_{lote_id}.txt"
        arquivo.write_text(
            "PLANO DE CONTROLE — AgroSmart\n"
            f"Gerado em: {datetime.now():%d/%m/%Y %H:%M}\n"
            f"Lote gatilho: {lote_id}\n"
            f"Praga: {praga}\n\n"
            f"Intervenção recomendada: {ClassificadorFrutas.recomendacao_para(praga)}\n\n"
            "Protocolo:\n"
            "1. Isolar a área afetada e sinalizar o talhão.\n"
            "2. Aplicar a intervenção recomendada em até 48h.\n"
            "3. Reforçar o monitoramento (envio diário de fotos) por 7 dias.\n"
            "4. Reavaliar com o agrônomo responsável após o período.\n",
            encoding="utf-8",
        )
        print(f"  [AÇÃO R2] Plano de controle salvo: {arquivo.name}")

    # ------------------------------------------------------------------ R3
    @staticmethod
    def _descarte(lote_id: str, resumo: dict, motivo: str) -> None:
        arquivo = DIR_RELATORIOS / f"descarte_{lote_id}.txt"
        arquivo.write_text(
            "RECOMENDAÇÃO DE DESCARTE — AgroSmart\n"
            f"Gerado em: {datetime.now():%d/%m/%Y %H:%M}\n"
            f"Lote: {lote_id}\n\n"
            f"Motivo: {motivo}\n"
            f"Frutas analisadas: {resumo['total']}\n"
            f"Podres: {resumo['pct_podres']:.0%} · Doentes: {resumo['pct_doentes']:.0%}\n",
            encoding="utf-8",
        )
        print(f"  [AÇÃO R3] Descarte recomendado: {arquivo.name}")
