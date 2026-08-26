# JEM Marketing Daily Report

Snapshot diário do site + pipeline de desenvolvimento para o time de marketing: KPIs de
cadastro/vendas do **Magento** (Companies, Contacts, pedidos e faturamento do dia/mês/ano, pedido
destaque, tendência de 6 meses) e o quadro de tarefas do **ClickUp**, espelhando a view "Board" do
go-live.

Três datasets **compartilhados** de Magento (MySQL, mesma visão para todos) + um dataset **REST** do
ClickUp. Todo KPI, gráfico e coluna do kanban é calculado **no navegador** a partir dessas linhas
cruas — é isso que faz o seletor de dia (Hoje / Ontem / calendário) recalcular a metade de cima na
hora, sem nova consulta.

**`credentials: shared`** marca o dashboard como recurso de **equipe**: um único token do ClickUp
cadastrado no portal serve todo o time de marketing, em vez de cada pessoa cadastrar a própria.
Independente disso, **um token precisa ser cadastrado uma vez** — o manifesto não pode carregar
chave, então o portal sempre pede na primeira vez.

---

## Dataset: `mkt_orders`

Uma linha por pedido JEM do ano (≈3.000 linhas). Alimenta pedidos e faturamento do dia / mês /
desde janeiro, o pedido destaque, "Companies com 1ª compra" e os dois gráficos de 6 meses.

`amount` é **faturamento = `subtotal + discount_amount`** — valor de venda puro, líquido de
desconto, **excluindo frete e imposto** (`discount_amount` já é gravado negativo no Magento, então
a soma simples já abate o desconto). `grand_total` **não** é usado: ele mistura frete e imposto,
que não são valor de venda.

`company_id` / `company_name` saem da tabela de **membros** (`amasty_company_account_customer`), e
não de `amasty_company_account_company.super_user_id` — o super_user é só o admin da empresa, então
um pedido feito por qualquer outro funcionário não resolveria empresa nenhuma. O join é seguro: **nenhum
cliente está ligado a mais de uma empresa** (verificado — 0 casos), então ele não duplica linhas de
pedido (32 pedidos em 27/07 = 32 linhas, com e sem o join).

```mysql name=mkt_orders connector=magento
SELECT
    so.increment_id                                  AS increment_id,
    DATE_FORMAT(so.created_at, '%Y-%m-%d %H:%i:%s')  AS created_at,
    ROUND(so.subtotal + so.discount_amount, 2)       AS amount,
    link.company_id                                  AS company_id,
    acc.company_name                                 AS company_name
FROM sales_order so
LEFT JOIN amasty_company_account_customer link ON link.customer_id = so.customer_id
LEFT JOIN amasty_company_account_company  acc  ON acc.company_id  = link.company_id
WHERE so.created_at >= '2026-01-01'
  AND so.increment_id LIKE '%JEM%'
ORDER BY so.created_at
```

## Dataset: `mkt_totais`

Uma única linha com os totais que não têm recorte por dia (Companies, Contacts) e o **relógio do
banco**, usado para definir o que é "hoje" no seletor de dia.

```mysql name=mkt_totais connector=magento
SELECT
    (SELECT COUNT(*) FROM amasty_company_account_company) AS companies_total,
    (SELECT COUNT(*) FROM customer_entity)                AS contacts_total,
    DATE_FORMAT(CURDATE(), '%Y-%m-%d')                    AS db_today,
    DATE_FORMAT(NOW(), '%Y-%m-%d %H:%i:%s')               AS db_now
```

## Dataset: `mkt_novos_contatos`

Contas de cliente criadas **por dia** no ano corrente (≈156 linhas — só dias com criação), de
`customer_entity.created_at`.
Alimenta o chip "novos no dia" do cartão Contacts, para **qualquer** dia do seletor.

```mysql name=mkt_novos_contatos connector=magento
SELECT
    DATE_FORMAT(created_at, '%Y-%m-%d') AS dia,
    COUNT(*)                            AS novos
FROM customer_entity
WHERE created_at >= '2026-01-01'
GROUP BY DATE_FORMAT(created_at, '%Y-%m-%d')
ORDER BY dia
```

## Dataset: `clickup_golive_board`

