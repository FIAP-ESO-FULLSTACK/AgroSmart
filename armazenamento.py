"""BancoSimulado — simula a gravação das fotos em um banco de dados.

Em produção as imagens iriam para um storage/tabela (ex.: volume do
Databricks ou blob storage). Aqui cada lote vira uma pasta em
banco_simulado/<lote_id>/ e os metadados vão para indice_lotes.json — que
também serve de histórico para as regras R2 (pragas seguidas) e R4 (inatividade).
"""
import json
from datetime import datetime

from config import ARQ_INDICE, DIR_BANCO


class BancoSimulado:
    def __init__(self):
        self.indice = self._carregar_indice()

    @staticmethod
    def _carregar_indice() -> list:
        if ARQ_INDICE.exists():
            return json.loads(ARQ_INDICE.read_text(encoding="utf-8"))
        return []

    def salvar_lote(
        self,
        lote_id: str,
        remetente: str,
        assunto: str,
        anexos: list[tuple[str, bytes]],
        resultados: list[dict],
        resumo: dict,
        acoes: list[dict],
        cenario: str | None = None,
    ) -> dict:
        pasta = DIR_BANCO / lote_id
        pasta.mkdir(exist_ok=True)

        nomes = []
        for i, (nome, conteudo) in enumerate(anexos, start=1):
            destino = pasta / nome
            if destino.exists():  # dois anexos com o mesmo nome no mesmo e-mail
                destino = pasta / f"{i}_{nome}"
            destino.write_bytes(conteudo)
            nomes.append(destino.name)

        agora = datetime.now()
        registro = {
            "lote_id": lote_id,
            "data": f"{agora:%d/%m/%Y %H:%M:%S}",
            "data_iso": agora.isoformat(),
            "remetente": remetente,
            "assunto": assunto,
            "total_fotos": len(nomes),
            "arquivos": nomes,
            "cenario": cenario,
            "resultados": resultados,
            "resumo": resumo,
            "acoes": acoes,
        }
        self.indice.append(registro)
        ARQ_INDICE.write_text(
            json.dumps(self.indice, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return registro
