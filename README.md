# AgroSmart — Monitoramento automatizado de frutas por e-mail

Produtores enviam fotos reais de frutas do campo por e-mail. O sistema detecta
os e-mails novos, **valida a entrada**, classifica cada fruta com um modelo de
visão computacional (**simulado** — ver nota Databricks), aplica regras de
decisão SE/ENTÃO, grava as fotos em uma pasta que **simula o banco de dados**
e dispara ações automáticas (alerta por e-mail, plano de controle, recomendação
de descarte).

## Arquitetura (origem → ingestão → processamento → ação)

```
 Produtor no campo               AgroSmart (Python)                         Ações
┌─────────────────┐  IMAP  ┌───────────────────────────┐  R1 ───► ┌──────────────────────────┐
│ E-mail c/ fotos │ ─────► │ MonitorEmail              │  R2 ───► │ Alerta de infestação     │
│ assunto FRUTAS  │ polling│  • UIDs novos + checkpoint│  R3 ───► │ Plano de controle (.txt) │
│ (+ "cenario: x" │  30 s  │  • extrai fotos           │  R4 ───► │ Descarte (.txt)          │
│  no corpo)      │        ├───────────────────────────┤          │ Alerta de talhão parado  │
└─────────────────┘        │ Validações V1 / V2        │          └──────────────────────────┘
        ▲                  ├───────────────────────────┤          ┌──────────────────────────┐
        │ aviso de         │ ClassificadorFrutas       │ ───────► │ banco_simulado/<lote>/   │
        │ reenvio          │ (Databricks SIMULADO)     │          │  + indice_lotes.json     │
        │                  ├───────────────────────────┤          └──────────────────────────┘
        └── inválido ──────┤ MotorRegras R1/R2/R3      │
                           │ Inatividade R4 (por tempo)│
                           └───────────────────────────┘
```

## Organização do código

| Arquivo             | Classe                    | Responsabilidade                                     |
|---------------------|---------------------------|------------------------------------------------------|
| `main.py`           | `AgroSmart`              | Ponto de entrada; orquestra o fluxo                  |
| `monitor.py`        | `MonitorEmail`            | IMAP, UIDs novos, checkpoint, fotos, cenário         |
| `classificador.py`  | `ClassificadorFrutas`     | Inferência (Databricks simulado), por cenário ou hash|
| `regras.py`         | `MotorRegras`             | Resumo do lote + regras R1, R2 e R3                  |
| `inatividade.py`    | `VerificadorInatividade`  | Regra R4 (remetente sem lote há mais de N dias)      |
| `acoes.py`          | `ExecutorAcoes`           | Executa as ações das regras R1–R3                    |
| `notificador.py`    | `Notificador`             | Respostas ao remetente e alertas por e-mail          |
| `armazenamento.py`  | `BancoSimulado`           | Fotos em pasta + índice de lotes (histórico)         |
| `enviar_lote.py`    | —                         | Producer: envia lotes de teste, com cenários         |
| `config.py`         | —                         | Parâmetros, limiares e caminhos                      |

## Validações de entrada

Lote inválido **não é gravado**: o remetente recebe um e-mail pedindo o
reenvio e o UID vai para o checkpoint (não é reprocessado).

| Código | Condição                       | Resposta ao remetente            |
|--------|--------------------------------|----------------------------------|
| V1     | e-mail **sem** foto anexada    | "não continha fotos anexadas"    |
| V2     | menos de 3 fotos (`MIN_FOTOS`) | "amostra insuficiente — reenvie" |

Mensagens automáticas (cabeçalho `Auto-Submitted`) são ignoradas, evitando loop.

## Regras de decisão (lógica booleana)

| Regra | Condição (SE)                                                                         | Ação (ENTÃO)                               |
|-------|---------------------------------------------------------------------------------------|--------------------------------------------|
| R1    | `pct_doentes > 30%` **E** `confianca_media > 70%`                                     | Alerta de infestação por e-mail (SMTP)     |
| R2    | mesma praga em **3 lotes seguidos** do mesmo remetente                                | Plano de controle (`relatorios/*.txt`)     |
| R3    | `pct_podres > 50%` **OU** (`pct_doentes > 30%` **E** `confianca_media > 90%`)         | Recomendação de descarte (`relatorios/*.txt`) |
| R4    | `agora − último lote do remetente > 3 dias` **E NÃO** (já alertado para esse lote)    | Alerta de monitoramento interrompido       |

Os limiares ficam em `config.py`. Com um lote por dia, a R2 equivale aos
"3 dias seguidos". O estado da R4 fica em `banco_simulado/estado_inatividade.json`.

## Simulação de decisões: cenários do producer

O classificador é simulado, então o producer controla o veredito do lote com
`--cenario`. O e-mail leva no corpo a linha `cenario: <nome>` e o classificador
devolve o resultado correspondente. Sem cenário, vale o sorteio por hash
(mesma foto = mesmo veredito).