**A view "Board" do go-live**, exatamente a que o time usa:
<https://app.clickup.com/31082060/v/b/6-901112863157-2>. Um único dataset alimenta as 5 colunas.

Antes eram duas consultas às listas inteiras (Incident Support | Go-Live + Hyvä Backlog) e o
critério de "quais tarefas entram" era **meu**. Agora é o do time: a curadoria vive na view, e o
dashboard só obedece. Foi o que reduziu o quadro de ~46 tarefas ativas para **36** — o excesso vinha
de puxar a Hyvä Backlog inteira.

Verificado ao vivo em 29/07 (`probe_clickup_view.py`):

- O id do navegador (`6-901112863157-2`) **entra literal na API** — é uma *required view* de tipo
  `board`, não precisa tradução.
- A view **não tem filtro de campo** (`filters.fields: []`), agrupa por `status` e traz **169
  tarefas**: 36 ativas + 133 `Closed`.
- Ela **não esconde nada** da lista Incident Support (65 tarefas, 0 escondidas) — ela **soma**
  tarefas de outras listas que o time adicionou ao board: aparecem **Hyvä Backlog** e
  **Sprint 16**. Ou seja, a Bulk Pack do report de referência **continua no quadro**.
- Não devolve subtarefa nenhuma (0 com `parent`), então não há o risco que o parâmetro `subtasks`
  criava.
- O payload é o **REST v2 cru**: `status` como objeto, com `date_updated` e `date_done`.
- Funciona **sem** o parâmetro `page` (devolve a página 0), 30 tarefas por página.

### Três requisições em vez de sete (29/07/2026)

A versão anterior era **um** dataset com `paginate: true`, o que dá **7 requisições** (6 páginas de
30 + a página vazia que encerra). Esse endpoint tem lentidão intermitente, e cada requisição é uma
chance de estourar o tempo — foi assim que o tile caiu em produção
(*"The operation was aborted due to timeout"*). Agora são **3 requisições**, medidas em ~3,5s.

O que tornou isso possível, tudo verificado ao vivo em 29/07:

- **A view devolve as ativas ANTES das concluídas** (ela agrupa por `status`, e os status de
  conclusão são os últimos do fluxo). Medido: página 0 = 30 ativas / 0 concluídas; página 1 = 6
  ativas / 24 concluídas; páginas 2–5 = só concluídas. As **36 ativas ocupam os itens 0–35**, ou
  seja **2 páginas bastam** para as colunas 1–4, com folga de 24 itens.
- **A ordem das concluídas é arbitrária** (133 concluídas, 84 quebras de ordem por data): ler 2
  páginas pegaria conclusões de abril/junho e **perderia todas as 10 mais recentes**. Por isso a
  coluna 5 tem dataset próprio.
- **`locations` diz a que listas a tarefa pertence**, então "está no board?" é decidível sem ler a
  view inteira: `list.id == 901112863157` **ou** `locations[]` contém `901112863157`. Regra
  conferida contra a view: **94/94 e 100/100 acertos**.
- O endpoint da view **ignora todo parâmetro** menos `page` (testados `per_page`, `limit`,
  `page_size`, `pageSize`, `count`, `size`, `include_closed`, `show_closed`, `archived`,
  `statuses[]`, `order_by`, `reverse` — todos devolveram exatamente a mesma página). Não existe
  página maior que 30 aqui.
- O endpoint de equipe **não** substitui a view: filtrado por `list_ids[]` ele traz só a lista-mãe
  (65 de 169 tarefas), e sem filtro de data estoura no próprio ClickUp (HTTP 500 após 55s).

⚠ **`paginate: false` é essencial nos dois primeiros datasets** — é ele que faz cada um ser **uma**
requisição na página fixa. **Como conferir na primeira publicação:** a pílula de origem no cabeçalho
mostra a contagem de linhas. Tem de aparecer **30 e 30**; se aparecer 169 em algum dos dois, a
plataforma ignorou o `paginate: false` e o certo é voltar ao dataset único com `paginate: true`.

```rest
name: clickup_board_pg0
connector: clickup
method: GET
path: /view/6-901112863157-2/task
query: { page: 0 }
select: tasks
paginate: false
credentials: shared
```

