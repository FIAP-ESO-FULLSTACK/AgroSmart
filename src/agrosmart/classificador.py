"""Classificação e análise de lotes de fotos (modelo pré-treinado PlantVillage).

O modelo (MobileNetV2, 38 classes) roda local em CPU; na primeira execução é
baixado do Hugging Face e fica em cache (~/.cache/huggingface).

Além de classificar cada foto, a classe aplica as REGRAS DE DECISÃO do
AgroSmart sobre o lote (item 1 da entrega):

R1 (fotos ilegíveis):   SE nenhuma foto avaliada com confiança E lote tem fotos
                        ENTÃO pedir reenvio com fotos melhores
R2 (infestação):        SE pct_doentes > LIMIAR_INFESTACAO
                        ENTÃO alerta de infestação ao remetente
R3 (recorrência):       SE mesma doença predominante nos últimos
                        LOTES_RECORRENCIA lotes do remetente
                        ENTÃO acionar plano de controle
R4 (lote saudável):     SE doentes == 0 E NÃO houve foto descartada
                        ENTÃO confirmar lote saudável

O histórico (historico.jsonl, um JSON por linha) é a memória entre lotes
que permite à R3 enxergar "N lotes seguidos".
"""
import io
import json
import os
from datetime import datetime

from PIL import Image
from transformers import pipeline

from agrosmart.config import (
    ARQUIVO_HISTORICO,
    CONFIANCA_MINIMA,
    LIMIAR_INFESTACAO,
    LOTES_RECORRENCIA,
)

MODELO = "linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification"