| Cenário      | Lote simulado                                  | Regras que disparam     |
|--------------|------------------------------------------------|-------------------------|
| `saudavel`   | todas saudáveis, confiança 80–95%              | nenhuma                 |
| `infestacao` | ~40% doentes, confiança ~80%                   | R1                      |
| `incerto`    | ~40% doentes, mas confiança < 70%              | nenhuma (o **E** da R1 falha) |
| `critico`    | ~40% doentes, confiança > 90%                  | R1 e R3 (2º ramo do **OU**) |
| `descarte`   | ~70% podres, confiança ~80%                    | R1 e R3 (1º ramo do **OU**) |
| `praga`      | 1 fruta com cochonilha, confiança 80–90%       | R2 no **3º** lote seguido |

Observações: no cenário `praga`, use **4 ou mais fotos** — com 3 fotos, 1 praga
já são 33% de doentes e a R1 também dispara. Os cenários `incerto` e
`infestacao` têm o mesmo percentual de doentes e só mudam a confiança, o que
mostra a decisão do **E** da R1.

## Modelo de ingestão escolhido: micro-batch (e-mail/IMAP)

Cada e-mail é um micro-lote que chega de forma assíncrona. O monitor faz
polling a cada 30 s, busca apenas UIDs ainda não registrados no checkpoint
(`processed_uids.json`) e processa somente os registros novos — e-mails já
tratados **nunca** disparam as ações de novo, mesmo reiniciando o programa.

**Justificativa (latência de cada regra):** a R2 ("mesma praga em 3 lotes
seguidos") e a R4 (remetente parado há 3 dias) operam na escala de dias. A R1
e a R3 avaliam lotes fotográficos cuja coleta no campo já leva minutos, e a
decisão agronômica (inspecionar, descartar) é medida em horas — uma latência
de até 30 s é irrelevante. Um pipeline de streaming (Kafka) só se justificaria
com sensores enviando leituras a cada poucos segundos e exigindo reação em
tempo real (ex.: umidade crítica do solo); aqui adicionaria infraestrutura
(broker, tópicos, consumer groups) sem ganho prático. O e-mail ainda traz um
benefício operacional: o produtor no campo não precisa de nenhum sistema novo.

## Nota sobre o Databricks (simulação)

`ClassificadorFrutas` recebe as fotos reais, mas a inferência é simulada. Em
produção, `classificar_lote` faria uma chamada REST ao **Model Serving
endpoint** do Databricks:

```
POST https://<workspace>.cloud.databricks.com/serving-endpoints/frutas/invocations
Authorization: Bearer <token>
Body: {"inputs": [<imagem base64>]}
```

O formato de retorno (`classe`, `doenca`, `confianca` por foto) é o mesmo, então
o restante do pipeline não muda. O armazenamento também é simulado:
`BancoSimulado` grava cada lote em `banco_simulado/L<uid>/` e os metadados em
`indice_lotes.json`; em produção, iriam para um storage e uma tabela reais.

## Como executar

```bash
pip install -r requirements.txt
cp .env.example .env     # preencher EMAIL_USER e EMAIL_APP_PASSWORD (senha de app do Gmail)
```

1. Coloque pelo menos 4 fotos (jpg/png) na pasta `amostras/`.
2. Terminal 1: `python main.py` — monitor em execução contínua.
3. Terminal 2, um comando por teste:

| Comando                                      | O que demonstra                               |
|----------------------------------------------|-----------------------------------------------|
| `python enviar_lote.py --cenario saudavel`   | lote normal: grava no banco, nenhuma regra    |
| `python enviar_lote.py --cenario infestacao` | R1: alerta de infestação por e-mail           |
| `python enviar_lote.py --cenario incerto`    | confiança baixa: R1 **não** dispara           |
| `python enviar_lote.py --cenario critico`    | R1 + R3 (confiança muito alta)                |
| `python enviar_lote.py --cenario descarte`   | R1 + R3 (maioria podre)                       |
| `python enviar_lote.py --cenario praga`      | rode **3 vezes**: R2 gera o plano de controle |
| `python enviar_lote.py --sem-anexo`          | V1: aviso de "sem anexo"                      |
| `python enviar_lote.py foto1.jpg`            | V2: aviso de amostra insuficiente             |

`python enviar_lote.py --ajuda-cenarios` lista os cenários. Também dá para
simular pelo próprio Gmail (inclusive de outra conta, bom para o vídeo): escreva
`FRUTAS` no assunto, anexe as fotos e coloque `cenario: infestacao` no corpo.

Para testar a R4 sem esperar 3 dias, baixe `DIAS_SEM_LOTE` no `config.py`
(ex.: `0.001`, cerca de 1,5 min), envie um lote válido e aguarde.

## Roteiro de evidências (prints/log para a entrega)

1. Terminal com `main.py` rodando e mostrando "Nenhum e-mail novo".
2. Lote `saudavel`: classificação simulada no log, fotos gravadas em
   `banco_simulado/L<uid>/` e nenhuma regra disparando.
3. `infestacao`: log da R1 + e-mail de alerta recebido. `incerto`: mesma
   porcentagem de doentes, mas sem alerta (prova da lógica do **E**).
4. `descarte` ou `critico`: log da R3 + arquivo `relatorios/descarte_*.txt`.
5. `praga` ×3: log da R2 + `relatorios/plano_controle_*.txt`.
6. V1 e V2: log de rejeição + e-mail de aviso recebido.
7. R4: alerta de monitoramento interrompido.
8. Reinício do `main.py`: os mesmos UIDs aparecem como "já processados" e
   **não** disparam as ações de novo (prova do checkpoint).