```rest
name: clickup_board_pg1
connector: clickup
method: GET
path: /view/6-901112863157-2/task
query: { page: 1 }
select: tasks
paginate: false
credentials: shared
```

Coluna 5 numa requisição: tarefas **concluídas** das listas que alimentam o board, atualizadas nos
últimos 60 dias. Medido: **64 itens, `last_page: true`, ~1,0s**, e o top 10 resultante é
**idêntico** ao que sai da view inteira. A janela de 60 dias existe para caber em **uma** página de
100: sem ela vêm 100 itens com `last_page: false` (truncado, e aí faltam 3 do top 10).

```rest
name: clickup_concluidas
connector: clickup
method: GET
path: /team/31082060/task
query: { list_ids[]: ["901112863157", "901110423629", "901113068292"], statuses[]: ["Closed", "approved by qa - prd"], include_closed: true, date_updated_gt: 60d }
select: tasks
paginate: false
credentials: shared
```

⚠ **`date_updated_gt: 60d`** — se a plataforma não resolver esse atalho para epoch em ms, troque por
um valor absoluto (ex.: `1782500000000`) e reveja a cada tanto; o dashboard **avisa na tela** se essa
consulta voltar truncada (≥100 linhas) ou com menos de 10 conclusões.

⚠ **Esta é a única peça do desenho que depende de algo não verificado: a plataforma precisa
serializar `list_ids[]` e `statuses[]` como parâmetro REPETIDO** (`list_ids[]=a&list_ids[]=b`).
Testado na API em 29/07: a forma com vírgula (`list_ids=a,b`) devolve **HTTP 400** — não é opção.
Se a plataforma não conseguir, este dataset falha e **só a coluna 5 fica vazia**, com o motivo
escrito no rodapé do tile; as outras quatro colunas não dependem dele. Nesse caso, duas saídas:

1. tentar a query como string única — `query: "list_ids[]=901112863157&list_ids[]=901110423629&list_ids[]=901113068292&statuses[]=Closed&statuses[]=approved%20by%20qa%20-%20prd&include_closed=true"`;
2. trocar por este bloco, que **não usa array nenhum** (indentado de propósito, para ativar basta
   virar bloco `rest` e renomear o dataset para `clickup_concluidas`):

       name: clickup_concluidas
       connector: clickup
       method: GET
       path: /list/901112863157/task
       query: { include_closed: true, page: 0 }
       select: tasks
       paginate: false
       credentials: shared

   **Custo declarado:** essa consulta traz só as tarefas cuja lista-mãe é a do go-live (65 tarefas,
   1 página, ~1,4s, **zero** tarefa fora do board). A coluna 5 passa a ignorar as conclusões de
   tarefas que o time trouxe de outras listas — em 29/07 isso seria **6 das 10** conclusões mais
   recentes em vez de 10 (4 vinham da Hyvä Backlog). Nenhum cartão falso; cobertura menor.

⚠ **Os três `list_ids` estão fixos no manifesto.** Se o time adicionar ao board uma tarefa de uma
**quarta** lista, as conclusões dela não entram nesta consulta. Isso é **detectado**: as páginas 0–1
revelam de quais listas o board é composto, e o dashboard compara com a lista fixa e avisa no rodapé
qual lista ficou fora. Falha visível em vez de coluna silenciosamente incompleta.

⚠ **A coluna "Conclusões mais recentes (PRD)" mostra o que o board esconde.** A view tem
`show_closed: false`, então na tela do ClickUp as 133 fechadas não aparecem — mas o endpoint
`/view/{id}/task` **ignora esse ajuste** e as devolve. É uma divergência deliberada: o quadro segue
a view nas 4 colunas ativas, e a 5ª usa as fechadas que vêm de brinde (decisão da Maynara: manter a
coluna de conclusões). Não precisou de consulta separada à lista.

---

## Escopo e fórmulas

- **Escopo de pedidos = `increment_id LIKE '%JEM%'`**, sem filtro de status. Os pedidos numerados
  "SO######" (outro canal) ficam fora. Conferido contra o report manual de 27/07: pedidos no dia
  32≡32, pedidos no mês 449≡449, pedido destaque `$6.392,75 · JEMUS000002914 · Briscoe Protective -
  Pye-Barker NY`. Excluir `canceled`/`closed` **piorava** a conciliação, por isso não se exclui.
