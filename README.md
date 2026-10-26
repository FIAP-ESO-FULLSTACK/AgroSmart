# AgroSmart — Sprint 3

Sistema de monitoramento de lavouras por e-mail: produtores enviam fotos das
plantas por e-mail, um modelo de visão computacional classifica cada foto
(saudável ou doente, e qual doença) e regras de decisão disparam respostas
automáticas — alerta de infestação, plano de controle ou confirmação de lote
saudável.

## Como funciona
1. **Ingestão (micro-batch)** — o monitor conecta na caixa de entrada via IMAP
   e, a cada 30 segundos, busca e-mails cujo assunto contém `Frutas para
   analise`. O arquivo `processados.txt` (checkpoint) guarda os UIDs já
   tratados: e-mail processado nunca dispara ação de novo, mesmo reiniciando o
   programa. Mensagens automáticas (cabeçalho `Auto-Submitted`) são ignoradas,
   o que impede loops de resposta.

2. **Classificação** — cada foto anexada passa pelo modelo pré-treinado
   [MobileNetV2 / PlantVillage](https://huggingface.co/linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification)
   (38 classes de doenças em 14 culturas), que roda localmente em CPU. Na
   primeira execução o modelo (~14 MB) é baixado do Hugging Face e fica em
   cache (`~/.cache/huggingface`) — as execuções seguintes funcionam offline.
   Predições com confiança abaixo de 60% são descartadas (foto ilegível).

3. **Regras de decisão** — aplicadas sobre o resumo do lote e o histórico:

   | Regra | SE | ENTÃO |
   |---|---|---|
   | R1 | nenhuma foto avaliada com confiança **E** o lote tem fotos | pedir reenvio com fotos melhores |
   | R2 | mais de 30% das fotos avaliadas doentes | alerta de infestação |
   | R3 | mesma doença predominante nos últimos 3 lotes do remetente | acionar plano de controle |
   | R4 | nenhuma doente **E** nenhuma descartada | confirmar lote saudável |

   (Um e-mail sem anexo nenhum é rejeitado antes da classificação, com aviso
   ao remetente.) Os limiares (60%, 30%, 3 lotes) são parâmetros em
   `src/agrosmart/config.py`.

4. **Ações** — cada regra disparada gera um e-mail automático em HTML,
   respondido **na mesma conversa** do lote (threading). O histórico de lotes
   fica em `historico.jsonl` (um JSON por linha) — é a memória que permite à
   R3 enxergar recorrência.

## Como iniciar

Requisitos: Python 3.12+ e [uv](https://docs.astral.sh/uv/). Primeira execução
precisa de internet (download do modelo).

```powershell
# 1. Instalar dependências (cria a .venv automaticamente)
uv sync

# 2. Configurar credenciais
copy .env.example .env    # e preencher (Gmail: usar senha de app)

# 3. Iniciar o monitor
uv run agrosmart
```

Para simular a chegada de dados (em outro terminal):

```powershell
uv run python scripts/enviar_lote.py --listar          # cenários disponíveis
uv run python scripts/enviar_lote.py sarna_da_maca     # lote doente → alerta
uv run python scripts/enviar_lote.py saudaveis 3       # lote saudável → confirmação
uv run python scripts/enviar_lote.py sem_anexo         # sem fotos → rejeição
```

O gerador envia e-mails reais (com fotos de `amostras/`) para a própria caixa
monitorada; o monitor os capta no ciclo seguinte e responde.

## Como funcionaria em produção

**Vários produtores, caixas independentes.** Cada produtor envia de seu
próprio e-mail. O histórico é registrado **por remetente**, então a regra de
recorrência (R3) conta os lotes de cada produtor separadamente: três lotes
seguidos de sarna do João disparam o plano de controle para o João, sem
interferência dos lotes da Maria.

**Latência.** Com polling de 30s e ~1s de classificação por foto, um alerta
chega em menos de 1 minuto após o envio do lote. Essa é a razão do modelo de
ingestão **micro-batch**: nenhuma das regras exige tempo real — a R3 opera em
escala de dias, e mesmo o alerta de infestação (R2) é acionável em minutos.
Um fluxo streaming (Kafka) só se justificaria com sensores contínuos e regras
de latência crítica (ex.: umidade do solo), o que não é o caso.

**Roteamento das mensagens.** O remetente do lote sempre recebe a resposta na
própria conversa (confirmação, pedido de reenvio ou alerta). Alertas (R2/R3)
são **adicionalmente** comunicados ao e-mail configurado em `EMAIL_ALERTAS`
(ex.: o agrônomo responsável), identificando qual produtor enviou o lote. Se
`EMAIL_ALERTAS` não estiver configurado, o sistema avisa no log e o alerta
segue apenas para o remetente — nunca se perde.

**Resiliência.** Se a conexão IMAP cair, o monitor reconecta no ciclo
seguinte; se o processo for reiniciado, o checkpoint garante que nada é
reprocessado e nenhum e-mail pendente é perdido (o UID só entra no checkpoint
após o tratamento completo).
