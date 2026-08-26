# Harness de verificação do portal (`portal_jem_marketing_daily.*`)

Valida a versão-portal do dashboard **sem precisar publicar no portal**. Serve para reconferir tudo
depois de qualquer mexida no `.md` ou no `.html`.

O ponto importante: o `run_manifest.py` **extrai os blocos ` ```mysql ` do próprio manifesto** e roda
contra o Magento ao vivo. Então o que é testado é literalmente o que está no `.md` — se alguém editar
uma query e quebrar, o teste acusa.

## Como rodar (nesta pasta)

```bash
# 1. roda as queries do manifesto contra o Magento, escreve site/data/*.json,
#    e sincroniza site/index.html com o portal_jem_marketing_daily.html atual
python run_manifest.py

# 2. puxa a view real do ClickUp + injeta as fixtures compactas, e reconcilia 27/07
python make_fixtures.py

# 3. roda o <script> da própria página sob um DOM stub e faz as asserções
node test_portal.mjs
```

`python` puro funciona desde 29/07 (o PATH foi corrigido — ver `../CLAUDE.md` §5). Se der
"Python was not found", o terminal foi aberto **antes** da correção: feche e reabra, ou use
`C:/Users/MaynaraAmaral/anaconda3/python.exe` no lugar.

## O que cada arquivo faz

| Arquivo | Papel |
|---|---|
| `run_manifest.py` | Extrai os ` ```mysql ` do `.md`, roda no Magento, escreve `site/data/*.json` no mesmo formato que o portal serviria (decimais e datas como **string**, como o MySQL devolve). Também lista os blocos ` ```rest ` pra inspeção. |
| `make_fixtures.py` | Reconcilia 27/07 do jeito que o `compute()` da página faz e escreve as **3 fixtures do ClickUp** (`clickup_board_pg0/pg1.json` + `clickup_concluidas.json`), reproduzindo **exatamente as 3 requisições** que o portal faz — se aqui virasse uma varredura completa da view, o teste passaria num dado que o portal nunca recebe. Com retry/backoff. |
| `clickup_mcp_pull.json` | Amostra de tarefas (pull via MCP, 2026-07-28), usada só como **fallback** se não houver `CLICKUP_TOKEN` ou a API estiver fora. |
| `test_portal.mjs` | Extrai o `<script>` do `.html`, roda sob um DOM/fetch stub mínimo no Node e faz as asserções. |

**O dataset mistura os dois formatos de payload de propósito**, porque as duas formas existem no
mundo real: as ~169 tarefas da view vêm no formato **REST v2 cru** (`status` como objeto, com
`date_updated`/`date_done` — é o que o portal recebe), e o `make_fixtures.py` acrescenta 3 linhas no
formato **compacto** (`status` como string, sem `date_updated` — é o que as ferramentas MCP
devolvem). Duas dessas 3 são casos-limite deliberados: uma com `backlog` (tem que ficar fora do
quadro) e uma com status inexistente no mapa (tem que virar **aviso** no rodapé, nunca desaparecer
calada).

⚠ **A API do ClickUp dá timeout esporádico** nesse endpoint — uma passada inteira funciona e a
seguinte estoura. O `get_page()` tem retry com backoff por isso; se ainda assim falhar, o script cai
no fallback e **avisa na saída** (confira a linha "fonte:"). Fallback = payload todo em formato
string, então o caminho do payload real não é exercitado.

## Baseline esperado: 132 asserções, 0 falhas

A âncora de reconciliação é o **"Report 27 de Julho"** — é data passada, então esses números **não
mudam** e são o que de fato prova a correção:

- pedidos no dia **32**, pedidos no mês **449**
- pedido destaque **$6.392,75 · #JEMUS000002914 · Briscoe Protective - Pye-Barker NY**
- companies com 1ª compra **415** (acumulado até 27/07) · novos contatos no dia **7**

⚠ **O banco é vivo:** contagem de pedidos, totais de companies/contacts e `db_today` sobem todo dia
(em 28/07 eram 3.004 / 2.993 / 12.036; um dia depois já eram 3.010+ / 2.997 / 12.056). O teste foi
escrito pra isso: nesses casos ele afere **relações e pisos** (`period.max === db_today`, totais
`>=` a referência) e imprime o valor real, em vez de fixar literais que apodrecem em 24h. Se você
mexer no teste, mantenha essa distinção — literal só pra data passada.

**O mesmo vale para o quadro do ClickUp**, que muda conforme o time trabalha. Por isso o teste não
afere contagem por coluna, e sim **conservação**: `cartões no quadro + não mapeadas + backlog +
concluídas além do top-10 == total de tarefas`. Se alguma tarefa sumir por um bug de mapeamento, essa
soma não fecha. Em 29/07 a view dava 47 cartões no quadro (33 · 1 · 2 · 1 · 10) de 169 tarefas.

Também cobre os caminhos de erro, que é onde dashboard costuma mentir: ClickUp fora → caixa
explicativa + pílula vermelha e **o Magento continua renderizando**; Magento fora → os dois tiles de
dados degradam e **o ClickUp continua**.

`site/` é gerado (≈470 KB de JSON) — pode apagar à vontade, o passo 1 recria.