- **Faturamento** = `subtotal + discount_amount` (ver `mkt_orders`). Nunca `grand_total`.
- **Companies com 1ª compra** = `COUNT(DISTINCT company_id)` entre os pedidos até o dia
  selecionado — calculado no navegador, portanto correto para qualquer dia do seletor. Referência
  de validação: 416 empresas distintas no acumulado do ano (≈13,9% de 2.993).
- **Pedido destaque** = maior `amount` do dia, com o nome da empresa já resolvido no SQL.
- **Gráficos de 6 meses** = 6 meses terminando no mês do dia selecionado, agregados das mesmas
  linhas de `mkt_orders` (escolher uma data passada re-ancora os gráficos, não só os KPIs).

## Colunas do kanban (status reais do ClickUp)

**Quem entra no quadro é a view** (ver o dataset acima). O mapa abaixo só decide **em qual coluna**
cada tarefa cai, agrupando os 15 status da lista nas 5 etapas do report — é a mesma numeração 1→5 do
report manual. `backlog` fica fora por segurança (não iniciado ≠ pipeline ativo), embora a view não
devolva nenhuma hoje. Status fora do mapa são contados num rodapé de aviso, para que um status novo
criado no ClickUp apareça como alerta em vez de desaparecer em silêncio.

| Nº | Coluna | Status ClickUp | Na view em 29/07 |
|---|---|---|---|
| 1 | Em andamento | researching · to do (sprint) · doing · on hold · blocked · code review - stg | **32** |
| 2 | Prontas para validação (STG) | ready for testing - stg · testing - stg · fail - stg | **1** |
| 3 | Tarefas aguardando Deploy | ready to deploy | **2** |
| 4 | Tarefas prontas para validação (PRD) | ready for testing - prd · testing - prd · fail - prd | **1** |
| 5 | Conclusões mais recentes (PRD) | approved by qa - prd · Closed — **top 10** por data | 133 → 10 |

Data de conclusão = `date_closed` (status tipo *closed*) ou `date_done` (`approved by qa - prd`, que
é tipo *done* e não preenche `date_closed`). Ambos vêm no próprio payload — sem chamada extra.

### Filtro de status (múltipla escolha)

Botão **"Status: …"** numa barra própria **dentro do tile do quadro** (destacada em teal, centralizada
— mesma barra da versão local desde 29/07). Fica ali, e não na barra de filtros do topo, porque a
barra do topo é o seletor de dia da metade Magento; um filtro de status lá daria a entender que afeta
os KPIs também.

Na mesma barra, onde a versão local tem o **seletor de data do quadro**, aqui há uma etiqueta fixa
**"estado atual · sem histórico por dia"** — o motivo está em "Preservar o log do dia anterior",
abaixo. Etiqueta em vez de seletor desabilitado: desabilitado sugere que um dia funciona sozinho, e
um seletor que filtrasse por `date_updated` faria o quadro parecer histórico sem ser.

Cada cartão mostra o **status** no rodapé, com a bolinha na cor do próprio ClickUp — é por ele que
este filtro recorta, e filtro cujo critério não aparece no cartão obriga a adivinhar por que a tarefa
está ali. A lista de origem virou tooltip do título.

- As opções saem dos status **que realmente aparecem no payload**, com a contagem de cada um, e vêm
  agrupadas pelas 5 colunas. Não é lista fixa: um status novo criado no ClickUp aparece
  automaticamente, e status que nunca ocorrem não poluem a lista.
- `backlog` e status fora do mapa também aparecem, num grupo **"Fora do quadro"** — dá para inspecioná-los
  sem que eles entrem no quadro por acidente.
- Com filtro ativo, o rodapé declara **quantas tarefas foram escondidas** e diz que o quadro não é o
  total. Quadro filtrado que parece completo é dashboard que mente.
- Marcar todos à mão equivale a "todos" (o botão volta ao estado neutro, sem borda de destaque).
- O "dia mais recente" do ponto verde é calculado sobre o conjunto **completo**, de propósito: ele
  não deve mudar porque alguém escondeu um status.
