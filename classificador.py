"""ClassificadorFrutas — SIMULAÇÃO do modelo hospedado no Databricks.

Recebe as fotos REAIS do lote, mas a inferência é simulada. Em produção,
`classificar_lote` faria uma chamada REST ao Model Serving endpoint:

    POST https://<workspace>.cloud.databricks.com/serving-endpoints/frutas/invocations
    Authorization: Bearer <token>
    Body: {"inputs": [<imagem em base64>]}

Dois modos de simulação:
  • COM cenário (linha "cenario: <nome>" no corpo do e-mail, enviada pelo
    producer): o veredito do lote segue o cenário, para demonstrar cada
    decisão das regras de forma controlada.
  • SEM cenário: sorteio determinístico (hash do conteúdo da imagem como
    semente) — a mesma foto sempre recebe o mesmo veredito.
"""
import hashlib
import random

# Cada cenário define o lote: fração de frutas podres e com praga (do total de
# fotos), faixa de confiança do modelo e a praga usada.
CENARIOS = {
    "saudavel":   {"podres": 0.0, "pragas": 0.0, "confianca": (0.80, 0.95)},
    "infestacao": {"podres": 0.4, "pragas": 0.0, "confianca": (0.75, 0.88)},
    "incerto":    {"podres": 0.4, "pragas": 0.0, "confianca": (0.65, 0.69)},
    "critico":    {"podres": 0.4, "pragas": 0.0, "confianca": (0.92, 0.98)},
    "descarte":   {"podres": 0.7, "pragas": 0.0, "confianca": (0.75, 0.88)},
    "praga":      {"podres": 0.0, "pragas": 0.2, "confianca": (0.80, 0.90), "praga": "cochonilha"},
}

DESCRICAO_CENARIOS = {
    "saudavel":   "lote saudável — nenhuma regra dispara",
    "infestacao": "40% doentes, confiança ~80% — R1",
    "incerto":    "40% doentes, mas confiança < 70% — nenhuma regra (AND falha)",
    "critico":    "40% doentes com confiança > 90% — R1 e R3 (ramo do OR)",
    "descarte":   "70% podres — R1 e R3 (ramo do OR)",
    "praga":      "1 fruta com cochonilha — repita 3x para a R2",
}


class ClassificadorFrutas:
    CLASSES = ["saudavel", "podre", "praga"]
    PESOS = [0.45, 0.35, 0.20]

    DOENCAS = {
        "podre": ["antracnose", "podridao-parda", "fungo-botrytis"],
        "praga": ["mosca-da-fruta", "bicho-furao", "cochonilha"],
    }

    RECOMENDACOES = {
        "antracnose": "Aplicar fungicida cúprico e remover frutos atingidos.",
        "podridao-parda": "Descartar frutos, podar ramos afetados e ventilar o pomar.",
        "fungo-botrytis": "Reduzir umidade, melhorar espaçamento e aplicar fungicida.",
        "mosca-da-fruta": "Instalar armadilhas McPhail e aplicar isca tóxica seletiva.",
        "bicho-furao": "Coleta e destruição de frutos caídos; controle biológico.",
        "cochonilha": "Aplicar óleo mineral e introduzir joaninhas predadoras.",
    }

    def classificar_lote(
        self, anexos: list[tuple[str, bytes]], cenario: str | None = None
    ) -> list[dict]:
        """Classifica as fotos do lote. Retorna uma lista de
        {"arquivo", "classe", "doenca", "confianca"}."""
        if cenario in CENARIOS:
            return self._por_cenario(anexos, CENARIOS[cenario])
        return [self._por_hash(nome, conteudo) for nome, conteudo in anexos]

    # ------------------------------------------------------------ simulações
    @staticmethod
    def _semente(conteudo: bytes) -> random.Random:
        return random.Random(int(hashlib.sha256(conteudo).hexdigest(), 16) % (2**32))

    def _por_hash(self, nome: str, conteudo: bytes) -> dict:
        rng = self._semente(conteudo)
        classe = rng.choices(self.CLASSES, weights=self.PESOS)[0]
        doenca = rng.choice(self.DOENCAS[classe]) if classe in self.DOENCAS else None
        return {
            "arquivo": nome,
            "classe": classe,
            "doenca": doenca,
            "confianca": round(rng.uniform(0.65, 0.99), 2),
        }

    def _por_cenario(self, anexos: list[tuple[str, bytes]], spec: dict) -> list[dict]:
        total = len(anexos)

        def quantos(fracao: float) -> int:
            return max(1, int(fracao * total + 0.5)) if fracao > 0 else 0

        n_podres, n_pragas = quantos(spec["podres"]), quantos(spec["pragas"])
        classes = ["podre"] * n_podres + ["praga"] * n_pragas
        classes += ["saudavel"] * (total - len(classes))

        resultados = []
        for (nome, conteudo), classe in zip(anexos, classes):
            rng = self._semente(conteudo)
            if classe == "praga":
                doenca = spec.get("praga") or rng.choice(self.DOENCAS["praga"])
            elif classe == "podre":
                doenca = rng.choice(self.DOENCAS["podre"])
            else:
                doenca = None
            minimo, maximo = spec["confianca"]
            resultados.append(
                {
                    "arquivo": nome,
                    "classe": classe,
                    "doenca": doenca,
                    "confianca": round(rng.uniform(minimo, maximo), 2),
                }
            )
        return resultados

    @classmethod
    def recomendacao_para(cls, doenca: str | None) -> str:
        if not doenca:
            return "Nenhuma ação necessária."
        return cls.RECOMENDACOES.get(doenca, "Encaminhar para análise do agrônomo.")
