# Dicionário de dados — AgroSmart

## Evento de entrada (e-mail de lote)

| Campo     | Tipo   | Unidade/Domínio                    | Descrição                                      | Exemplo                        |
|-----------|--------|------------------------------------|------------------------------------------------|--------------------------------|
| uid       | string | UID IMAP (inteiro sequencial)      | Identificador único do e-mail na caixa         | "4821"                         |
| remetente | string | e-mail válido                      | Quem enviou o lote                             | "produtor@fazenda.com"         |
| assunto   | string | contém "FRUTAS"                    | Filtro de ingestão                             | "FRUTAS - lote 22/10 14:05"    |
| fotos     | lista  | imagens JPEG/PNG, mínimo 3         | Fotos das frutas do talhão                     | ["f1.jpg", "f2.jpg", "f3.jpg"] |
| cenario   | string | ver cenários do README (opcional)  | Linha `cenario: <nome>` no corpo; só para simulação | "infestacao"              |

## Validações de entrada

| Código | Condição                        | Resultado                            |
|--------|---------------------------------|--------------------------------------|
| V1     | nenhuma foto anexada            | aviso ao remetente; lote não gravado |
| V2     | menos de 3 fotos                | aviso ao remetente; lote não gravado |
| —      | cabeçalho `Auto-Submitted` ≠ no | ignorado (evita loop de respostas)   |

## Resultado da classificação (por foto — saída do modelo simulado)

| Campo     | Tipo        | Unidade/Domínio                          | Descrição                    | Exemplo                 |
|-----------|-------------|------------------------------------------|------------------------------|-------------------------|
| arquivo   | string      | nome de arquivo                          | Foto classificada            | "f1.jpg"                |
| classe    | string      | saudavel \| podre \| praga               | Veredito do modelo           | "podre"                 |
| doenca    | string/null | antracnose, cochonilha, ... \| null      | Diagnóstico quando doente    | "antracnose"            |
| confianca | float       | 0.0 – 1.0                                | Confiança da predição        | 0.87                    |

## Resumo do lote (entrada das regras)

| Campo             | Tipo       | Unidade/Domínio | Descrição                          | Exemplo        |
|-------------------|------------|-----------------|------------------------------------|----------------|
| total             | int        | ≥ 3             | Fotos no lote                      | 5              |
| pct_doentes       | float      | 0.0 – 1.0       | Proporção classe ≠ saudavel        | 0.40           |
| pct_podres        | float      | 0.0 – 1.0       | Proporção classe = podre           | 0.40           |
| confianca_media   | float      | 0.0 – 1.0       | Média das confianças               | 0.81           |
| pragas_detectadas | lista[str] | nomes de praga  | Pragas distintas no lote           | ["cochonilha"] |

## Registro de ação (saída das regras R1–R3)

| Campo  | Tipo   | Domínio                                    | Descrição                  | Exemplo                                          |
|--------|--------|--------------------------------------------|----------------------------|--------------------------------------------------|
| regra  | string | R1 \| R2 \| R3                             | Regra que disparou         | "R1"                                             |
| acao   | string | alerta_email \| plano_controle \| descarte | Ação executada             | "alerta_email"                                   |
| motivo | string | texto livre                                | Explicação auditável       | "40% de frutas doentes (> 30%) com confiança ..."|
| praga  | string | só na R2                                   | Praga que originou o plano | "cochonilha"                                     |

A R4 não grava ação no lote: seu estado ("já alertado") fica em
`banco_simulado/estado_inatividade.json` (`{remetente: data_iso do último lote alertado}`).

## Registro do lote (`banco_simulado/indice_lotes.json`)

| Campo       | Tipo        | Descrição                                                  |
|-------------|-------------|------------------------------------------------------------|
| lote_id     | string      | "L" + UID; também o nome da pasta do lote                  |
| data        | string      | dd/mm/aaaa hh:mm:ss (legível)                              |
| data_iso    | string      | ISO 8601 (usado pela R4)                                   |
| remetente   | string      | Quem enviou                                                |
| assunto     | string      | Assunto do e-mail original                                 |
| total_fotos | int         | Fotos gravadas                                             |
| arquivos    | lista[str]  | Fotos em `banco_simulado/<lote_id>/`                       |
| cenario     | string/null | Cenário usado na simulação (null = sorteio por hash)       |
| resultados  | lista       | Classificação por foto (tabela acima)                      |
| resumo      | objeto      | Resumo do lote (tabela acima)                              |
| acoes       | lista       | Ações disparadas pelas regras (tabela acima)               |

## Exemplo de um registro completo

```json
{
  "lote_id": "L4821",
  "data": "22/10/2026 14:05:43",
  "data_iso": "2026-10-22T14:05:43.120345",
  "remetente": "produtor@fazenda.com",
  "assunto": "FRUTAS - lote 22/10 14:05",
  "total_fotos": 5,
  "arquivos": ["f1.jpg", "f2.jpg", "f3.jpg", "f4.jpg", "f5.jpg"],
  "cenario": "infestacao",
  "resultados": [
    {"arquivo": "f1.jpg", "classe": "podre", "doenca": "antracnose", "confianca": 0.84},
    {"arquivo": "f2.jpg", "classe": "podre", "doenca": "fungo-botrytis", "confianca": 0.79},
    {"arquivo": "f3.jpg", "classe": "saudavel", "doenca": null, "confianca": 0.83},
    {"arquivo": "f4.jpg", "classe": "saudavel", "doenca": null, "confianca": 0.78},
    {"arquivo": "f5.jpg", "classe": "saudavel", "doenca": null, "confianca": 0.81}
  ],
  "resumo": {
    "total": 5, "pct_doentes": 0.4, "pct_podres": 0.4,
    "confianca_media": 0.81, "pragas_detectadas": []
  },
  "acoes": [
    {"regra": "R1", "acao": "alerta_email",
     "motivo": "40% de frutas doentes (> 30%) com confiança média 81% (> 70%)"}
  ]
}
```