- Sem `localStorage` (iframe sandbox), a escolha **vale para a sessão**.

## Diferenças conscientes vs. a versão local (`dashboard.html`)

Três coisas da versão local **não são reproduzíveis no portal**, e estão degradadas de forma
explícita em vez de fabricadas:

1. **Setas de tendência (▲ avanço / ▼ recuo / = mesma etapa) — removidas.** Elas vêm de
   `GET /task/{id}/time_in_status`, que exige um id de tarefa por chamada, ou seja, um dataset que
   dependa do resultado de outro. O portal não encadeia datasets (cada bloco é uma requisição
   independente e o `path` não aceita variável). No lugar, cada cartão ativo mostra a **data de
   `date_updated`**, destacada quando é o dia mais recente — sinal honesto de "mexeu agora", que
   **não** é direção de etapa. A legenda do dashboard explica isso.
   → **Isto deixa de ser um limite no dia em que o log de ontem for preservado**: ver "Preservar o log
   do dia anterior", adiante. A conta da seta não é o problema; a base de comparação é.
2. **Delta de Companies (ex.: −1) — indisponível.** Exigiria um valor do dia anterior, e
   `amasty_company_account_company` **não tem coluna de data** (verificado: nenhuma coluna
   timestamp/date na tabela) — nem o portal persiste snapshot entre refreshes. O cartão mostra o
   total atual, rotulado como total atual sem histórico por dia. Contacts **não** tem esse problema:
   `customer_entity.created_at` existe, e `mkt_novos_contatos` dá os novos de qualquer dia — melhor
   que o `history.json` local, que só sabia dos dias em que alguém rodou o script.
3. **O quadro do ClickUp é sempre o estado ATUAL**, mesmo com uma data passada escolhida no seletor
   — não existe histórico de status sem o `time_in_status`. A barra do tile diz isso com a etiqueta
   "estado atual · sem histórico por dia", e a versão local **tem** esse seletor (janela de 60 dias).
   → Mesmo destravamento do item 1: ver "Preservar o log do dia anterior".

## Preservar o log do dia anterior

**Por que este arquivo fala disso:** as setas (▲ avanço / ▼ recuo / = mesma etapa) e o quadro por dia
já funcionam na versão local e **não** aqui. Falta uma única coisa: o **estado do quadro no fechamento
de ontem**. O portal não consegue produzir isso sozinho — ele refaz todas as consultas do zero a cada
atualização (não guarda nada entre refreshes), não encadeia datasets, e o histórico do ClickUp só
existe atrás de um endpoint **por tarefa** (`/task/{id}/time_in_status`). Logo o dia anterior precisa
ser **preservado por quem já o calcula** e lido aqui como um dataset comum. **Estas instruções são a
parte que não pode se perder:** sem o log de ontem guardado, nenhuma implementação futura das setas é
possível — o dado simplesmente não existirá mais.

### O que precisa ser preservado

Uma linha por tarefa, com a etapa em que ela estava às **23:59:59 (America/Phoenix)** daquele dia:

    {
      "tarefas": [
        { "refere_se_a": "2026-07-28", "id": "868ggetw0", "col": 3, "status": "ready to deploy" },
        { "refere_se_a": "2026-07-28", "id": "868j82089", "col": 1, "status": "researching" }
      ]
    }

- **Chave = `id` da tarefa**, nunca o título: título é editado e renomeado, id não.
- `col` = a numeração 1→5 da tabela de colunas acima (a mesma do report manual).
- **`refere_se_a` repete em toda linha de propósito.** Um dataset do portal entrega só as *linhas*
  (`select: tarefas`), então qualquer campo fora do array se perde no caminho — e é justamente essa
  data que a página precisa conferir (regra 3 abaixo).
- Quem já calcula isso: o `build_data.py` da versão local, todo dia às 22:00 locais (18:00 Phoenix).
  O `data.json` que ele grava já traz `tasks.items[].hist` (histórico de status normalizado, por
  tarefa) — **não é preciso computar nada novo, só publicar**.

### As regras de preservação (é aqui que dá errado)