class Classificador:
    """Carrega o modelo uma vez; classifica fotos e analisa lotes."""

    def __init__(self):
        # O preprocessor_config.json deste modelo é antigo e o transformers
        # atual não o reconhece; usamos o processor da arquitetura original.
        self._pipeline = pipeline(
            "image-classification",
            model=MODELO,
            image_processor="google/mobilenet_v2_1.0_224",
        )

    # --------------------------------------------------------- classificação
    def classificar(self, conteudo: bytes) -> dict:
        """Classifica uma foto. Retorna:
        {"classe": "Apple Scab", "saudavel": False, "confianca": 0.97}
        Classes saudáveis vêm como "Healthy <Cultura> Plant"."""
        imagem = Image.open(io.BytesIO(conteudo)).convert("RGB")
        melhor = self._pipeline(imagem, top_k=1)[0]
        classe = melhor["label"]
        return {
            "classe": classe,
            "saudavel": "healthy" in classe.lower(),
            "confianca": round(melhor["score"], 4),
        }

    # -------------------------------------------------------------- análise
    def analisar_lote(self, remetente: str, resultados: list[dict]) -> dict:
        """Analisa um lote já classificado: resume, aplica as regras e grava
        no histórico. Retorna {"resumo": {...}, "acoes": [{...}, ...]}."""
        resumo = self._resumir(resultados)
        acoes = self._avaliar_regras(remetente, resumo)
        self._registrar_historico(remetente, resumo)
        return {"resumo": resumo, "acoes": acoes}

    @staticmethod
    def _resumir(resultados: list[dict]) -> dict:
        """Agrega os resultados das fotos em números para as regras. Fotos com
        confiança abaixo de CONFIANCA_MINIMA são descartadas (ilegíveis)."""
        avaliadas = [r for r in resultados if r["confianca"] >= CONFIANCA_MINIMA]
        doentes = [r for r in avaliadas if not r["saudavel"]]
        contagem: dict[str, int] = {}
        for r in doentes:
            contagem[r["classe"]] = contagem.get(r["classe"], 0) + 1
        return {
            "total_fotos": len(resultados),
            "avaliadas": len(avaliadas),
            "descartadas": len(resultados) - len(avaliadas),
            "doentes": len(doentes),
            "pct_doentes": len(doentes) / len(avaliadas) if avaliadas else 0.0,
            "doencas": contagem,
            "doenca_predominante": max(contagem, key=contagem.get) if contagem else None,
        }

    def _avaliar_regras(self, remetente: str, resumo: dict) -> list[dict]:
        """Aplica R1-R4. Retorna [{regra, motivo, assunto, corpo}, ...]."""
        acoes = []

        # R1 — nenhuma foto aproveitável
        if resumo["avaliadas"] == 0 and resumo["total_fotos"] > 0:
            acoes.append({
                "regra": "R1", "nivel": "aviso",
                "motivo": "nenhuma foto do lote pôde ser avaliada com confiança",
                "assunto": "AgroSmart: fotos ilegíveis — reenvie o lote",
                "corpo": (
                    f"Olá,\n"
                    f"\n"
                    f"Nenhuma das {resumo['total_fotos']} foto(s) do seu lote pôde ser avaliada com confiança pelo classificador.\n"
                    f"\n"
                    f"Reenvie as fotos com melhor iluminação e foco, enquadrando uma folha por foto.\n"
                ),
            })
            return acoes  # sem fotos avaliadas não há o que analisar nas demais

        # R2 — infestação no lote
        if resumo["pct_doentes"] > LIMIAR_INFESTACAO:
            doencas = ", ".join(
                f"{d} ({n} foto(s))" for d, n in resumo["doencas"].items()
            )
            acoes.append({
                "regra": "R2", "nivel": "alerta",
                "motivo": f"{resumo['pct_doentes']:.0%} das fotos avaliadas estão "
                          f"doentes (limiar: {LIMIAR_INFESTACAO:.0%})",
                "assunto": "AgroSmart: ALERTA de infestação no seu lote",
                "corpo": (
                    f"Olá,\n"
                    f"\n"
                    f"Detectamos sinais de infestação no lote enviado: {resumo['doentes']} de {resumo['avaliadas']} foto(s) avaliada(s) apresentam doença ({resumo['pct_doentes']:.0%}, acima do limiar de {LIMIAR_INFESTACAO:.0%}).\n"
                    f"\n"
                    f"Diagnóstico por foto: {doencas}.\n"
                    f"\n"
                    f"Recomendamos inspeção da área nos próximos dias e isolamento das plantas afetadas.\n"
                ),
            })

        # R3 — mesma doença recorrente em lotes seguidos do mesmo remetente
        predominante = resumo["doenca_predominante"]
        if predominante is not None:
            anteriores = [
                h for h in self._carregar_historico() if h["remetente"] == remetente
            ]
            ultimos = anteriores[-(LOTES_RECORRENCIA - 1):]
            recorrente = (
                len(ultimos) == LOTES_RECORRENCIA - 1
                and all(h.get("doenca_predominante") == predominante for h in ultimos)
            )
            if recorrente:
                acoes.append({
                    "regra": "R3", "nivel": "alerta",
                    "motivo": f"'{predominante}' predominante em "
                              f"{LOTES_RECORRENCIA} lotes seguidos",
                    "assunto": "AgroSmart: doença recorrente — acionar plano de controle",
                    "corpo": (
                        f"Olá,\n"
                        f"\n"
                        f"A doença \"{predominante}\" foi a predominante nos seus últimos {LOTES_RECORRENCIA} lotes. Isso indica um problema persistente, não um caso isolado.\n"
                        f"\n"
                        f"Recomendamos acionar o plano de controle: aplicação de defensivo adequado, remoção das plantas mais afetadas e novo envio de fotos em 7 dias para acompanhamento.\n"
                    ),
                })

        # R4 — lote totalmente saudável (nenhuma doente E nenhuma descartada)
        if resumo["doentes"] == 0 and resumo["descartadas"] == 0:
            acoes.append({
                "regra": "R4", "nivel": "ok",
                "motivo": "todas as fotos avaliadas e saudáveis",
                "assunto": "AgroSmart: lote analisado — tudo saudável",
                "corpo": (
                    f"Olá,\n"
                    f"\n"
                    f"Boas notícias: as {resumo['avaliadas']} foto(s) do seu lote foram analisadas e nenhuma apresenta sinais de doença.\n"
                ),
            })

        return acoes

    # ------------------------------------------------------------ histórico
    @staticmethod
    def _carregar_historico() -> list[dict]:
        if not os.path.exists(ARQUIVO_HISTORICO):
            return []
        with open(ARQUIVO_HISTORICO, encoding="utf-8") as f:
            return [json.loads(linha) for linha in f if linha.strip()]

    @staticmethod
    def _registrar_historico(remetente: str, resumo: dict) -> None:
        registro = {
            "data": datetime.now().isoformat(timespec="seconds"),
            "remetente": remetente,
            **resumo,
        }
        with open(ARQUIVO_HISTORICO, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
