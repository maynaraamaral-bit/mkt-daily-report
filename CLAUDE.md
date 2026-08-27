# JEM Marketing Daily Report — Dashboard Replication

Consolidated instructions for this dashboard (replaces the usual `context.md` + `memory.md` +
`scheduled.md` — this is a single dashboard replication, not a full project).

Unlike the other 6 dashboards in this repo, this one has **no NSAW reference image or `.dva`
export** — it was requested directly by the marketing/site stakeholder (via Maynara, after a
2026-07-27 meeting) and designed from two mockup screenshots he sent, with explicit permission
to improve the visual design (not pixel-clone it).

---

## 1. Context

A daily site + dev-pipeline snapshot for the marketing/site team: **Magento** site/sales KPIs
("Status de cadastramento e vendas do site" + "Visão geral de vendas") on top, and a **ClickUp**
kanban-style dev task board ("Fluxo de tarefas") on the bottom, mirroring what the marketing
analyst currently assembles by hand at end of day.

**Reference images** (both copied into this folder):
- `JEM Marketing Daily Report.png` — the real "Report 27 de Julho" snapshot (real data, called
  "o modelo ideal" by the stakeholder — this is the visual target).
- `JEM Marketing Daily Report (early mock).png` — an earlier placeholder-data mock (`Group 1
  (2).png`), superseded by the one above but kept for history.

### Sources

| Source | Connection | Status |
|---|---|---|
| **Magento** (`prd_db`, read-only) | MySQL, shared `../.env` | 🟢 Live — `build_data.py` queries it directly every refresh |
| **ClickUp** | REST API, `CLICKUP_TOKEN` in shared `../.env` | 🟢 Live since 2026-07-29 — `clickup_client.py`, arrows included. See §2 |

### Files

| File | Purpose |
|---|---|
| `CLAUDE.md` | This file |
| `JEM Marketing Daily Report.png` / `... (early mock).png` | Reference images |
| `queries/companies_total.sql` | `COUNT(*)` of B2B companies (Amasty) |
| `queries/contacts_total.sql` | `COUNT(*)` of Magento customer accounts |
| `queries/company_customer_map.sql` | customer_id → company_id/company_name, via the **member** junction table (not `super_user_id`) |
| `queries/orders_ytd.sql` | Order-level rows YTD, JEM-scope, `subtotal`+`discount_amount` (not `grand_total`) |
| `build_data.py` | Refresh script — **Magento and ClickUp both live** every run (see §2) |
| `clickup_client.py` | ClickUp REST client: go-live board view + per-task status history → the 5 columns with real ▲▼= arrows |
| `probe_clickup_view.py` | Read-only probe: lists the views with their API ids, dumps the board view's filters, and diffs view × full list. Re-run whenever the board config changes |
| `task_log.py` | CLI: log de status de **uma** tarefa com coluna 1→5 e seta. `python task_log.py 868ggetw0` \| `"bulk pack"` \| `--cutoff 2026-07-26`. Importa `clickup_client` para nunca divergir do quadro. Também imprime a partir de quando a trilha dela é confiável (a mesma conta que gera o "?" no quadro) |
| `board_test.mjs` | `node board_test.mjs` — 47 asserções: filtros do quadro + tema (ver §2a). Roda o `<script>` da própria `dashboard.html` num DOM stub contra o `data.json` real |
| `refresh_scheduled.cmd` | Wrapper da tarefa agendada (força UTF-8, crava o interpretador, loga) — ver §6.2 |
| `board_baseline/` | Um arquivo por dia com o **estado do quadro no fechamento daquele dia** (id → coluna 1-5), 7 dias retidos. É a base das setas do PORTAL — ver §8 e a seção "Preservar o log do dia anterior" no `.md`. Gravado pelo `build_data.py`; o dashboard local não usa (tem o histórico inteiro no `data.json`) |
| `refresh.log` | Saída do refresh automático. **Primeiro lugar a olhar se o dashboard parecer parado** |
| `portal_test/` | 180-assertion harness for the portal version (era 132 até 26/08; +48 de formato do manifesto, busca no quadro e prefers-color-scheme) (see its `README.md`). Também serve de PRÉVIA local do portal: `site/` tem a página + os dados reais |
| `clickup_snapshot.json` | Leftover from the old manual MCP pull — only used as fallback if the API fails (see §2) |
| `history.json` | Day-over-day snapshot of Companies/Contacts/etc., since Magento has no history of its own |
| `serve.py` | Shim launching the central `../server.py` |
| `data.json` / `data.js` | Generated dataset (`orders` YTD array + `company_map` + `history` + `monthly` + `tasks`) |
| `dashboard.html` | The dashboard (no external libraries; inline SVG bar/line charts, day-picker filter, draggable tiles) |

### Architecture (why the `orders` array + client-side compute)

`build_data.py` emits the **raw YTD order rows** (JEM-scope) plus a `customer_id → company_name`
map and the day-over-day `history` snapshots. `dashboard.html`'s `compute(dateStr)` derives
**every** day-scoped KPI (orders/faturamento today, month-to-date, YTD-to-date, highlight order,
the 6-month trend ending at the selected month) from those raw rows — this is what lets the
**day-picker (Hoje/Ontem/calendar) recompute the whole top half instantly**, for any day between
2026-01-01 and today, without re-querying Magento. Companies/Contacts/"1ª compra" are **not**
derivable this way (Magento has no per-day history of them) — they read from `history.json` for
whatever date was captured, and show "Sem captura para este dia" otherwise.

---

## 2. ClickUp data — LIVE via API since 2026-07-29 (was manual; §2b keeps the old notes)

**`clickup_client.py` builds the whole board with no human in the loop**, using `CLICKUP_TOKEN`
from `../.env`. `build_data.py` calls it every run, so `python build_data.py` now refreshes
**both** Magento and ClickUp — trend arrows included.

- **Source = the go-live "Board" view** (`6-901112863157-2`), not the two lists. The team's own
  curation decides who's on the board; this repo only maps status → column. See §9 for the probe
  findings behind that switch.
- **Arrows are real**: one `/task/{id}/time_in_status` call per task that can still move, compared
  against **yesterday 23:59:59 Phoenix**. This is the part the portal cannot do — it can't chain a
  request per row (§9). Since the date filter (§2a) the same call set also feeds past-day
  reconstruction, so the sweep is **active tasks + tasks closed inside the reconstruction window**
  (66 calls on 2026-07-29, was 36).
- **A task with no baseline gets `trend: "new"`, never a fabricated `=`.** `dashboard.html` renders
  it as "novo" with its own tooltip; claiming "mesma etapa" for a task that didn't exist yesterday
  would be a lie.
- **Fallback chain, always visible on screen:** live API → `clickup_snapshot.json` (old manual pull)
  → static reference copy. `tasks.source` carries which one, and the tile footer states it, so stale
  data can never masquerade as live.

### ⚠ The `since` trap (cost a silent all-arrows-blank bug on the first run)

`status_history[].since` lives in **two different places** depending on who answers:

```
REST v2 cru : {"status":"doing", "total_time":{"by_minute":19834,"since":"1784155628314"}}
normalizado : {"status":"doing", "since":"1784155628314", "total_time":"13d 16h 22m"}   <- MCP
```

Reading only `h["since"]` makes **every** task look baseline-less, and since the fallback is `"new"`,
the board renders with no arrows at all instead of raising. `clickup_client.history_since()` handles
both — don't "simplify" it. Two guards were added so this can't be silent again:
`stats.tasks_without_usable_since` and `stats.all_new_suspicious` (a whole board of `new` would mean
every task was created today — implausible), both printed by `build_data.py` and shown in the tile.

### Verification (2026-07-29)