1. **Nunca sobrescrever o arquivo de ontem antes de a comparação de hoje acontecer.** Publique um
   arquivo por dia, com a data no nome (`board-2026-07-28.json`), e guarde os **últimos 7 dias**.
2. Se for uma URL fixa (`board-latest.json`), o arquivo tem de conter **os dois** dias. Ler a mesma
   URL duas vezes e chamar uma delas de "ontem" faz **toda** seta virar `=` — e `=` é resultado
   plausível ("ninguém mexeu"), então o erro não aparece na tela: o dashboard mente com cara de dado
   certo. É a pior falha possível aqui.
3. **O arquivo declara a que dia se refere e a página confere.** Se a base não for o dia anterior ao
   do quadro, não se desenha seta nenhuma e se diz de que dia a base é. Falha visível, nunca seta
   errada.
4. Tarefa que **não está** na base recebe **"novo"**, nunca `=`: afirmar "mesma etapa" de uma tarefa
   que não existia ontem é falso. É a regra que a versão local já segue.
5. Se o run das 22:00 falhar, a base do dia seguinte é a **mais recente disponível**, e a tela declara
   contra qual dia está comparando. É por isso que se guardam 7 dias, e não 1.

**Ganho colateral que justifica o esforço:** um log preservado dia a dia é **mais exato** do que
reconstruir o passado depois. O `since` do ClickUp é a **última** vez que a tarefa entrou em cada
status, então idas e voltas repetidas ao mesmo status ficam invisíveis — é por isso que a versão local
marca alguns cartões com "?" em datas passadas. Um snapshot tirado todo dia às 18:00 Phoenix registra
o estado **como ele era** e não degrada com o tempo.

### Estado: os dois lados já estão prontos — falta só a URL

**Quem gera (pronto em 29/07):** o `build_data.py` grava, a cada execução das 22:00,
`board_baseline/board-AAAA-MM-DD.json` no formato acima, e mantém os **7 mais recentes**. Não exigiu
chamada nova: o histórico de status de cada tarefa já era buscado para as setas da versão local, então
a coluna de ontem sai do mesmo dado — e sai **exata** (o estado às 23:59:59 de ontem, não um retrato
das 22:00, porque o histórico permite consultar qualquer instante).

**Quem lê (pronto em 29/07):** esta página já procura o dataset **`board_baseline`**. Sem ele nada
quebra — o quadro funciona igual, sem setas, e o rodapé diz por quê. Com ele, as setas aparecem
sozinhas: **nenhuma mudança de `.html` será necessária**.

**O que falta:** publicar o arquivo diário numa URL que o servidor do portal alcance, e ativar o bloco
abaixo — ele está **indentado de propósito** para a plataforma não tentar executá-lo com uma URL de
mentira. Para ligar, virar bloco de código com a linguagem `rest` e preencher a URL:

    name: board_baseline
    connector: http
    method: GET
    url: https://<host-interno>/jem-marketing/board-ontem.json
    select: tarefas
    credentials: shared

Comportamento desta leitura, já implementado e coberto por 17 asserções em `portal_test/`:

| Situação | O que a tela faz |
|---|---|
| base do dia anterior disponível | desenha ▲▼= e **declara no rodapé de que dia é a base** |
| tarefa ausente da base | mostra **novo**, nunca `=` |
| base com mais de **3 dias** | **desliga as setas** e avisa que a base está velha — seta errada é pior que seta nenhuma |
| dataset ausente ou com erro | quadro normal, sem seta, com o motivo escrito; **não** conta como falha de fonte (nada de pílula vermelha) |

⚠ **Segurança:** o arquivo **não** leva título de tarefa — só `id`, `col` e `status` (5,5 KB para 66
tarefas). Ainda assim os ids são internos: prefira endpoint autenticado (token no conector) ou rede
interna a uma URL aberta.

**Candidato mais forte para "quem publica": o n8n**, que a JEM já usa nas integrações
NetSuite↔Magento — ele itera itens, faz uma chamada HTTP por item, guarda o estado do dia anterior e
expõe um webhook que o portal lê. ⚠ A máquina local **não** serve de host: o servidor do portal não
está na mesma rede (o host do banco Magento é IP público).

## Notas

