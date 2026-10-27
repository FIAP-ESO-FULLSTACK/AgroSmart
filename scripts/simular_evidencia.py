"""Executa as regras e o checkpoint sem acessar IMAP ou SMTP.

Uso:
    uv run python scripts/simular_evidencia.py
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import agrosmart.classificador as classificador_mod
import agrosmart.servico_email as email_mod
from agrosmart.classificador import Classificador
from agrosmart.servico_email import ServicoEmail


EVENTOS = [
    ("1842", "produtor@exemplo.com", "Apple Scab", False, 5),
    ("1843", "produtor@exemplo.com", "Apple Scab", False, 5),
    ("1844", "produtor@exemplo.com", "Apple Scab", False, 5),
    ("1845", "produtor2@exemplo.com", "Healthy Apple Plant", True, 3),
]


def executar() -> None:
    print("COMANDO: uv run python scripts/simular_evidencia.py")

    with TemporaryDirectory() as pasta:
        raiz = Path(pasta)
        classificador_mod.ARQUIVO_HISTORICO = str(raiz / "historico.jsonl")
        email_mod.ARQUIVO_CHECKPOINT = str(raiz / "processados.txt")
        classificador = object.__new__(Classificador)

        print("\nPRIMEIRA VARREDURA")
        for uid, remetente, classe, saudavel, quantidade in EVENTOS:
            if uid in ServicoEmail._carregar_processados():
                print(f"UID {uid} ignorado | já está no checkpoint")
                continue

            resultados = [
                {"classe": classe, "saudavel": saudavel, "confianca": 0.97}
                for _ in range(quantidade)
            ]
            analise = classificador.analisar_lote(remetente, resultados)
            resumo = analise["resumo"]
            regras = ", ".join(acao["regra"] for acao in analise["acoes"])

            print(f"UID {uid} | {remetente} | {classe}")
            print(
                f"RESULTADO: {resumo['doentes']}/{resumo['avaliadas']} doentes | "
                f"predominante: {resumo['doenca_predominante'] or 'nenhuma'}"
            )
            print(f"AÇÕES: {regras}")
            for acao in analise["acoes"]:
                print(f"AÇÃO SIMULADA (e-mail): {acao['assunto']}")

            ServicoEmail.marcar_processado(uid)
            print(f"CHECKPOINT: UID {uid} salvo")

        print("\nSEGUNDA VARREDURA")
        for uid, *_ in EVENTOS:
            if uid in ServicoEmail._carregar_processados():
                print(f"UID {uid} ignorado | já está no checkpoint")

        print("CONCLUSÃO: nenhuma ação duplicada após checkpoint")


if __name__ == "__main__":
    executar()
