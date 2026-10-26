"""AgroSmart — monitor de e-mails de análise de frutas.

Fluxo: e-mail novo com assunto-filtro → fotos classificadas pelo modelo →
resumo do lote → regras de decisão → ações (e-mails automáticos) →
histórico + checkpoint.

Uso: uv run agrosmart
"""
import time
from datetime import datetime

from agrosmart.classificador import Classificador
from agrosmart.config import ASSUNTO_FILTRO, EMAIL_ALERTAS, INTERVALO_POLLING
from agrosmart.servico_email import ServicoEmail


def ciclo(servico: ServicoEmail, classificador: Classificador) -> int:
    """Processa os e-mails novos de uma checagem. Retorna quantos tratou."""
    novos = servico.buscar_novos()
    for uid, msg in novos:
        remetente, assunto = servico.resumo(msg)
        print(f"[{datetime.now():%H:%M:%S}] UID {uid} | {remetente} | {assunto}")

        if servico.eh_automatico(msg):
            print("  Mensagem automática — ignorada.")
            servico.marcar_processado(uid)
            continue

        fotos = servico.extrair_fotos(msg)
        if not fotos:
            print("  Sem fotos em anexo — avisando o remetente.")
            servico.avisar_sem_anexo(remetente, assunto, em_resposta_a=msg)
            servico.marcar_processado(uid)
            continue

        # Classificação de cada foto do lote
        resultados = []
        for nome, conteudo in fotos:
            r = classificador.classificar(conteudo)
            resultados.append(r)
            print(f"  {nome}: {r['classe']} (confiança {r['confianca']:.0%})")

        # Análise do lote: resumo + regras de decisão + histórico
        analise = classificador.analisar_lote(remetente, resultados)
        resumo = analise["resumo"]
        print(
            f"  Lote: {resumo['doentes']}/{resumo['avaliadas']} doente(s), "
            f"{resumo['descartadas']} descartada(s) por baixa confiança"
        )

        if not analise["acoes"]:
            print("  Nenhuma regra disparou.")
        for acao in analise["acoes"]:
            print(f"  [{acao['regra']}] {acao['motivo']} -> e-mail: {acao['assunto']}")
            servico.notificar(
                remetente, acao["assunto"], acao["corpo"],
                em_resposta_a=msg, nivel=acao["nivel"],
            )
            # Alertas (R2/R3) também são comunicados ao responsável configurado
            if acao["nivel"] == "alerta":
                if not EMAIL_ALERTAS:
                    print("  [AVISO] EMAIL_ALERTAS não configurado no .env — "
                          "alerta enviado apenas ao remetente do lote.")
                elif EMAIL_ALERTAS.lower() != remetente.lower():
                    corpo = f"Lote enviado por: {remetente}\n\n{acao['corpo']}"
                    servico.notificar(EMAIL_ALERTAS, acao["assunto"], corpo, nivel="alerta")
                    print(f"  alerta também comunicado a {EMAIL_ALERTAS}")

        servico.marcar_processado(uid)
    return len(novos)


def main() -> None:
    print(f"AgroSmart — aguardando e-mails com assunto '{ASSUNTO_FILTRO}'")
    print(f"Checando a cada {INTERVALO_POLLING}s (Ctrl+C para parar)")
    print("Carregando modelo de classificação...")
    classificador = Classificador()
    print("Modelo pronto.\n")

    servico = ServicoEmail()
    servico.conectar()
    try:
        while True:
            try:
                if ciclo(servico, classificador) == 0:
                    print(f"[{datetime.now():%H:%M:%S}] nada novo")
            except Exception as exc:
                print(f"[ERRO] {exc} — reconectando no próximo ciclo")
                servico.desconectar()
                servico.conectar()
            time.sleep(INTERVALO_POLLING)
    except KeyboardInterrupt:
        print("\nEncerrado.")
        servico.desconectar()