- **Conectores:** `magento` (MySQL somente leitura, no servidor) e `clickup` (REST, token cadastrado
  no portal e compartilhado com o time via `credentials: shared` na frontmatter). **Nenhuma
  credencial neste arquivo.** O token do ClickUp é cadastrado uma vez no portal: avatar (canto
  superior direito) → Settings → Apps → **API Token** → Generate
  (<https://app.clickup.com/settings/apps>); começa com `pk_` e não expira. Não é OAuth — o endpoint
  `getaccesstoken` da doc do ClickUp serve só para apps OAuth registradas, não para token pessoal.
- **"Hoje" = `db_today`**, o relógio do próprio banco (UTC) — o mesmo relógio em que os
  `created_at` estão gravados, para os dois lados baterem. A versão local usava Phoenix (GMT-7);
  as duas podem discordar de pedidos feitos depois das 17h de Phoenix.
- **Tipos:** MySQL devolve decimais e datas como **string** (inteiros vêm como número) e os epochs
  do ClickUp vêm como string de milissegundos — a página faz `Number()` / `new Date()` antes de
  somar ou plotar.
- **Volume medido:** `mkt_orders` 3.004 linhas / 0,65s · `mkt_novos_contatos` 156 / 0,13s ·
  `mkt_totais` 1 / 0,12s; a view do ClickUp devolve 169 tarefas em ~6 páginas de 30.
- ⚠ **O endpoint da view dá timeout esporádico — e isso já apareceu no portal em produção**
  (29/07/2026: *"clickup_golive_board: The operation was aborted due to timeout"*). Medido no mesmo
  dia, direto na API: a varredura completa leva **8 a 12s** em 7 requisições (3 rodadas seguidas), ou
  seja **dentro** do orçamento — a falha é intermitente, não estrutural: de vez em quando **uma**
  página passa de 45s e derruba a coleta inteira.
  - **Não é credencial.** Chave ausente, errada ou sem permissão devolve `401`/`403`. A caixa de erro
    do dashboard trata os dois casos separadamente desde 29/07, justamente porque a versão anterior
    listava "credencial de equipe" como causa nº 1 diante de uma mensagem de timeout e mandava
    investigar o lado errado.
  - **O que fazer:** atualizar de novo. Só depois de ~3 falhas seguidas vale suspeitar de credencial
    ou da view.
  - **Por que não tem retry aqui:** nenhum bloco ` ```rest ` deste portal (em nenhum dos dashboards)
    usa opção de `timeout`/`retries` — não há evidência de que a plataforma aceite. Se algum dia
    aceitar, **é este bloco que precisa**. Fora do portal, todo script que consome esse endpoint já
    tem retry com backoff (`clickup_client.py`, `probe_clickup_view.py`, `make_fixtures.py`).
  - **A exposição é o número de requisições** (7, sequenciais). Reduzir exigiria trocar a view por
    consultas de lista (100 por página em vez de 30) — e aí o critério de "quem entra no quadro"
    deixaria de ser o do time. Decisão consciente: mantém-se a view.
- **Nº de acessos / Taxa de conversão** continuam **fora** do dashboard (não inventados): o Magento
  não tem a informação (`customer_visitor` guarda ~8 dias e subestima ~2×; `amasty_ga4_client_data`
  só tem `client_id` de atribuição de pedido). Pendente integração com o Google Analytics — há uma
  nota de uma linha no lugar.
- **Sem `localStorage` no portal** (roda em iframe sandbox): os blocos são arrastáveis na sessão,
  mas a ordem não persiste entre recarregamentos; "⟲ Ordem padrão" volta ao arranjo original.
- **Tema claro / escuro** pelo botão ☾/☀ no cabeçalho. Abre sempre no **claro** (bege). A troca só
  mexe no atributo `data-theme` da raiz — todo o resto é variável CSS, inclusive as cores dos
  gráficos, que leem `var(--teal)`/`var(--card)` direto no atributo SVG e acompanham sem redesenhar.
  Pela mesma limitação de sandbox acima, **a escolha vale para a sessão** e recarregar volta ao
  claro. No escuro os tokens `-dk` clareiam (eles são cor de *texto*: rótulo de gráfico, delta,
  legenda) e as tintas pastel `-bg` viram tintas escuras.
