"""R4 — Monitoramento interrompido (regra que depende do tempo).

    SE (agora − último lote do remetente > 3 dias)
       E NÃO (alerta já enviado para esse último lote)
    ENTÃO alertar que o remetente está sem enviar lotes.

O estado "já alertado" fica em estado_inatividade.json: um remetente só
gera novo alerta depois que enviar um lote novo e voltar a ficar parado.
"""
import json
from datetime import datetime, timedelta

from config import ARQ_ESTADO_INATIVIDADE, DIAS_SEM_LOTE


class VerificadorInatividade:
    def __init__(self):
        self.estado = self._carregar()

    @staticmethod
    def _carregar() -> dict:
        if ARQ_ESTADO_INATIVIDADE.exists():
            return json.loads(ARQ_ESTADO_INATIVIDADE.read_text(encoding="utf-8"))
        return {}

    def pendentes(self, historico: list, agora: datetime) -> list[tuple[str, datetime]]:
        """Remetentes parados há mais de DIAS_SEM_LOTE dias e ainda não alertados."""
        ultimo: dict[str, datetime] = {}
        for lote in historico:
            remetente = lote.get("remetente")
            if not remetente:
                continue
            quando = datetime.fromisoformat(lote["data_iso"])
            if remetente not in ultimo or quando > ultimo[remetente]:
                ultimo[remetente] = quando

        return [
            (remetente, quando)
            for remetente, quando in ultimo.items()
            if agora - quando > timedelta(days=DIAS_SEM_LOTE)
            and self.estado.get(remetente) != quando.isoformat()
        ]

    def marcar(self, remetente: str, ultimo_lote: datetime) -> None:
        self.estado[remetente] = ultimo_lote.isoformat()
        ARQ_ESTADO_INATIVIDADE.write_text(
            json.dumps(self.estado, ensure_ascii=False, indent=2), encoding="utf-8"
        )