Running with the cutoff moved back to **26/07 23:59:59** reproduced, independently, the movements we
had established by hand from the raw log: **Bulk Pack ▲** (`blocked` col 1 → `ready to deploy` col 3
— matching the reference report's ↑ for that task), plus `Fallback and Notification` ▲ and
`Update Shopping Cart` ▲, and `Price Spy` as **novo** (created after the cutoff, so correctly no
arrow). With the normal cutoff (yesterday EOD) all 36 came back `same`, which matches reality —
nobody moved anything that morning.

## 2a. Board filters — date + status (added 2026-07-29, local dashboard only)

Two filters **inside the ClickUp tile**, asked for by Maynara ("uma opção de data assim como temos
para o magento e outra opção de status"):

- **Data do quadro** — Hoje / Ontem / calendar, same shape as the top-of-page day picker. It
  **remounts the board for that day**, it does not merely hide cards.
- **Status** — multi-select popover, options derived from the statuses actually present *on the
  selected date*, grouped by column, with counts and ClickUp's own status colors. Unmapped/backlog
  statuses are listed too, **disabled**, under "Fora do quadro" — visible, not swallowed.

Both are deep-linkable: `?board=YYYY-MM-DD` and `?st=a~b~c` (alongside the existing `?date=`).
Changing the **top** picker drags the board with it; changing the **tile** picker moves only the
board (a footer line says so). Each card now shows its ClickUp status next to the arrow.

### How past days are reconstructed (and why that's honest)

`build_data.py` no longer emits pre-built columns. `clickup_client.build_board` emits **raw tasks +
each one's normalized status history** (`items[].hist = [{ms, s}]`), and `dashboard.html` buckets
them per selected date: a task's column on day *T* is the status with the greatest `since ≤ 23:59:59
Phoenix of T`; its arrow compares that against the same computation for *T−1*. Same "base data in
the file, aggregation in the browser" convention as the Magento `orders` array. For today this
reproduces the server's board **exactly** — asserted card-by-card in `board_test.mjs`, arrows
included.

`columns` in `data.json` is now **definitions only** (label/icon/color, no cards) so the board can't
have two versions. The old shape (cards nested in columns) still renders — that's what
`clickup_snapshot.json` and the static copy carry — and in that mode **the filter bar is hidden**,
because there's no history to filter on.

**Window = 60 days** (`clickup_client.HISTORY_WINDOW_DAYS`), which is what bounds the date picker
(`history_from`). The window is what keeps the pull affordable: to rebuild day *T* you need history
for everything not yet finished at *T*, i.e. active tasks + tasks closed inside the window. Anything
closed before the window was already done on any reconstructable day, so its `date_closed` alone
places it in column 5 — no call. On 2026-07-29 that was 36 + 30 = **66 calls instead of 169**.

### ⚠ The `since` floor is not theoretical — hence the "?" cards

`since` is the **last** entry into each status, so a task that revisits a status erases its earlier
visit. Proof from this very repo: reconstructing **27/07** put *"Dashboard Credit Limit - Dados"* at
`doing`, while §2b's own record shows it was `approved by qa - prd` at that cutoff — it was reopened
and re-approved on 28/07, moving that `since` forward.

That is detectable, so it is detected instead of shipped: `total_time` is the accumulated time
across **all** visits, so when it exceeds the visible span (`since` → next entry, or → now), that
status had a hidden earlier visit. `clickup_client.unsure_before()` returns the greatest such
`since` = the instant from which the task's trail is complete. Cards reconstructed **before** that
instant render as **`?`** (dashed border, own tooltip, no arrow) and are counted in the footer.
Today's board is never affected. Reality check on 2026-07-29 data: 4 uncertain cards on 27/07, 15 on
15/06 — the degradation with age is real, visible, and labelled.

**Do not "improve" this by hiding the `?` or guessing an arrow for those cards** — it's the same
rule as §9's "a wrong arrow is worse than no arrow". `task_log.py` prints the same
"trilha confiável de" instant, so any card can be audited by hand.

Other declared limits, all on screen in the tile footer: only tasks **currently in the view** appear
(someone removed from the view later is gone from past days too); tasks with no known status on that
date are counted out loud; column 5 stays capped at the 10 most recent completions **as of the
selected date**.

## 2b. ClickUp data — the old manual mechanism (superseded, kept for context)

**There is no ClickUp connector reachable from a standalone Python process in this repo.** The
`mcp__claude_ai_ClickUp__*` tools only exist inside a live Claude conversation (OAuth'd per
session) — `build_data.py` (which runs via plain `python build_data.py`, no Claude in the loop)
cannot call them. Per Maynara's decision (2026-07-28: "vamos seguir tudo via MCP"), this dashboard
does **not** use a ClickUp API token in `.env` (the alternative path, which would make it fully
self-refreshing like Magento — still open if ever wanted, see §6).

**Current mechanism:** a human asks Claude (in a conversation, with ClickUp MCP connected) to
re-pull the board and overwrite `clickup_snapshot.json` in this folder, in the shape shown below.
`build_data.py`'s `load_clickup_tasks()` reads that file if present, else falls back to a
hand-copied static placeholder matching the reference image. **The ⟳ Refresh data button in the
dashboard does NOT refresh ClickUp** — only Magento. Re-pulling ClickUp is a separate, manual step.

### Scope (confirmed with Maynara 2026-07-28)

Exactly **2 ClickUp lists**, both under space "JEM Systems eComm":
- **Incident Support | Go-Live** — list_id `901112863157`
- **Hyvä Backlog** — list_id `901110423629`

Explicitly **excluded**: Sprint N lists (e.g. "Sprint 16"), "QA Board", "QA Automation" — these
are the team's own dev-process lists, not what the marketing report tracks. *(If the true
population changes, Maynara said she'd tell me — don't re-derive this from scratch.)*

### Status → column mapping

Both lists share the same 15 real ClickUp statuses. `backlog` is **excluded from the board
entirely** (not yet started = not "active pipeline", per Maynara). **No further curation** —
every task whose current status falls in a column below is shown, however many that is (as of
2026-07-28, "Em andamento" alone is 40 cards — confirmed intentional, not a bug; the UI scrolls
each kanban column internally, `.kcol-scroll`, so one big column doesn't blow up tile height).

| Column key | Label | ClickUp statuses |
|---|---|---|
| `in_progress` | Em andamento | researching, to do (sprint), doing, on hold, blocked, code review - stg |
| `ready_stg` | Prontas para validação (STG) | ready for testing - stg, testing - stg, fail - stg |
| `awaiting_deploy` | Tarefas aguardando Deploy | ready to deploy |
| `ready_prd` | Tarefas prontas para validação (PRD) | ready for testing - prd, testing - prd, fail - prd |
| `done_prd` | Conclusões mais recentes (PRD) | approved by qa - prd, Closed |

### Trend arrows (▲ avanço / ▼ recuo / = mesma etapa)

Computed from **ClickUp's own history**, not a homemade snapshot: `clickup_get_task_time_in_status`
(per task) returns `status_history` (`{status, since}`, `since` = epoch ms). For each active task
(everything except `done_prd`), find the status whose `since` is the latest one `<=` **the cutoff
`2026-07-27 23:59:59 America/Phoenix`** ("yesterday end of day" relative to the 2026-07-28 pull),
map it to a column, and compare its ordinal (in_progress=1 … ready_prd=4) to today's current-status
column. This is more robust than a homemade daily snapshot (which is what Companies/Contacts use)
because ClickUp already retains the true change history — no need to have been capturing our own
snapshots every day in advance. **Worked/verified example:** task `868ggetw0` ("[JEM-Hyva]
Integração do atributo Bulk Pack…") — confirmed 3 real status changes on 2026-07-27 (`fail - stg`
12:24:09 → `testing - stg` 15:51:02 → `ready to deploy` 15:51:06, all Phoenix time) via this exact
method, cross-checked against the reference report's "↑" for that same task.

**`done_prd` (Conclusões mais recentes) — top N=10**, no date filter (per Maynara — spans however
far back it needs to, e.g. 2026-07-07 to 2026-07-27 on the first pull). Sort key = completion
timestamp: `date_closed` for `Closed`-type tasks (already in the plain task-list pull, no extra
call); `current_status.since` (needs `time_in_status`) for `approved by qa - prd` (a `done`-type
status, not `closed`-type, so `date_closed` is null for those).

### Real regressions found on the first pull (2026-07-28) — sanity-check that this actually works
- **"Fallback and Notification - IF and Invoice"** — was ready-for-testing in **PRD** as of the
  cutoff, failed and got sent back to **STG** → trend "down".
- **"Dashboard Credit Limit - Dados"** — was **approved by qa - prd** as of the cutoff (i.e.
  already effectively done) and got **reopened** to testing-prd → trend "down".

Both surfaced correctly with the method above — a good sign the logic is sound, not just luck.

---

## 3. Widget → data mapping & formulas

Three filters: the page-wide **day picker** (Hoje / Ontem / calendar, bounded to
`[2026-01-01, today]`, `?date=YYYY-MM-DD`), plus — inside the ClickUp tile — its own **board date**
(`?board=`) and a **status multi-select** (`?st=`). See §2a.

| Widget | Definition |
|---|---|
| **Companies** | `COUNT(*)` `amasty_company_account_company` (2,992ish) |
| **Contacts** | `COUNT(*)` `customer_entity` |
| **Companies com 1ª compra** | distinct `company_id` (via the **member** junction `amasty_company_account_customer`, not `company.super_user_id` — that only catches the company admin, missing regular employee-placed orders) with ≥1 JEM order since 2026-01-01 |
| **Pedidos hoje / no mês / desde janeiro** | `COUNT(*)` of JEM-scope orders for the selected day / that day's month-to-date / YTD-to-date |
| **Faturamento hoje / no mês / acumulado** | `SUM(subtotal + discount_amount)` — see §4 "Faturamento" |
| **Pedido destaque do dia** | the single highest-`amount` order that day, with company name resolved via the same member-junction map |
| **Faturamento / Nº de pedidos — últimos 6 meses** | client-computed from the raw `orders` array, 6 months ending at the **selected** day's month (so picking a past date re-anchors the chart, not just the KPIs) |
| **Nº de acessos / Taxa de conversão** | **removed from the UI 2026-07-28** (not fabricated) — see §4 |
| **Fluxo de tarefas (ClickUp)** | see §2; per-day reconstruction + status filter in §2a |

### Interactivity
- **Day picker**: Hoje / Ontem buttons + `<input type=date>`, bounded, deep-linkable. Recomputes
  every day-scoped KPI + both charts instantly from the `orders` array (no re-query). It also
  drags the ClickUp board to the same day (clamped to the board's 60-day window, which the tile
  footer explains when it bites).
- **Board filters** (inside the ClickUp tile): its own date picker + status multi-select — §2a.
- **Tema claro/escuro** (`☾ Escuro` / `☀ Claro` no cabeçalho), pedido por Maynara 2026-07-29.
  Troca só `data-theme` na raiz — todo o CSS é token, e os SVGs dos gráficos leem
  `var(--teal)`/`var(--card)` no próprio atributo, então nada é redesenhado. Escala de acento
  igual à do portal (as `-dk` **clareiam** no escuro porque são cor de texto; as `-bg` escurecem);
  os neutros aqui são frios, para combinar com o claro deste dashboard. `color-scheme` acerta o
  que é nativo (seletor de data, barra de rolagem). A escolha persiste em `localStorage`
  (`jem-mktdaily-theme`) e é aplicada por um script no `<head>` — sem isso, quem usa escuro leva
  um flash branco a cada carga. O portal não persiste (iframe sandbox); aqui persiste.
  ⚠ Fundo de toast/pílula tem de usar a cor **forte** (`--green`), nunca a `-dk`: no escuro a
  `-dk` clareia e o texto branco some. `board_test.mjs` falha se algum token do claro não tiver
  par no escuro, ou se sobrar cor fixa de fundo/borda no CSS.
- **Draggable tiles** (`⠿`); layout persists in `localStorage` (`jem-mktdaily-layout-v1`); **⟲ Reset
  layout**.
- **⟳ Refresh data** re-queries **Magento *and* ClickUp** (needs `python serve.py`). It goes through
  `/api/refresh` → `build_data.build()`, which since 2026-07-29 pulls the board view and the status
  history too — so the button now also refreshes the arrows. Takes **~60s**: one history call per
  active task *and* per task closed inside the 60-day window (66 on 2026-07-29). *(Before that date
  it touched Magento only; that claim survives in §2b as history.)*
- Kanban columns scroll internally (`max-height:520px`) so a large column (e.g. 40-card "Em
  andamento") doesn't blow up the tile.
- **Colors:** teal = site/company identity (Companies, Contacts, 1ª compra) · blue = order counts ·
  green = money/faturamento · gold = highlight/destaque · purple/orange/blue/gold = kanban
  pipeline-stage icons (matching the reference's own icon colors).

---

## 4. Key formulas & decisions confirmed with Maynara

1. **Order scope = JEM-prefixed `increment_id` only** (`LIKE '%JEM%'`), same rule as the
   `JEM Magento Customer Sales` dashboard. Confirmed 2026-07-28 by an **exact match** against the
   "Report 27 de Julho" reference for 2026-07-27: Pedidos hoje 32≡32, Faturamento hoje / Pedido
   destaque `$7,010.51 #JEMUS000002914 Briscoe Protective` matched exactly (before the faturamento
   change below), Pedidos no mês 449≡449. The alternative ("SO######"-numbered orders, a
   different/non-JEM channel) is **excluded**.
2. **No order-state filter** — `canceled`/`closed` states are **not** excluded from any count/sum.
   Excluding them made the reconciliation against the reference *worse*, not better.
3. **"Faturamento" = `subtotal + discount_amount`, changed 2026-07-28 (per Maynara).** Originally
   built on `grand_total`; Maynara flagged that `grand_total` mixes in shipping and tax, which
   isn't "valor de venda". Confirmed via schema: `grand_total = subtotal + discount_amount +
   shipping_amount + tax_amount` (shipping_tax_amount is already folded inside `tax_amount`, not
   separately additive — verified on order `JEMUS000002914`: 6392.75 + 0 + 76.00 + 541.76 =
   7010.51 = grand_total exactly). `discount_amount` is stored **already negative** in Magento, so
   `subtotal + discount_amount` nets it out correctly with no sign flip needed. Every money KPI
   (today/month/accumulated, the 6-month chart, the highlight order) uses this, not `grand_total`.
   Renamed "GMV" → "Faturamento" everywhere in the UI to match.
4. **Company name on the highlight order** resolves via `amasty_company_account_customer`
   (per-member link), **not** `amasty_company_account_company.super_user_id` (the company admin
   only) — confirmed live: order `JEMUS000002914`'s buyer (customer 3375, "William St Louis") only
   resolves to "Briscoe Protective - Pye-Barker NY" through the member junction; the super_user-only
   join returned `None` for this exact order in an earlier build.
5. **Nº de acessos / Taxa de conversão hoje — removed from the UI 2026-07-28** (per Maynara: don't
   show pending-source placeholder tiles, just a note). Not available from Magento: `customer_visitor`
   only retains ~8 days and undercounts the reference figure (594 actual vs 1,206 in the reference
   for the same day) — likely GA4-sourced in the original manual report. `amasty_ga4_client_data`
   only stores order-attribution `client_id`s, not general traffic. A one-line note now sits in the
   highlight-bar card: "Nº de acessos e Taxa de conversão ainda não estão disponíveis — pendente
   integração com o Google Analytics."
6. **Day-over-day deltas** (Companies −1, Contacts +18, "1ª compra" ±pp) need a **prior-day
   snapshot**, which Magento doesn't retain — `history.json` captures one entry per calendar day
   (capped to the last 60) and diffs are `null` → shown as "—" until 2+ days exist. This is
   **separate** from the ClickUp trend mechanism (§2), which doesn't need a homemade snapshot since
   ClickUp retains real history itself.
7. **ClickUp board = no curation, all active tasks shown** (per Maynara 2026-07-28, explicitly
   overriding an earlier narrower "only a handful of highlighted tasks" reading of the reference
   image) — see §2.

---

## 5. Environment — FIXED 2026-07-29, plain `python` now works

`python build_data.py` works from any folder. The interpreter is **Anaconda3 3.12.7**
(`C:\Users\MaynaraAmaral\anaconda3\python.exe`), with `pymysql` installed.

**What was wrong until 2026-07-29:** bare `python` resolved to the **Microsoft Store stub**
(`AppData\Local\Microsoft\WindowsApps\python.exe`), which sat at position 2 of the *user* PATH while
Anaconda wasn't on the PATH at all. Everything in this folder's history therefore used the full
Anaconda path explicitly — if you find such a command, it still works, it's just no longer necessary.

**The fix:** three directories prepended to the **user** PATH, ahead of `WindowsApps` —
`anaconda3`, `anaconda3\Library\bin`, `anaconda3\Scripts`. `where python` now lists Anaconda first
and the stub second; `pip` resolves to Anaconda's too.

⚠ **`Library\usr\bin` and `Library\mingw-w64\bin` were deliberately left OUT.** They carry unix
builds of `find.exe`, `sort.exe` and friends, which would shadow the Windows ones and silently break
unrelated `.bat`/`.cmd` scripts. If some conda package ever complains about a missing DLL, add
`Library\bin` first (already there) before considering those two.

The previous user PATH was backed up to `C:\Users\MaynaraAmaral\path-user-backup-<timestamp>.txt`.

⚠ **Already-running processes keep the old PATH** — Windows only hands the new value to processes
started after the change. VS Code and any open terminal must be **fully restarted** (not just a new
tab) before `python` works inside them.

**`refresh_scheduled.cmd` still hard-codes the full Anaconda path on purpose.** A scheduled job must
not depend on PATH resolution — that's exactly the kind of dependency that makes an unattended task
fail silently after an unrelated environment change.

---

## 6. Open items / next steps

1. ~~**"AI Dashboard Central" portal version**~~ — **DONE 2026-07-28**, see §8. Both open questions
   were answered by the platform's own authoring spec (pasted by Maynara): **no dataset chaining**
   (every block is one independent request, `path` takes no variables) and **no day-over-day
   persistence** (each refresh is a fresh server-side snapshot). Files:
   `portal_jem_marketing_daily.md` + `portal_jem_marketing_daily.html`.
   **Still to do:** publish them, and register a ClickUp API token in the portal **once** —
   unavoidable, see the `rest` gotchas in §8. `credentials: shared` now sits in the `.md`
   frontmatter so that single token serves the whole marketing team (Maynara's call, 2026-07-28).
2. ~~**`CLICKUP_TOKEN` in `../.env`**~~ — **DONE 2026-07-29.** Token in place, `clickup_client.py`
   written, `build_data.py` wired, and a **Windows scheduled task** registered:

   | | |
   |---|---|
   | Task name | `JEM Marketing Daily Report` |
   | Runs | daily **22:00 local (UTC-3) = 18:00 Phoenix** — end of the work day, so the arrows cover the whole day (they compare yesterday's close against the moment of execution) |
   | Entry point | `refresh_scheduled.cmd` (wrapper) → `build_data.py` |
   | Log | `refresh.log` in this folder — **check here first if the dashboard looks frozen** |
   | Verified | triggered manually 2026-07-29: exit code 0, 30s, 36 history calls, accents intact in the log. Same day, after the board filters (§2a), a normal run does **66** history calls in ~60s — still far inside the 30-min limit, but the number grows with how many tasks close inside the 60-day window |

   Two things the wrapper exists for, both learned the hard way: it forces
   **`PYTHONIOENCODING=utf-8`** (the script prints accented text and a cp1252 log target raises
   `UnicodeEncodeError` mid-run — this already killed the probe once), and it hard-codes the
   **Anaconda interpreter path** with an explicit error if it's missing (bare `python` here is the
   Store stub, §5). Settings: `StartWhenAvailable` (a missed run catches up), 30-min limit,
   `IgnoreNew` so two runs can't overlap.

   ⚠ The task runs in Maynara's user context, so it needs her **logged on** at 22:00. If the machine
   is off/logged out, `StartWhenAvailable` makes it run at the next opportunity instead — the data
   is then late but never silently stale, since `last_execution` is on screen.
3. **GA4/analytics integration** for Nº de acessos + Taxa de conversão — no source connected yet.
4. **`?all=True`-style "show hidden" param** — not applicable here (no hidden-row concept like the
   Limit dashboard), just noting it's not missing, N/A by design.
5. Add this dashboard to the root `INDEX.md` dashboards table (done as part of this same save-state
   pass — check it's still there if this file predates a later INDEX.md edit).

---

## 7. Decisions / memory log

- **2026-07-27** — Marketing/site stakeholder meeting; Maynara scoped a new daily-report dashboard
  (Magento site KPIs + ClickUp task log). ClickUp MCP connected same day.
- **2026-07-28** — Received the "Report 27 de Julho" reference (real data, called the ideal model,
  freedom to improve granted). Probed Magento live via `pymysql` (Anaconda) to validate: Pedidos
  hoje, GMV(→later Faturamento) hoje, Pedido destaque all matched exactly for 2026-07-27 under the
  JEM-scope/no-state-filter rule. Built dashboard #7: `queries/*.sql`, `build_data.py`,
  `dashboard.html`, `serve.py`, `history.json` mechanism for day-over-day deltas. Loaded the
  `dataviz` skill for the two 6-month charts (teal single-hue, mark specs, tooltips).
- **2026-07-28 (day-picker)** — Added the Hoje/Ontem/calendar filter; reworked `build_data.py` to
  emit raw YTD `orders` + `company_map` + `history` instead of pre-baked "today" KPIs, so
  `dashboard.html`'s `compute(dateStr)` can recompute any day client-side. Verified `?date=2026-07-27`
  reproduces the reference exactly (see §4.1).
- **2026-07-28 (faturamento fix)** — Per Maynara, swapped every money figure from `grand_total` to
  `subtotal + discount_amount` (excludes shipping/tax). Renamed "GMV" → "Faturamento" throughout.
  Fixed the highlight-order company-name join to use the member junction table instead of
  `super_user_id`. See §4.3–4.4.
- **2026-07-28 (ClickUp investigation)** — Discovered ClickUp's `time_in_status` API retains real
  `status_history` with timestamps (no homemade snapshot needed for trend). Explored candidate
  lists; user pointed to "Go Live > Incident Report" — resolved to list `901112863157`
  ("Incident Support | Go-Live") via a matching task title ("Avatax Implementation in Magento").
  Verified the platform's actual connector model (`conexoes.png` screenshot: `rest`/`mysql` blocks,
  per-user API keys) — realized "via MCP" ≠ a literal MCP-protocol connector on the platform, but
  the user chose to proceed via manual Claude+MCP pulls for now regardless (see §6.2).
- **2026-07-28 (Bulk Pack task hunt)** — The reference's "Integração do atributo Bulk Pack…" task
  wasn't in "Incident Support | Go-Live"; a fork searched ~300 tasks across 2 spaces without
  finding it; user screenshotted the task directly (`868ggetw0`, list "Hyvä Backlog") — this is
  what revealed the board spans 2 lists, not 1. Used this task's real `status_history` to prove the
  cutoff-comparison method (3 real status changes reconstructed with exact Phoenix timestamps).
- **2026-07-28 (ClickUp scope + full pull)** — Maynara confirmed the 2-list scope (Incident Support
  + Hyvä Backlog) and N=10 for "Conclusões mais recentes". First fork pull over-curated (excluded
  `to do (sprint)`, narrowing "Em andamento" to 14) — Maynara corrected: no curation, show
  everything (→ 40 cards) and make sure fail→testing regressions are included. Resumed the same
  fork with corrected instructions; wrote the real `clickup_snapshot.json` (40/3/1/2/10 across the
  5 columns); added `.kcol-scroll` (max-height 520px) so the 40-card column doesn't blow up tile
  height; added a completion-date footer (instead of a trend arrow) for `done_prd` cards.
- **2026-07-28 (acessos/conversão removed)** — Per Maynara, removed the two pending-source KPI
  tiles entirely (Nº de acessos, Taxa de conversão) and replaced with a one-line note in the
  highlight-bar card instead of showing empty/placeholder tiles.
- **2026-07-28 (session save-state)** — Maynara asked to save all context before restarting VS
  Code; this CLAUDE.md was written to capture the full state (previously undocumented) — see §6 for
  what's still open, especially the paused "AI Dashboard Central" portal work.
- **2026-07-28 (portal version built)** — Maynara pasted the platform's authoring spec, which
  answered both blocking questions (no chaining, no persistence). Wrote
  `portal_jem_marketing_daily.md` + `.html`. See §8 for the full design + what degraded and why.
- **2026-07-29 (`credentials: shared` — two wrong guesses, then settled)** — The portal kept asking
  for an API key. First I *removed* the line (made it worse: per-user keys), then moved it to the
  document frontmatter (a guess, and it broke the `.md`). Settled: **inside the ` ```rest ` block,
  H1 first**, and the honest conclusion is that **a token must be registered once regardless** — the
  line only decides *whose* key is used, it never silences the prompt. See §8.
- **2026-07-29 (board = the go-live view)** — Per Maynara: *"vamos replicar exatamente o que está no
  board mesmo que as tarefas de exemplo do print saiam."* Wrote `probe_clickup_view.py` first instead
  of editing blind; it showed the browser-URL view id works verbatim, the view spans **3 lists** (so
  **Bulk Pack was never at risk**), and `/view/{id}/task` **ignores `show_closed`** and returns the
  133 closed tasks — which let column 5 survive from the same single dataset. Active tasks ~46 → 36.
- **2026-07-29 (ClickUp automated end to end)** — Token approved and pasted; wrote `clickup_client.py`
  (view + one `time_in_status` per active task → real ▲▼=), wired `build_data.py`, registered the
  daily scheduled task (§6.2). **First run silently produced a board with no arrows at all**: the raw
  REST nests `since` inside `total_time` while the MCP tools return it flat, so every task looked
  baseline-less and fell back to `"new"`. Fixed in `history_since()` and guarded by
  `tasks_without_usable_since` + `all_new_suspicious`. Verified by moving the cutoff back to 26/07 and
  independently reproducing the movements found by hand (Bulk Pack ▲, plus two others, and `Price Spy`
  correctly `novo`). Added `task_log.py` for per-task auditing.
- **2026-07-29 (portal UI)** — Warm paper palette (*"esse branco tá desconfortável"*), centred filter
  bar, light/dark toggle, and a **multi-select status filter** on the board tile. Two of my own test
  defects surfaced and were fixed: an assertion that searched for `<svg` in the wrong element (passing
  because the KPI icons are also SVG) and a tautology (`every(() => true)`). Harness: 79 assertions.
- **2026-07-29 (PATH fixed)** — Plain `python` now resolves to Anaconda; see §5. Note that already-open
  terminals/VS Code keep the old PATH and need a full restart.
- **2026-07-29 (board filters: data + status)** — Maynara pediu, para o tile do ClickUp, "uma opção de
  data assim como temos para o magento e outra opção de status". Interpretado como a mesma semântica
  do filtro do Magento: **remontar o quadro naquele dia**, não só esconder cartões. Provado antes de
  codar que dava: `status_history` **inclui o status atual** (3 tarefas conferidas ao vivo), então a
  reconstrução em JS bate exatamente com o quadro do servidor para hoje. `build_data.py` passou a
  emitir tarefas cruas + histórico (`items[].hist`) e `columns` virou só definição. **A verificação
  achou um erro real antes de ir para a tela**: 27/07 reconstruía "Dashboard Credit Limit" como
  `doing`, mas o §2b registra que ela estava em `approved by qa - prd` naquele corte — o `since`
  tinha andado para a re-aprovação do dia 28. Daí `unsure_before()` e os cartões **"?"** (§2a), em
  vez de afirmar etapa errada. `board_test.mjs` (39 asserções) cobre tudo isso; a coluna 5 continua
  no top 10 **da data escolhida**. Custo do pull: 36 → 66 chamadas (~60s).
- **2026-07-29 (filtros centralizados + tema escuro)** — Pedidos na sequência, olhando a tela: as
  barras de filtro foram centralizadas (a do quadro com fundo teal, para ter peso de filtro de
  verdade) e o dashboard ganhou **tema claro/escuro** persistente (§3). O CSS local passou a ser
  100% token: `board_test.mjs` (47 asserções) agora quebra se um token do claro não tiver par no
  escuro ou se sobrar cor fixa de fundo/borda.
- **2026-07-29 (paridade do portal)** — *"replique esse mesmo dashboard do html para eu colocar no
  portal"*: portada a parte visual (barra de filtro do quadro destacada dentro do tile, status +
  bolinha no cartão, popover centralizado, coluna vazia igual). Só `.html` — nenhum dataset mudou.
  O seletor de **data do quadro** continua impossível no portal (histórico por tarefa = uma
  requisição por tarefa) e agora tem uma etiqueta que diz isso, com o motivo no tooltip; ver
  "Paridade com a versão local" em §8. `test_portal.mjs` foi de 79 → **84** asserções (as duas que
  falharam eram o teste procurando o botão de status no lugar antigo — sinal de que o harness pega
  mudança de layout, não só de lógica).
- **2026-07-29 (timeout no portal, em produção)** — Ela subiu o `.html` e o tile do ClickUp veio com
  *"clickup_golive_board: The operation was aborted due to timeout"*. **A caixa de erro estava
  errando o diagnóstico**: listava "credencial de equipe" como causa nº 1, e credencial devolve
  401/403, nunca timeout — mandou ela investigar chave. Medido na hora, direto na API: varredura
  completa da view = **8–12s em 7 requisições**, três rodadas seguidas, ou seja dentro do orçamento;
  a falha é a instabilidade intermitente já conhecida (uma página passa de 45s). Corrigido:
  `isTimeoutErr()` + `clickupErrorBox()` separam os dois casos (timeout ganha caixa âmbar que
  desmente credencial e manda atualizar de novo; pílula diz "timeout", não "erro"), e o `.md` ganhou
  os números medidos. `test_portal.mjs` → **91** asserções, com `AIDash.meta` stubado para simular o
  jeito real que o portal reporta falha. **Não há retry no bloco `rest`** porque nenhum dashboard
  deste repo usa `timeout`/`retries` — não inventei chave; se a plataforma aceitar algum dia, é esse
  bloco que precisa.
- **2026-07-29 (envelope + base de ontem)** — Depois de subir os 3 datasets, o tile veio com
  *"Nenhuma tarefa retornada"* — sem erro e com zero linhas. Causa provável: sem paginação o portal
  entrega o **corpo cru** (`{tasks:[...]}`) porque o `select` é aplicado pelo paginador, e o
  `loadSet` só aceitava `[...]` ou `{rows:[...]}`. Agora `rowsFrom()` reconhece qualquer envelope
  plausível (e deduz a 1ª lista de um desconhecido), **registra o formato observado** e a caixa de
  vazio mostra o que cada dataset entregou — era um sintoma sem pista, virou diagnóstico. A revisão
  do teste expôs um buraco de verdade: dataset que responde **vazio sem erro** com os outros ok
  deixava o quadro renderizar e a falha passar calada; agora vira aviso nomeado no rodapé.
  Em seguida, a pedido dela (*"tente a 3"*), foram feitas as duas peças que não dependem de
  infraestrutura: `build_data.py` passou a gravar a **base do dia anterior** e o `.html` do portal a
  **lê-la** (setas ▲▼=, "novo" para quem não está na base, setas desligadas se a base tiver >3 dias,
  ausência tratada como "ainda não publicada" e não como erro). `test_portal.mjs` → **132**.
  ⚠ Aprendizado de ferramenta: editar arquivo com `pathlib.write_text` no Windows converte para
  **CRLF** e quebrou a extração do `<script>` no harness (`/<script>\n/`). As quebras foram
  normalizadas de volta para LF; edite esses arquivos com Edit, não com script Python.
- **2026-07-29 (portal: 7 → 3 requisições)** — Pedido dela: *"tente reduzir o numero de
  requisições"*. Antes de mexer, medi: o endpoint da view **ignora todo parâmetro** menos `page`
  (12 nomes testados), então página maior não existe; e o endpoint de equipe **não** substitui a view
  (filtrado por `list_ids[]` traz só a lista-mãe, 65 de 169; sem filtro de data estoura em HTTP 500 no
  próprio ClickUp após 55s). O que abriu caminho foi a **ordem** da view (ativas antes de concluídas,
  36 ativas nos itens 0–35) e o campo **`locations`**, que torna a pertinência ao board decidível fora
  da view. Resultado: 2 páginas fixas + 1 consulta de conclusões = **3 requisições (~3,5s)**, escopo
  exato, com 5 guardas de tempo de execução. Bônus não pedido mas real: as falhas ficaram
  **parciais** — página 1 fora degrada com aviso, conclusões fora esvaziam só a coluna 5.
  `test_portal.mjs` → **100** asserções (conservação agora aferida por fonte, e dois novos casos de
  degradação parcial); `make_fixtures.py` passou a gerar as 3 fixtures reproduzindo exatamente as 3
  requisições do portal.
- **2026-08-24 (a pane de 26 dias)** — Ela reportou os dados do Magento travados em 29/07. Causa
  raiz: **o banco só aceita conexão da rede da JEM**, e o job das 22:00 roda com ela em casa — 17
  falhas idênticas de timeout de TCP, nenhuma de credencial. Fechado com três medições
  independentes (conecta em 0,1s da "JEM Guests"; grant é `prd_db@%`, logo o bloqueio é firewall;
  o log de perfis de rede mostra que a única execução OK foi a única na rede da JEM). Dados
  atualizados na hora; tarefa endurecida (bateria — que estava **matando** execuções —, 5
  repetições, gatilhos 12:00/17:00/22:00); faixa de dado velho no dashboard; `connect()` com
  retry e erro que nomeia a causa. Duas descobertas laterais **não** consertadas de ofício, por
  mexerem em números já validados / no que um teste afirma: o fuso UTC+2 do servidor de banco
  (~7% dos pedidos caem no dia seguinte) e as 5 asserções congeladas de 27/07 do `board_test.mjs`
  que apodreceram junto com o `since` do ClickUp. Detalhe completo no topo do §9.
- **2026-08-24 (n8n fora, job fica no notebook)** — Perguntado onde o job deveria morar para ser
  realmente diário, ela escolheu n8n e **em seguida voltou atrás**: *"melhor deixar como está.
  vamos deixar de usar o n8n em breve, não vale a pena esse esforço."* Fica no notebook com os 3
  gatilhos + faixa de aviso; **n8n saiu do mapa** e as menções que o recomendavam (inclusive como
  host das setas do portal) foram marcadas obsoletas em vez de apagadas, para ninguém reciclar o
  desenho antigo. Nada de código mudou nesta reversão — só documentação.
- **2026-08-26 (skill `ai-dashboard`: o manifesto estava no formato que NÃO roda)** — Pedido:
  *"carregue a skill ai-dashboard e ajuste o md e o html desse projeto"*. A skill mora em
  `C:\Claude\Skills\ai-dashboard.skill` (um .zip com `SKILL.md`) e **não está instalada** como skill
  do Claude Code — foi lida direto do arquivo. O que ela estabelece, verificado por Flávio em
  25/08: **o texto de instruções do portal está errado sobre o formato do manifesto**. O `.md` daqui
  usava exatamente o formato errado (` ```mysql name=X connector=Y ` na linha da cerca, sem
  frontmatter). Convertido: frontmatter YAML (`title`/`credentials: shared`/`connectors:`) + corpo
  YAML por bloco (`name:`, `connector:`, SQL sob `query: |`). **Isto reabilita a decisão de 29/07 que
  havia sido revertida** — e agora se sabe por quê ela falhou: só a frontmatter foi movida, com o
  resto do arquivo ainda em formato de cerca. As duas peças andam juntas. `credentials: shared` ficou
  nos **dois** lugares (frontmatter + blocos `rest`), porque as duas dizem `shared` e nenhuma das
  leituras possíveis cai em chave por usuário — que foi o defeito observado ao removê-la do bloco.
  **Bug latente achado no caminho:** com o corpo do bloco sendo YAML, `{ list_ids[]: [...] }` **não
  parseia** (`[`/`]`/`,` são indicadores reservados em mapa de fluxo — `ParserError` confirmado com
  pyyaml); as chaves foram para entre aspas. No `.html`, os dois itens do padrão de dashboard da
  skill que faltavam: **`prefers-color-scheme`** (abria fixo no claro — flash branco a cada carga em
  quem usa escuro, e sem `localStorage` no sandbox não há como lembrar; o clique no botão passa a
  vencer o sistema pela sessão) e **busca por texto** no quadro (casa título/status/lista, sem acento
  e sem caixa, AND entre termos, `Esc` limpa; cumulativa com o filtro de status, e o rodapé diz
  **qual** dos dois está escondendo tarefa). Harness: **132 → 180 asserções**, 0 falhas — inclui uma
  seção nova que **afere o formato do próprio `.md`** e o contrato de nomes `.md`↔`.html`, para o
  formato não ser revertido uma terceira vez. `run_manifest.py` passou a parsear o formato novo (e
  **recusa** o antigo em voz alta). Duas armadilhas consertadas de ofício: o `test_portal.mjs` lia
  `site/index.html`, que só o `run_manifest.py` sincroniza — **fora da rede da JEM ele testava uma
  página velha em silêncio** (aconteceu nesta sessão), agora lê a origem e avisa se a prévia
  divergir; e as regexes novas do manifesto toleram CRLF, porque `core.autocrlf=true` neste repo faz
  um clone novo vir com CRLF.
  ⚠ **Duas quebras achadas nesta sessão, causadas pela mudança de pasta, NÃO consertadas** (são
  decisão dela): ver o topo do §9.

---

## 8. Portal version (`portal_jem_marketing_daily.md` / `.html`)

Six datasets (⚠ **formato do manifesto mudou em 26/08** — frontmatter YAML + corpo YAML por bloco;
os `connector=` citados abaixo viraram `connector:` DENTRO do bloco, ver o log de 26/08 no §7 e a
seção "⚠ Formato deste arquivo" no próprio `.md`): 3 × ` ```mysql ` (`mkt_orders`, `mkt_totais`,
`mkt_novos_contatos`) + 3 × ` ```rest connector: clickup ` — `clickup_board_pg0`,
`clickup_board_pg1` (páginas fixas da view, `paginate: false`) e `clickup_concluidas` (consulta de
equipe). The HTML fetches each by name (`fetch('data/<name>.json')`, which the portal intercepts) and
computes everything client-side, so the day picker still works.

**Por que 3 datasets de ClickUp e não 1 (29/07):** o dataset único com `paginate: true` custava
**7 requisições** a um endpoint com timeout intermitente — foi o que derrubou o tile em produção.
Ver "Três requisições em vez de sete" no `.md`, que carrega a medição completa. Resumo do que
sustenta o desenho: (1) a view devolve **ativas antes de concluídas**, e as 36 ativas cabem nos 60
primeiros itens (2 páginas); (2) a ordem das **concluídas é arbitrária** (84 quebras), então a coluna
5 não pode sair dessas 2 páginas — ela vem de `/team/{id}/task` filtrado por status de conclusão +
janela de 60 dias (64 linhas, 1 página, top 10 **idêntico** ao da view inteira); (3) pertinência ao
board = `list.id == 901112863157 || locations[] contém 901112863157`, regra conferida **94/94 e
100/100**, que é o que permite usar a consulta de equipe sem colar tarefa fora do board.
Cada premissa tem guarda em `boardGuards()` e vira aviso no rodapé — nada disso pode falhar calado.
⚠ Único ponto não verificável: a plataforma precisa serializar `list_ids[]`/`statuses[]` como
parâmetro repetido (vírgula dá **HTTP 400** na API, testado). Se não conseguir, só a coluna 5 esvazia,
com o motivo na tela, e o `.md` já traz o bloco alternativo sem array nenhum.

### What the portal's constraints forced (degraded honestly, not faked)

| Local version | Portal version | Why |
|---|---|---|
| Trend arrows ▲▼= per card | `atualizada dd/mm` + green dot on the newest day | Arrows need `time_in_status` = one call **per task id** → dataset chaining, which the platform doesn't do |
| Companies delta (`−1`) | live total, labelled "total atual — sem histórico por dia" | `amasty_company_account_company` has **no date column at all** (verified) and the portal persists nothing |
| Contacts delta from `history.json` | `+7` novos from `customer_entity.created_at` | **Better** than the local version — works for any past day, not just days someone ran the script |
| `company_map` dataset + client-side join | `company_name` resolved in SQL | Safe: **0 customers belong to >1 company** (verified), so the LEFT JOIN can't fan out (32 orders = 32 rows either way) |
| `history.json` for "1ª compra" | `COUNT(DISTINCT company_id)` client-side | Day-accurate for any selected date; server-side would only know "as of now" |
| localStorage tile order | session-only drag + "⟲ Ordem padrão" | Portal runs in `<iframe sandbox>` — no localStorage |

### ClickUp `rest` block gotchas (learned the hard way, 2026-07-28)
- **A ClickUp API token MUST be registered in the portal — there is no way around it.** `rest`
  datasets are credential-backed and the manifest is forbidden from carrying tokens, so the portal
  asks once. "The platform already has a ClickUp connection" means the *connector* exists (ClickUp is
  offered on the Sistemas page), **not** that a key is stored.
  **Getting the token:** avatar (upper-right) → Settings → Apps → **API Token** → Generate, or go
  straight to <https://app.clickup.com/settings/apps>. It starts with `pk_` and **never expires**.
  ⚠ **Not** OAuth: <https://developer.clickup.com/reference/getaccesstoken> is a dead end for this —
  it needs `client_id`/`client_secret`/`code` from a registered OAuth app, and the docs state
  outright that "applications utilizing a personal API token don't use this endpoint".
  The `pk_` token goes **only** into the portal (encrypted there) — never into `.env`, the manifest,
  or any file in this repo.
- **`credentials: shared` belongs in the `.md` FRONTMATTER, not inside the ` ```rest ` block.**
  Inside the block it had no effect and the portal fell back to per-user keys ("Este dashboard puxa
  dados com a sua chave de API… Falta 1 chave(s)"). In the frontmatter it makes the dashboard a team
  resource: one token serves everyone. **Dead end worth remembering:** removing the line entirely
  does *not* silence the prompt — it makes it worse (every viewer gets asked for their own key).
  `portal_jem_salesrep.md` carries it inside the block, i.e. probably silently per-user too.
- **No `subtasks` param at all.** ClickUp treats the mere *presence* of `subtasks` as "include them",
  so `subtasks: false` can still pull subtasks in; the default (param absent) already excludes them.

### Paridade com a versão local (2026-07-29, *"replique esse mesmo dashboard"*)

Portado (só `.html`, nada de dados mudou): **barra de filtro do quadro** centralizada e destacada em
teal dentro do tile (o filtro de status saiu do cabeçalho para ela, mesmo lugar e mesmo peso da
local) · **status no rodapé do cartão** com a bolinha na cor do próprio ClickUp — antes o cartão
mostrava a lista de origem, que virou tooltip do título; sem isso, filtrar por um critério que não
aparece no cartão obriga a adivinhar · bolinhas também nas opções do filtro · popover centralizado
sob o botão · coluna vazia com o mesmo cartão tracejado "—" · rótulo do filtro do topo em teal.

**Não portável, e por isso declarado na tela em vez de simulado:** o seletor de **data do quadro**.
Onde a local tem o `<input type=date>`, aqui há uma etiqueta fixa *"estado atual · sem histórico por
dia"* com o motivo no tooltip. Remontar um dia passado exige `time_in_status` **por tarefa** — a
mesma parede das setas (§9). Duas alternativas foram consideradas e recusadas: seletor desabilitado
(sugere que um dia funciona) e um filtro por `date_updated` fingindo ser histórico (o quadro
pareceria passado sem ser). **Se a publicação diária do `data.json` num URL interno sair (§9, questão
2), o portal ganha data E setas de uma vez** — o `data.json` local já carrega o histórico normalizado
desde §2a, então é só ler.

**Diferença deliberada que sobrou:** a paleta clara. O portal usa papel quente (pedido dela:
*"esse branco tá desconfortável"*), a local segue fria + tema escuro. Unificar é trocar os tokens
neutros de um `:root` pelos do outro — nada de layout muda. Não foi feito por conta própria porque
os dois lados são pedido explícito dela, em momentos diferentes.

**Prévia local sem publicar:** `portal_test/` já monta a página com dados reais —
`python run_manifest.py && python make_fixtures.py`, depois `python -m http.server 8790` dentro de
`portal_test/site` e abrir `http://127.0.0.1:8790/index.html`. É o `fetch('data/*.json')` do portal
resolvido por arquivo, então o que aparece é o que o portal renderiza.

### Other deliberate differences
- **"Hoje" = `db_today`** (the DB clock, UTC), not Phoenix. That's the clock `created_at` is stored
  in, so both sides of the comparison agree. The local build used Phoenix — the two can disagree for
  orders placed after 17:00 Phoenix. (DB `NOW()` was 21:07 UTC when local was ~18:07.)
- **The ClickUp board is always the CURRENT state**, even with a past date selected (a pill in the
  tile head says so) — there's no status history without `time_in_status`.
- **Unmapped statuses are surfaced**, not swallowed: a new ClickUp status shows as a ⚠ footer note
  with its name and count instead of silently vanishing from the board.
- **Two ClickUp payload shapes are handled**: the raw REST v2 shape (`status` as an object, with
  `date_updated`/`date_done`) *and* a compact shape (`status` as a plain string, no `date_updated`)
  — the MCP tools return the latter, so the tolerance is real, not speculative.

### Verification (2026-07-28) — 49/49 assertions
`build`-free harness in the scratchpad: the ` ```mysql ` blocks were extracted **from the manifest
itself**, run against live Magento, and fed to the page's own `<script>` under a minimal DOM stub in
Node.
- **Reconciles exactly with the "Report 27 de Julho"**: pedidos no dia 32≡32, pedidos no mês
  449≡449, destaque `$6.392,75 · #JEMUS000002914 · Briscoe Protective - Pye-Barker NY`.
- Totals `2.993 / 12.036` ≡ reference; "Companies com 1ª compra" 415 as of 27/07 (416 incl. 28/07).
- Volumes/timings: `mkt_orders` 3.004 rows / 0,65s · `mkt_novos_contatos` 156 / 0,13s.
- Error paths asserted: ClickUp key missing → explanatory box + red source pill, **Magento still
  renders**; Magento down → the two data tiles degrade, **ClickUp still renders**.

The harness now lives in **`portal_test/`** (`README.md` there has the 3 commands). It re-extracts
the SQL from the manifest on every run, so it catches a broken query edit. ⚠ It asserts **frozen
literals only for 27/07** (past data); the live figures (order count, companies/contacts totals,
`db_today`) drift daily and are asserted as *relationships and floors* instead — the first version
hardcoded them and self-failed within hours. Keep that distinction.

---

## 9. STATE — read this first next session

### 🔴 A MUDANÇA DE PASTA QUEBROU O REFRESH (achado em 26/08/2026, NÃO consertado)

O projeto **saiu** de `C:\Claude\nsaw-dash-migration\JEM Marketing Daily Report` e agora vive em
`C:\Claude\Projects\JEM Marketing Daily Report` (repo git novo, remoto
`github.com/maynaraamaral-bit/mkt-daily-report`, 1 commit). `C:\Claude` hoje tem só `Projects` e
`Skills`. Duas coisas ficaram para trás, ambas **medidas**, não deduzidas:

1. **A tarefa agendada ainda aponta para a pasta antiga.** `Get-ScheduledTask "JEM Marketing Daily
   Report"` devolve `Execute = C:\Claude\nsaw-dash-migration\...\refresh_scheduled.cmd`, que não
   existe mais. `LastTaskResult = 2147942667` (**0x8007010B, "nome de diretório inválido"**) na
   execução de 26/08 18:40 — ou seja, o job **não chega nem a rodar**, e a falha não é a de rede das
   22:00. Conserto = re-registrar a tarefa apontando para o caminho novo (o `.cmd` continua igual);
   é mexer em agendamento do computador dela, então **é decisão dela**.
2. **O `.env` compartilhado não foi movido.** `C:\Claude\Projects\.env` não existe (procurado em todo
   `C:\Claude`). Sem ele, `build_data.py` e `portal_test/run_manifest.py` não têm credencial nenhuma
   — **nem rodando na rede da JEM**. O arquivo nunca esteve no git (correto), então ele só pode vir
   de onde ela guardou. ⚠ Ela já reportou uma vez esse arquivo como "vazio" quando não estava
   (editor mostrando buffer mascarado): **se acontecer de novo, avisar para NÃO salvar dessa aba** —
   um Ctrl+S em buffer vazio apaga as credenciais de Magento/NetSuite/TaxJar/ClickUp.

Enquanto os dois não forem resolvidos, o `data.json` fica parado em **24/08 17:00** e a faixa âmbar
de dado velho (§9, pane de 26 dias) é o que aparece na tela. A faixa está funcionando — é
exatamente para isto que ela foi feita.

### 🔴 A PANE DE 26 DIAS (30/07 → 23/08/2026) — causa raiz achada em 24/08

**Sintoma relatado pela Maynara (24/08):** *"todos os dados de magento estão como arquivo e travados
no dia 29/07"*. Estavam: `data.json` era de 29/07 19:35.

**Causa raiz: o banco do Magento só aceita conexão do IP de saída da rede da JEM, e o job das
22:00 roda quando ela está em casa.** Nunca foi bug de código, credencial ou agendamento.

Prova, toda ela reproduzível:
- As **17 execuções** de 30/07 a 23/08 falharam com o MESMO erro: `(2003, "Can't connect to MySQL
  server on '209.151.154.185' (timed out)")`. **Timeout, nunca "Access denied"** — pacote descartado
  por firewall, não recusa de senha. Se fosse credencial, o erro chegaria na hora.
- Em 24/08, **da rede da JEM ("JEM Guests", IP de saída 67.159.238.251), conecta em 0,1s** e a query
  roda inteira. Nada no repo mudou nesse meio-tempo.
- O grant do MySQL é `prd_db@%` (**não** restrito por host), então o bloqueio é de **firewall de
  rede**, camada abaixo do MySQL — é por isso que dá timeout em vez de erro de permissão.
- Correlação fechada com o log `Microsoft-Windows-NetworkProfile/Operational` (retém 30 dias):
  **a única execução OK (29/07 14:30) é a única em que a máquina estava na "JEM Guests"**; ela
  trocou para o Wi-Fi de casa em 30/07 11:04 e todas as execuções seguintes falharam.
- ⚠️ **17/08 era a noite que teria funcionado** (ela estava na JEM às 22:00) — mas a máquina dormiu
  às 19:53 e a tarefa não disparou. A recuperação (`StartWhenAvailable`) rodou em 18/08 11:31 e foi
  **morta no meio** sem gravar nada. Ver a causa das mortes no item de bateria abaixo.

**Consertado em 24/08 (sem precisar de ninguém de fora):**
1. **Dados atualizados** — `python build_data.py` rodou da rede da JEM: 3.460 pedidos YTD, ClickUp
   ao vivo (186 tarefas na view, 62 chamadas de histórico), `board-2026-08-23.json` gravado.
2. **Tarefa agendada endurecida** (`Set-ScheduledTask`):
   - `DisallowStartIfOnBatteries` e `StopIfGoingOnBatteries` estavam **`True`** (o default do
     Windows, herdado da criação em 29/07). Isso **impedia a tarefa de iniciar na bateria** e
     **matava a execução em curso se o notebook fosse desconectado da tomada** — é a explicação
     das execuções que só gravaram "iniciando refresh" e nada mais (02/08, 14/08, 18/08). Ambos
     agora `False`.
   - `RestartCount=5` / `RestartInterval=PT20M`: falhou, tenta de novo por ~1h40 (cobre uma
     reconexão de rede). **Não** resolve estar fora da rede da JEM — só aproveita se ela voltar.
   - **Gatilhos: 12:00, 17:00 e 22:00** (era só 22:00). Em horário comercial ela está na rede da
     JEM, que é a única janela em que o job PODE funcionar. Rodar 3× ao dia é seguro: o script
     recalcula tudo do zero, `history.json` é uma entrada por dia civil (a última vence) e a base
     do quadro é sempre a reconstrução de **ontem**, determinística.
3. **Faixa de aviso de dado velho no `dashboard.html`** (`#staleBar`). Passou 26 dias sem ninguém
   notar porque a única pista era `Last execution` em texto miúdo. Agora, acima de **28h** sem
   refresh (= um dia inteiro de tentativas perdido) aparece faixa âmbar no topo, e acima de 48h
   ela fica vermelha, dizendo quantas horas/dias e que o refresh só alcança o banco pela rede da
   JEM. Tokens `--gold-*`/`--red-*`, que já têm par claro/escuro (o `board_test.mjs` exige).
4. **`connect()` do `build_data.py`**: 3 tentativas com 15s de intervalo e, ao desistir, erro que
   **nomeia a causa** ("timeout = firewall = provavelmente fora da rede da JEM; não é
   credencial"). O traceback cru mandava quem lê investigar senha, que era o único ponto certo.

**O que NÃO está resolvido:** enquanto o job viver no notebook, ele só funciona nos dias em que ela
estiver na rede da JEM com a máquina acordada. Não existe conserto local para isso.

### ✅ DECIDIDO 24/08: **fica no notebook, como está.** E **n8n está FORA** — a JEM vai parar de usar

Ofereci três caminhos: (1) mover o job para o n8n, (2) pedir à TI liberação do IP de casa/VPN,
(3) aceitar o notebook com os 3 gatilhos + a faixa de aviso. Ela escolheu 1, e **em seguida
voltou atrás com um motivo que encerra o assunto**: *"melhor deixar como está. vamos deixar de
usar o n8n em breve, não vale a pena esse esforço."*

**Consequência prática — o comportamento aceito, não um defeito a consertar:** o refresh roda nos
dias em que ela está na rede da JEM com a máquina acordada (3 tentativas/dia + 5 repetições), e
nos dias em que não roda **a faixa de dado velho diz na cara** há quantas horas/dias parou. Isso é
a decisão dela, com o trade-off na mesa. **Não reabrir propondo servidor/VPN/host novo** sem ela
pedir.

⚠️ **n8n saiu do mapa de infraestrutura deste repo.** Ele aparecia como "candidato mais forte"
para hospedar o encadeamento das **setas do portal** (§9) — essa recomendação está **morta**, e as
duas menções restantes no arquivo estão marcadas como obsoletas. A questão das setas do portal
volta a não ter candidato: se alguém retomar, **descubra primeiro o que vai substituir o n8n**, em
vez de reciclar o desenho antigo.

Para o registro, do que se apurou antes dela voltar atrás: n8n era real e ativo na JEM (5 tarefas
de flow no ClickUp — Credit Limit + Magento, TaxJar, Inventory, Invoice, Tax) e já alcançava
Magento e NetSuite, mas **não havia nenhum dado de acesso a ele no repo** (nem URL, nem host, nem
chave, procurado em `../.env` e em todo `C:\Claude`).

### ⚠ Duas descobertas laterais achadas na investigação (nenhuma causada por ela)

1. **O relógio do servidor de banco está em UTC+2, e o `created_at` segue esse relógio.**
   Medido em 24/08: `NOW()`=18:29, `UTC_TIMESTAMP()`=16:29 (2h de diferença), e o relógio da
   máquina dela está **certo** (+1s contra hora da internet). O `build_data.py` compara a data
   **Phoenix (UTC−7)** com a string `created_at` (UTC+2) — 9h de defasagem. Efeito prático:
   pedidos feitos entre 00:00 e 08:59 UTC+2 (= fim da tarde/noite Phoenix do dia anterior) caem no
   dia seguinte. **37 de 512 pedidos (~7%) desde 25/07** estão nessa faixa.
   **Não mexi**: em 28/07 a reconciliação com o "Report 27 de Julho" bateu exata (32≡32, 449≡449)
   com essa mesma lógica, e trocar a regra de dia mexe em todo número que ela já validou. É
   pergunta de negócio ("que dia é 'hoje': o de Phoenix ou o do banco?"), não bug óbvio.
   ⚠ Em 28/07 o `NOW()` do banco batia com UTC (registrado no §8) — ou seja, **o fuso do servidor
   parece ter mudado depois disso**. Se for confirmado, vale perguntar à TI.
2. ⚠ **Reconferido em 26/08: agora são 52 passam / 6 falham** (nada a ver com as edições de 26/08,
   que só tocaram os arquivos do portal — `git status` confirma). A 6ª é
   *"título malicioso sai escapado no cartão"*, e **não é falha de escape**: medido com debug, o
   payload cru (`<script>alert`) **não** aparece no HTML e o cartão injetado simplesmente **não é
   renderizado** (a reconstrução por dia o descarta), então a 1ª metade da conjunção falha sozinha.
   O `esc()` continua passando no teste unitário. Conserto honesto = injetar a tarefa de um jeito
   que ela realmente entre no quadro; é asserção dela, não mexi.
   **`board_test.mjs`: 58 asserções, 53 passam, 5 falham — as 5 são as asserções congeladas de
   27/07, e o mecanismo está CERTO.** (Eram 47; **+11 cobrindo a faixa de dado velho**, incluindo
   o caso real "26 dias parados acende a faixa vermelha". Duas dessas 11 pegaram defeito no
   próprio teste antes de passar: o `El` do stub **não liga `className` a `classList`** como o
   navegador liga, então asserção via `classList.contains` passava vazia — a de "âmbar não é
   vermelha" era tautologia. Leia `className`, que é o que a página escreve.) É exatamente o piso do `since` documentado no §2a: `since` é
   a **última** entrada em cada status, então a reconstrução de dias antigos apodrece sozinha.
   Prova no `task_log.py 868ggetw0`: o `ready to deploy` da Bulk Pack, que em 29/07 marcava
   27/07 15:51, hoje marca **18/08 10:07** — a tarefa voltou por lá em agosto. O cartão é marcado
   **`?` (incerto)**, que é o comportamento correto ("seta errada é pior que seta nenhuma"): a
   asserção que falha é literalmente *"NÃO é marcada como incerta em 27/07"*.
   **Não reescrevi as asserções** — mexer no que um teste afirma é decisão dela, e o harness é o
   portão de verificação dela. O conserto honesto é reancorar essas 5 no invariante que não expira
   ("ou reproduz a etapa registrada, ou é marcada incerta — nunca erra calado") em vez de num dia
   fixo. As outras 42, inclusive a paridade de tokens claro/escuro, passam.
   ⚠ Nada disso tem relação com as edições de 24/08: o harness não referencia `setHours`,
   `staleBar` nem `lastExec` (0 ocorrências).

### ONDE PARAMOS — fim do dia 2026-07-29

**A decisão que está aberta, e é por onde começar:** Maynara perguntou *"ao invés de comparar data,
não poderíamos somente fazer via mudança de task?"*, sobre as setas do portal. Foram apresentadas 3
formas e ela **não escolheu ainda**. O que já está apurado (não precisa re-investigar):

- **A direção do movimento NÃO sai da tarefa como o portal a vê.** O payload tem status atual +
  `date_updated` ("mexeu"), nada do status anterior. `fail - stg` hoje não distingue "voltou de PRD"
  de "sempre esteve aqui". Beco sem saída já verificado 3×; não oferecer heurística.
- **Opção 1 — webhook `taskStatusUpdated`:** o evento carrega o antes→depois, então a direção vem de
  graça, sem snapshot e sem data. ⚠ **Verificado em 29/07: a nossa chave ENXERGA a API de webhooks**
  (`GET /team/31082060/webhook` responde, 0 registrados). Custo: exige endpoint HTTPS **público** para
  o ClickUp postar (mais exigente que servir arquivo) + validação de assinatura, e ainda precisa
  gravar em algo que o portal leia. ~~Lugar natural: n8n (tem gatilho de webhook).~~
  ⚠️ **OBSOLETO (24/08): a JEM vai parar de usar o n8n** — não existe mais "lugar natural" para
  isso. Ver a decisão no topo do §9.
- **Opção 2 — guardar a coluna anterior num campo customizado da tarefa:** zero hospedagem, o quadro
  já devolve `custom_fields` (⚠ verificado: **20 campos visíveis** nessas tarefas, inclusive
  `BASELINE_status`/`BASELINE_due_date`, que são do recurso **nativo** de baseline do ClickUp, não
  nossos). Custo: escrever diariamente em ~40 tarefas do time de dev **bumpa o `date_updated` de
  todas** — mata o "atualizada dd/mm" e o ponto verde do cartão — e polui o feed deles. Precisa criar
  campo (admin) e aval do time. Não fazer sem isso.
- **Opção 3 — estado corrente por tarefa em vez de snapshot datado:** um arquivo único com "última
  coluna conhecida de cada tarefa", reescrito a cada execução. É o que **elimina a lógica de data**
  (regra de validade de 3 dias, fuso, estado "base velha") sem mexer em infra nenhuma; a seta passa a
  significar "mudou desde a última leitura", e a data vira informação na tela, não regra.
  **Recomendação registrada:** se o incômodo é a lógica de data, é esta.
- **Nenhuma das três elimina a peça 2** (algo fora do portal tem de guardar e servir). A opção 3
  elimina só a complexidade de data, que é o que ela questionou.

**O que precisa ser publicado no portal** (mudou hoje, dos dois lados): **`.md` E `.html`**. O `.md`
mudou de verdade (3 datasets de ClickUp em vez de 1, + a seção "Preservar o log do dia anterior").

🔴 **Atualização 26/08: os dois arquivos mudaram DE NOVO e nenhum foi publicado ainda.** O `.md` está
no **formato verificado** (frontmatter + corpo YAML — o formato antigo, que estava no ar, é o que
**não roda**), e o `.html` ganhou busca no quadro + tema do sistema. Se a versão publicada hoje é a
antiga, **republicar os dois é o que faz o dashboard funcionar de fato**, não um refinamento.

**O que está rodando sozinho:** a tarefa agendada das 22:00 chama o `build_data.py`, que desde hoje
também grava `board_baseline/board-AAAA-MM-DD.json`. Amanhã deve existir o `board-2026-07-29.json`
além do `board-2026-07-28.json` gerado hoje à mão — **conferir isso é a checagem de 30 segundos** que
prova que a retenção de 7 dias está funcionando.

**Prévia local do portal sem publicar** (o servidor da sessão de hoje morreu junto com ela):

```bash
cd portal_test && python run_manifest.py && python make_fixtures.py
cd site && python -m http.server 8790     # abrir http://127.0.0.1:8790/index.html
```

**Verificação (rodar antes e depois de qualquer mexida):** `node board_test.mjs` (local, 47) ·
`cd portal_test && node test_portal.mjs` (portal, **180** desde 26/08 — lê o `.html` de origem, não a cópia em `site/`, e afere o formato do `.md`). O do portal fica verde sem rede; o local tem 6 falhas conhecidas e explicadas (asserções congeladas, ver adiante).

**Fora do escopo até alguém pedir:** GA4 (Nº de acessos / Taxa de conversão) e unificar a paleta clara
do local com o papel quente do portal.

### Decisions taken 2026-07-29 (supersede parts of §2 and §8)

1. **DONE — the board is mirrored from the ClickUp go-live BOARD VIEW, not from "all active tasks".**
   Maynara: *"vamos replicar exatamente o que está no board mesmo que as tarefas de exemplo do print
   saiam"* — i.e. losing reference-report tasks (e.g. Bulk Pack, which lives in **Hyvä Backlog** and
   therefore cannot appear in a view scoped to the Incident list) is **accepted**. Target view:
   <https://app.clickup.com/31082060/v/b/6-901112863157-2> → id `6-901112863157-2` (`6` = list, so
   it's a list-level view on `901112863157`). This replaces the hand-maintained status→column
   curation for columns 1–4: the team's own view filters become the source of truth.
2. **Column 5 "Conclusões mais recentes (PRD)" stays, fed from the LIST with `include_closed`** — a
   work board normally hides closed tasks, so it can't come from the view. Hybrid by design.
3. **`CLICKUP_TOKEN` — approved AND in place** (pasted 2026-07-29, 45 chars, `pk_` prefix).
   ⚠ Never ask for a token in the conversation; she pastes it into `../.env` herself. Two friction
   points worth remembering: there was **no slot** for it (I appended a commented `CLICKUP_TOKEN=`
   block, mirroring the file's style) and she mistook the **commented-out `#SALESFORCE_TOKEN=`
   placeholder** for the ClickUp field. She also reported the file "empty" — it wasn't (verified:
   1914 bytes, 12/12 keys with values); her editor was showing a stale/masked buffer. **If that
   happens again, warn her NOT to save from that tab** — a Ctrl+S on an empty buffer would wipe the
   Magento/NetSuite/TaxJar credentials. `notepad` sidesteps extensions that mask `.env`.
4. **Portal arrows: deferred, not dropped.** Asked where the portal should read the day-before
   baseline from; she answered *"não sei / descobrir depois"*. So: build the view-based board now
   **without** arrows in the portal, keep the baseline hook pluggable, and revisit when a
   destination exists (internal URL via `connector: http` is the clean option; a dedicated ClickUp
   "control task" holding the baseline as a comment is the no-hosting fallback, `select: comments`).
   Arrows in the **local** dashboard are unaffected and become automatic with the token.

### Probe results (2026-07-29) — the view change is DONE and verified

`probe_clickup_view.py` answered everything; the portal `.md`/`.html` and the harness were updated
accordingly (53/53 assertions). What it found, all of it load-bearing:

- **The browser-URL id works verbatim in the API.** `6-901112863157-2` is a *required view* of type
  `board` on list `901112863157`. No translation needed. (The other views have ids like
  `xmhjc-176111`, so this was worth checking.)
- **The view has NO field filters** — `filters.fields: []`, grouping by `status`,
  `show_closed: false`, `show_subtasks: 1`.
- **`GET /view/{id}/task` ignores `show_closed`**: it returned **169 tasks, 133 of them `Closed`** —
  tasks the board itself does not display. This is what lets column 5 stay alive **without** a
  separate list query, so decision 2 above is satisfied more simply than planned. It's also a
  deliberate divergence from "exactly what the board shows", and the tile footer says so.
- **The view spans 3 lists** — `Incident Support | Go-Live`, **`Hyvä Backlog`** and
  **`Sprint 16 (2/2 - 2/15)`** — because the team added those tasks to the go-live board (ClickUp
  multi-list). So **Bulk Pack IS in the view**: the feared loss of the reference-report tasks did not
  happen. Decision 1's "even if the print's tasks drop out" turned out not to cost anything.
- **It hides nothing from the parent list** (65 tasks, 0 hidden) — it *adds*. The narrowing comes
  from no longer pulling the whole Hyvä Backlog: active tasks went ~46 → **36**.
- **No subtasks** in the response (0 with `parent`), so the old `subtasks` param worry is moot here.
- **Payload is raw REST v2** (`status` as object, `date_updated`/`date_done` present).
- **Works without the `page` param** (returns page 0), 30 per page. ⚠ **`last_page` is unreliable on
  this endpoint** — it stays `False` even on the last page, so paginate by "stop when a page brings
  nothing new", never by trusting `last_page`.
- ⚠ **The endpoint times out sporadically** — a full sweep succeeds, the next one blows past 45s.
  `make_fixtures.py` has retry+backoff for this; anything else that calls it needs the same.

### The old probe instructions (kept — re-run it whenever the board's config changes)

`probe_clickup_view.py` (in this folder) answers everything the view change depends on in one run,
and needs only the token. It is **read-only** (no POST/PUT) and stdlib-only:

```bash
C:/Users/MaynaraAmaral/anaconda3/python.exe probe_clickup_view.py
```

It prints: (1) the views on both lists **with the ids the API actually accepts** — the browser-URL
fragment may not be one of them; (2) the board view's real `filters`/`grouping`, i.e. the team's
criterion we've been reimplementing by hand; (3) exactly which tasks the view returns, whether any
are closed/done (decides whether decision 2 above is really needed), which lists appear, and whether
Bulk Pack is in there; (4) the **diff against the full list** — what the view hides, which is what
would drop off the board. Do not touch the manifest or the HTML before reading its output.

### The standing constraint: zero recurring manual steps

Maynara's goal, stated plainly: **"quero automatizar coisas e não precisar fazer absolutamente nada
manual."** Treat it as a hard design constraint. It rules out the old "via MCP" mechanism outright —
**MCP requires a human in a Claude conversation, so it *is* the manual step.** Don't cite the
2026-07-28 "vamos seguir tudo via MCP" decision as settled; it predates this goal and conflicts with it.

Distinguish **one-time setup** (she accepts it: pasting a token once, registering a key in the portal)
from **recurring manual work** (she does not).

`CLICKUP_TOKEN` — **resolved 2026-07-29**, in `../.env`, local dashboard automated and scheduled (§6.2).

> 📌 **As instruções de preservação do log de ontem moram no `portal_jem_marketing_daily.md`**, seção
> *"Preservar o log do dia anterior"* — por decisão da Maynara (29/07), elas viajam com o arquivo
> publicado, não aqui. Não duplique: se a regra mudar, mude lá. O que está lá: formato (uma linha por
> tarefa, chave = id, `col` 1→5, `refere_se_a` repetido em toda linha porque o `select` descarta o que
> está fora do array), as 5 regras de preservação (a crítica: sobrescrever a URL de ontem faz **toda**
> seta virar `=`, que é plausível e por isso invisível), e o bloco `connector: http` pronto, indentado
> de propósito para a plataforma não executá-lo — verificado que o parser continua vendo 3 `mysql` +
> 1 `rest`.
>
> **Still unanswered, and the only thing blocking portal arrows:**
> *Existe uma URL interna onde a gente possa publicar/servir um arquivo por dia?*
> Framing that landed best with her: such a URL doesn't have to be mere storage — **a service we host
> can do the per-task chaining and return the board with the arrows already computed**, and the portal
> can read from whoever chains even though it cannot chain itself. ~~Strongest candidate is **n8n**,
> which JEM already runs for the NetSuite↔Magento integrations.~~
> 🔴 **O candidato n8n MORREU em 24/08** — decisão dela: *"vamos deixar de usar o n8n em breve, não
> vale a pena esse esforço."* O raciocínio acima (quem hospeda encadeia, e o portal lê o resultado)
> **continua válido**; o que não existe mais é o host. **Não proponha n8n de novo.** Quem retomar
> isto precisa primeiro descobrir o que vai substituí-lo na JEM.
> ⚠ Note the Magento DB host is a **public IP**, i.e. the portal's server is not
> on her LAN — **her machine cannot be the host**. Also flag the security angle: an open webhook would
> expose task titles.

### What the token unlocked, and what it still doesn't

| | Status | |
|---|---|---|
| **Local `dashboard.html`** | ✅ **Done** — fully automatic, arrows included. `clickup_client.py` pulls the view + `time_in_status` per active task, computes the 1→5 ordinal, rewrites `data.json`; scheduled daily. No human. | §2, §6.2 |
| **Local board: any past day + status filter** | ✅ **Done 2026-07-29** — the same per-task history that feeds the arrows is shipped in `data.json`, so the tile remounts the board for any day in the last 60 and filters by status, client-side. | §2a |
| **Portal arrows** | ⏳ **Código pronto nos dois lados desde 29/07; falta só a URL.** `build_data.py` grava `board_baseline/board-AAAA-MM-DD.json` (estado às 23:59:59 de ontem, 7 dias retidos, sem títulos de tarefa) e o `.html` do portal já lê o dataset `board_baseline` — ausência dele não é erro, só não desenha seta. Ativar = publicar o arquivo diário numa URL alcançável e des-indentar o bloco no `.md`. | §8, box abaixo |
| **Portal board by date** | ❌ **Blocked by the same wall as the arrows** — a per-day board needs the per-task history, i.e. one request per task. The portal's **status** filter already exists (§8) and is unaffected. | §8, §9 |

### The trend-arrow logic is settled — only the data source is open

Maynara independently proposed the exact mechanism already implemented locally, and it's correct:
number the columns **1** Em andamento · **2** Prontas STG · **3** Aguardando Deploy · **4** Prontas
PRD · **5** Conclusões (5 shows a date, not an arrow). Compare today's ordinal to yesterday's:
higher = ▲ green, lower = ▼ red, equal = `=`. Her own example checks out (Bulk Pack sat at 3).

**The blocker is never the numbering — it's where yesterday's ordinal comes from.** Three candidates,
all investigated:
1. **The live ClickUp payload** — ❌ dead end, verified twice. It carries current status +
   `date_updated`/`date_closed`/`date_done`, nothing about the previous status. History exists only
   behind a **per-task** endpoint.
2. **The portal remembering** — ❌ by design (fresh snapshot each refresh; sandboxed iframe, no
   localStorage).
3. **Something feeding it the baseline** — ✅ the only way. Two automatic variants:
   - **A. Publish a JSON daily to an internal URL**, read via `connector: http` (absolute URL).
     Touches nothing in ClickUp. **Needs an HTTP-reachable location — that's open question 2.**
   - **B. Write yesterday's ordinal into a ClickUp custom field.** No hosting needed (the existing
     `rest` call already returns `custom_fields`), but it **writes into the dev team's ClickUp**
     (~47 tasks/day in their activity feed) and **bumps `date_updated` on every task**, which would
     destroy the "atualizada em" indicator and any updated-ordering. Not her call alone — needs the
     dev team. Prefer A.

⚠ **Do not offer a heuristic** (e.g. "task sits in `fail - stg` ⇒ regressed"). It was considered and
rejected: the two real regressions from the first pull ("Fallback and Notification" PRD→STG,
"Dashboard Credit Limit" reopened from *approved by qa*) are exactly the cases current-status-alone
cannot distinguish from "was always here". A wrong arrow is worse than no arrow.

### Portal publish state — both files need re-uploading (as of 2026-07-29)

Rule of thumb worth repeating to her: **`.md` = the data the server executes, `.html` = the screen.**
A visual-only change needs only the `.html`.

**`.md` changes:** the two list datasets collapsed into the single `clickup_golive_board` view
dataset; `subtasks` dropped from `query`; `credentials: shared` **back inside the ` ```rest ` block**
with the H1 as the first line — the YAML document frontmatter experiment was reverted (see the
`rest` gotchas above; the platform spec says "comece com um título em # (H1)", and Maynara reported
the file "não está certo" while the frontmatter was there).

**`.html` changes:** board rebuilt from the view · **light/dark theme toggle** (☾/☀, opens light,
session-only — no localStorage in the sandbox; only flips `data-theme`, and the SVGs read
`var(--teal)`/`var(--card)` so nothing is redrawn) · **multi-select status filter**, que em
**2026-07-29 saiu do cabeçalho do tile para a barra `.kfilters`** dentro dele (paridade com a local,
ver "Paridade" acima) — o `test_portal.mjs` procurava o botão em `extra-tasks` e acusou a mudança;
as asserções foram movidas para `body-tasks` e ganharam companhia (barra presente, escopo declarado,
status + bolinha no cartão): **91 asserções, 0 falhas**. Opções derivadas dos status realmente
presentes, com contagem, agrupadas por coluna;
`backlog`/unmapped shown under "Fora do quadro"; the footer declares how many tasks are hidden and
that the board is not the total) · centred filter bar · warm paper palette (`--bg:#f4f1e9`,
`--card:#fffdf8`, plus `--panel`/`--card2`/`--grid` so the theme can switch what used to be
hard-coded hex) — she asked for that one: *"esse branco tá desconfortável."*

### Also asked for, already delivered
- A one-sentence explanation for stakeholders on why the portal has no arrows: *"As setas comparam
  onde a tarefa está hoje com onde ela estava ontem, e o portal não guarda histórico — ele refaz
  todas as consultas do zero a cada atualização, então não existe um 'ontem' para comparar."*
- The ClickUp token path: `https://app.clickup.com/settings/apps` → API Token → Generate (`pk_`,
  never expires). **Not** `developer.clickup.com/reference/getaccesstoken` — that's the OAuth-app
  flow and the docs say personal-token users don't use it. She found that page and it's a dead end.

### Open, unchanged
- **GA4** for Nº de acessos + Taxa de conversão — still no source (tiles stay out, note in their place).
- ~~**`dashboard.html` (local) left-aligned filter**~~ — **resolvido 2026-07-29**: as duas barras
  (dia do relatório e quadro) agora são **centralizadas**, e a do quadro ganhou destaque em teal
  (*"deixe os filtros em mais destaque e centralizados"*). A do topo foi centralizada junto por
  coerência — se ela preferir de volta à esquerda, é um `justify-content` em `.filters`.
- **Paleta clara ainda é a fria** (o portal usa papel quente). Não foi perguntado de novo: com o
  tema escuro disponível (§3), o desconforto com o branco pode já estar resolvido. Se quiser
  alinhar, é só trocar os tokens neutros do `:root` claro pelos do portal — nada de layout muda.
- **Board window = 60 days** (§2a). Raising it is one constant, but the pull cost grows with the
  number of tasks closed inside the window (it was 30 of 133 at 60 days; all 133 would be ~169 calls,
  ~3 min per refresh). Only raise it if she actually asks to look further back.
