"""MotorRegras — regras de decisão (lógica booleana SE/ENTÃO) + resumo do lote.

R1 — Alerta de infestação:
    SE (pct_doentes > 30%) E (confianca_media > 70%)
    ENTÃO enviar alerta de infestação por e-mail.

R2 — Plano de controle:
    SE a MESMA praga aparecer em 3 lotes seguidos do mesmo remetente
    ENTÃO gerar plano de controle (relatório de intervenção).

R3 — Descarte:
    SE (pct_podres > 50%) OU (pct_doentes > 30% E confianca_media > 90%)
    ENTÃO recomendar o descarte do lote.

(R4 — monitoramento interrompido — está em inatividade.py, pois depende do tempo
e usa NÃO: SE parado > 3 dias E NÃO já alertado.)
"""
from config import (
    LIMIAR_CONFIANCA,
    LIMIAR_CONFIANCA_ALTA,
    LIMIAR_PCT_DOENTES,
    LIMIAR_PODRES_CRITICO,
    LOTES_SEGUIDOS_PRAGA,
)


class MotorRegras:
    @staticmethod
    def resumir_lote(resultados: list[dict]) -> dict:
        """Agrega as classificações individuais em métricas do lote."""
        total = len(resultados)
        doentes = [r for r in resultados if r["classe"] != "saudavel"]
        podres = [r for r in resultados if r["classe"] == "podre"]
        pragas = {r["doenca"] for r in resultados if r["classe"] == "praga"}
        return {
            "total": total,
            "pct_doentes": round(len(doentes) / total, 2) if total else 0.0,
            "pct_podres": round(len(podres) / total, 2) if total else 0.0,
            "confianca_media": (
                round(sum(r["confianca"] for r in resultados) / total, 2)
                if total
                else 0.0
            ),
            "pragas_detectadas": sorted(pragas),
        }

    @staticmethod
    def avaliar(resumo: dict, historico: list, remetente: str) -> list[dict]:
        """Avalia R1, R2 e R3 sobre o resumo do lote atual.

        `historico` são os lotes já gravados (anteriores ao atual).
        Retorna a lista de ações disparadas.
        """
        acoes = []
        doentes = resumo["pct_doentes"] > LIMIAR_PCT_DOENTES

        # R1: doentes > limiar E confiança > limiar
        if doentes and resumo["confianca_media"] > LIMIAR_CONFIANCA:
            acoes.append(
                {
                    "regra": "R1",
                    "acao": "alerta_email",
                    "motivo": (
                        f"{resumo['pct_doentes']:.0%} de frutas doentes "
                        f"(> {LIMIAR_PCT_DOENTES:.0%}) com confiança média "
                        f"{resumo['confianca_media']:.0%} (> {LIMIAR_CONFIANCA:.0%})"
                    ),
                }
            )

        # R2: mesma praga nos últimos N lotes do remetente (anteriores + atual)
        do_remetente = [l for l in historico if l.get("remetente") == remetente]
        anteriores = do_remetente[-(LOTES_SEGUIDOS_PRAGA - 1):]
        for praga in resumo["pragas_detectadas"]:
            seguidos = len(anteriores) == LOTES_SEGUIDOS_PRAGA - 1 and all(
                praga in (l.get("resumo") or {}).get("pragas_detectadas", [])
                for l in anteriores
            )
            if seguidos:
                acoes.append(
                    {
                        "regra": "R2",
                        "acao": "plano_controle",
                        "motivo": (
                            f"Praga '{praga}' detectada em "
                            f"{LOTES_SEGUIDOS_PRAGA} lotes seguidos"
                        ),
                        "praga": praga,
                    }
                )

        # R3: podres > 50% OU (doentes > 30% E confiança > 90%)
        if resumo["pct_podres"] > LIMIAR_PODRES_CRITICO or (
            doentes and resumo["confianca_media"] > LIMIAR_CONFIANCA_ALTA
        ):
            acoes.append(
                {
                    "regra": "R3",
                    "acao": "descarte",
                    "motivo": (
                        f"{resumo['pct_podres']:.0%} de frutas podres e "
                        f"{resumo['pct_doentes']:.0%} doentes com confiança "
                        f"{resumo['confianca_media']:.0%} — recomendar descarte"
                    ),
                }
            )

        return acoes
