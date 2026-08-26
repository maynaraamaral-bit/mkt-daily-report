"""Refresh script for the 'JEM Marketing Daily Report' dashboard.

Pulls live Magento data (pymysql) and computes every KPI show in the "Report 27 de
Julho" reference: site/sales snapshot (Companies, Contacts, orders, revenue,
highlight order) + a 6-month trend. Day-over-day deltas (the small "+18"/"-1" chips)
need YESTERDAY's snapshot, which Magento doesn't retain on its own -- so this script
keeps a tiny running history file (history.json) and diffs against it. On the very
first run (no prior entry) deltas come back as null and the dashboard shows "-".

Money = "amount" = subtotal + discount_amount (pure sale value, net of discount,
EXCLUDING shipping and tax -- per Maynara 2026-07-28; grand_total was dropped
because it mixes those non-sale-value amounts in). See orders_ytd.sql.

O quadro do ClickUp é montado AO VIVO por `clickup_client.py`, usando `CLICKUP_TOKEN`
do `../.env`: puxa a view "Board" do go-live e o histórico de status de cada tarefa
ativa, então as setas de tendência (▲▼=) saem reais e o script roda agendado sem
ninguém no meio. Sem token, cai para `clickup_snapshot.json` (pull manual antigo) e,
por último, para a cópia estática abaixo -- e a origem sempre aparece na tela.

O que vai para o data.json são as tarefas CRUAS com o histórico de status junto, não as
colunas prontas: assim o dashboard remonta o quadro para qualquer dia dos últimos
`clickup_client.HISTORY_WINDOW_DAYS` (filtro de data do quadro) e filtra por status sem
consultar nada -- mesma ideia dos pedidos do Magento.

"Acessos hoje" / "Taxa de conversao hoje" are NOT available from the Magento DB:
`customer_visitor` only retains ~8 days and undercounts the reference figure by ~2x
(likely GA4-sourced in the original report; `amasty_ga4_client_data` only stores
order-attribution client IDs, not raw traffic). Left null until a GA4/analytics
source is connected -- see CLAUDE.md.

    python build_data.py
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

import pymysql

import clickup_client

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
QUERIES = HERE / "queries"
HISTORY_PATH = HERE / "history.json"
PHOENIX = timezone(timedelta(hours=-7))  # America/Phoenix is MST year-round (no DST)
HISTORY_KEEP_DAYS = 60


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


CONNECT_ATTEMPTS = 3
CONNECT_BACKOFF_S = 15


def connect() -> pymysql.connections.Connection:
    """Conecta no Magento, com algumas tentativas antes de desistir.

    O timeout de TCP aqui NÃO é hipotético: entre 30/07 e 23/08/2026 as 17 execuções
    agendadas falharam todas em `(2003, ... timed out)` porque o job rodou com o notebook
    fora da rede da JEM. O banco (209.151.154.185) só aceita conexão do IP de saída do
    escritório -- o pacote é descartado pelo firewall, então dá TIMEOUT, não "Access
    denied". Por isso a mensagem de erro abaixo aponta a rede: um "timed out" cru manda
    quem lê investigar credencial, que é justamente o que não está errado.

    As tentativas cobrem o caso de uma reconexão de Wi-Fi em curso; elas NÃO resolvem
    estar fora da rede da JEM -- nesse caso as 3 falham e o job termina com erro visível.
    """
    env = load_env(ROOT / ".env")
    host = env["MAGENTO_DB_HOST"]
    last: Exception | None = None
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        try:
            return pymysql.connect(
                host=host,
                port=int(env.get("MAGENTO_DB_PORT", "3306")),
                user=env["MAGENTO_DB_USER"],
                password=env["MAGENTO_DB_PASSWORD"],
                database=env["MAGENTO_DB_NAME"],
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=20,
                read_timeout=120,
            )
        except pymysql.err.OperationalError as exc:
            last = exc
            print(f"  Magento: tentativa {attempt}/{CONNECT_ATTEMPTS} falhou -- {exc}")
            if attempt < CONNECT_ATTEMPTS:
                time.sleep(CONNECT_BACKOFF_S)

    is_timeout = "timed out" in str(last) or "unreachable" in str(last)
    raise RuntimeError(
        f"Não foi possível conectar ao Magento ({host}) em {CONNECT_ATTEMPTS} tentativas: {last}\n"
        + (
            "  DIAGNÓSTICO: timeout de TCP = o firewall do banco descartou o pacote, o que\n"
            "  normalmente significa RODAR FORA DA REDE DA JEM (o banco só libera o IP de\n"
            "  saída do escritório). Não é credencial -- senha errada devolveria 'Access\n"
            "  denied' na hora. Rode de novo conectada à rede da JEM.\n"
            if is_timeout
            else "  Erro não é timeout -- verifique as credenciais MAGENTO_* em ../.env.\n"
        )
    ) from last


def run_sql(cur, path: Path) -> list[dict]:
    cur.execute(path.read_text(encoding="utf-8").strip().rstrip(";"))
    return list(cur.fetchall())


def num(value) -> float:
    if value is None:
        return 0.0
    return float(value) if isinstance(value, Decimal) else float(value)


# Último recurso: cópia estática do quadro do report "27 de Julho".
# Só é usada se não houver token E não houver clickup_snapshot.json -- o caminho normal
# hoje é a API ao vivo (clickup_client.build_board).
TASKS_STATIC = {
    "source": "static_reference_pending_clickup",
    "as_of": "2026-07-27",
    "columns": [
        {
            "key": "in_progress", "label": "Em andamento", "icon": "play", "color": "green",
            "tasks": [
                {"title": "Investigação de divergências na atribuição de Sales Rep entre NetSuite e Magento", "trend": "same"},
                {"title": "Implementação do AvaTax como fonte oficial de cálculo de Taxes no Magento e NetSuite", "trend": "same"},
                {"title": "Implementação de novo fluxo de cadastro via Site integrado ao NetSuite", "trend": "same"},
                {"title": "Atualização automática dos valores somados do Shopping Cart ao alterar a quantidade de produtos", "trend": "down"},
            ],
        },
        {
            "key": "ready_stg", "label": "Prontas para validação (STG)", "icon": "clock", "color": "blue",
            "tasks": [
                {"title": "Monitoramento e correções automáticas de falhas (Fallback) nas integrações de IF e Invoices", "trend": "same"},
            ],
        },
        {
            "key": "awaiting_deploy", "label": "Tarefas aguardando Deploy", "icon": "rocket", "color": "purple",
            "tasks": [
                {"title": "Integração do atributo Bulk Pack entre NetSuite e Magento para controle de exibição de produtos", "trend": "up"},
            ],
        },
        {
            "key": "ready_prd", "label": "Tarefas prontas para validação (PRD)", "icon": "clipboard", "color": "orange",
            "tasks": [
                {"title": "Criação de dashboard para monitorar a integração de IFs e Invoices entre NetSuite e Magento", "trend": "same"},
            ],
        },
        {
            "key": "done_prd", "label": "Conclusões mais recentes (PRD)", "icon": "trophy", "color": "gold",
            "tasks": [
                {"title": "Criação de dashboard para monitorar a integração de Credit Limit entre NetSuite e Magento", "trend": "up"},
            ],
        },
    ],
    "pipeline": [
        {"step": 1, "icon": "play", "label": "Tarefa em andamento (início)"},
        {"step": 2, "icon": "flask", "label": "Validação em ambiente de testes (STG)"},
        {"step": 3, "icon": "rocket", "label": "Publicação da tarefa em PRD (Deploy)"},
        {"step": 4, "icon": "clipboard", "label": "Testes finais em ambiente real (PRD)"},
        {"step": 5, "icon": "trophy", "label": "Conclusão da tarefa (etapa final)"},
    ],
}


CLICKUP_SNAPSHOT_PATH = HERE / "clickup_snapshot.json"


def load_clickup_tasks(now: datetime) -> dict:
    """Monta o quadro do ClickUp -- ao vivo, sem humano no meio.

    Ordem de preferência:
      1. **API do ClickUp** com `CLICKUP_TOKEN` do `../.env` (clickup_client). Puxa a view
         "Board" do go-live e o histórico de cada tarefa ativa, então as setas de tendência
         são reais e o script pode rodar agendado.
      2. `clickup_snapshot.json`, se existir -- resquício do fluxo manual via MCP.
      3. Cópia estática do report de referência (último recurso).

    A queda para 2/3 é registrada em `source`, e o dashboard mostra na tela de onde veio o
    quadro: nunca se passa dado velho por dado ao vivo.
    """
    env = load_env(ROOT / ".env")
    token = env.get("CLICKUP_TOKEN", "").strip()

    if token:
        # Base das setas: fechamento de ONTEM (23:59:59 Phoenix).
        cutoff_dt = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
        cutoff_ms = int(cutoff_dt.timestamp() * 1000)
        # Janela em que o filtro de data do quadro consegue remontar o passado.
        window_dt = (now - timedelta(days=clickup_client.HISTORY_WINDOW_DAYS)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        try:
            board = clickup_client.build_board(
                token=token,
                cutoff_ms=cutoff_ms,
                cutoff_label=cutoff_dt.strftime("%Y-%m-%d %H:%M:%S America/Phoenix"),
                as_of=now.strftime("%Y-%m-%d"),
                window_start_ms=int(window_dt.timestamp() * 1000),
                history_from=window_dt.strftime("%Y-%m-%d"),
                now_ms=int(now.timestamp() * 1000),
            )
            s = board["stats"]
            print(f"  ClickUp (API)      : {s['tasks_in_view']} tarefas na view · "
                  f"{s['history_calls']} chamadas de histórico · "
                  f"{s['ignored_backlog']} backlog ignoradas · "
                  f"quadro reconstruível desde {board['history_from']}")
            if s.get("tasks_with_hidden_visits"):
                print(f"    {s['tasks_with_hidden_visits']} tarefa(s) com status repetido no "
                      f"histórico -> em datas anteriores à última repetição o quadro marca "
                      f"a etapa como incerta ('?') em vez de afirmar")
            if s["unmapped"]:
                print(f"    !! status fora do mapa (ficaram fora do quadro): {s['unmapped']}")
            if s["tasks_without_history"]:
                print(f"    !! {s['tasks_without_history']} tarefa(s) sem histórico -> sem seta "
                      f"(ClickApp 'Total time in Status' desligado?)")
            if s.get("tasks_without_usable_since"):
                print(f"    !! {s['tasks_without_usable_since']} tarefa(s) com histórico mas SEM "
                      f"`since` legível -> o formato do payload do ClickUp mudou; ver "
                      f"clickup_client.history_since()")
            # base do dia anterior para as setas do PORTAL (a versão local não precisa:
            # ela tem o histórico inteiro no data.json)
            try:
                p = write_board_baseline(board, cutoff_ms, cutoff_dt.strftime("%Y-%m-%d"))
                if p:
                    print(f"  Base de ontem      : {p.name} "
                          f"({len(json.loads(p.read_text(encoding='utf-8'))['tarefas'])} tarefas)")
                else:
                    print("  Base de ontem      : nenhuma tarefa com etapa conhecida no fechamento "
                          "de ontem — arquivo não gravado")
            except Exception as e:  # noqa: BLE001
                # não pode derrubar o refresh: o dashboard local não depende disso
                print(f"  !! falhou ao gravar a base de ontem: {e}")
            if s.get("all_new_suspicious"):
                print("    !! TODAS as tarefas ativas ficaram sem base de comparação. Isso é "
                      "implausível (seria o quadro inteiro criado hoje) e costuma indicar "
                      "`since` ilegível -- NÃO publique as setas assim.")
            return board
        except Exception as e:  # noqa: BLE001
            print(f"  !! ClickUp ao vivo falhou ({e}); caindo para o snapshot/estático")

    if CLICKUP_SNAPSHOT_PATH.is_file():
        print("  ClickUp            : clickup_snapshot.json (pull manual antigo, NÃO ao vivo)")
        return json.loads(CLICKUP_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    print("  ClickUp            : cópia estática do report de referência (NÃO ao vivo)")
    return TASKS_STATIC


BASELINE_DIR = HERE / "board_baseline"
BASELINE_KEEP_DAYS = 7


def write_board_baseline(board: dict, cutoff_ms: int, cutoff_date: str) -> Path | None:
    """Grava o ESTADO DO QUADRO NO FECHAMENTO DE ONTEM, no formato que o portal lê.

    É a peça que falta para o portal ter setas de tendência: ele não consegue calcular
    isso (não encadeia requisições nem guarda nada entre atualizações), então alguém tem
    de preservar o dia anterior. Aqui é de graça: o histórico de status de cada tarefa já
    foi buscado para as setas da versão local, então a coluna de ontem sai do mesmo dado.

    Por que o fechamento de ontem e não o instante da execução: a regra publicada no
    manifesto é "onde a tarefa estava às 23:59:59 (Phoenix) do dia", e dá para cumprir
    exatamente porque o histórico permite consultar qualquer instante. Um retrato tirado
    às 18:00 (hora do agendamento) jogaria as movimentações do fim do dia para o dia
    seguinte.

    ⚠ Um arquivo por dia, com a data no nome, e os 7 mais recentes preservados. Sobrescrever
    o de ontem antes da comparação faria TODA seta virar `=` -- resultado plausível, logo
    invisível. Ver a seção "Preservar o log do dia anterior" no
    `portal_jem_marketing_daily.md`, que é a especificação deste arquivo.

    O arquivo NÃO leva título de tarefa: só id, coluna e status. Quem exibe o título é o
    quadro ao vivo; a base só precisa dizer em que etapa cada id estava.
    """
    ordinal = {c["key"]: i + 1 for i, c in enumerate(clickup_client.COLUMNS)}
    rows = []
    for item in board.get("items", []):
        hist = item.get("hist") or []
        at = clickup_client.status_at(hist, cutoff_ms)
        if not at:
            continue  # não existia / sem status conhecido naquele instante
        key = clickup_client.column_key(at["s"])
        if key is None:
            continue  # backlog ou status fora do mapa: não estava no quadro
        rows.append({
            # repetido em toda linha de propósito: um dataset do portal entrega só as
            # LINHAS (`select`), então campo fora do array se perde -- e é justamente
            # esta data que a tela precisa conferir antes de desenhar seta
            "refere_se_a": cutoff_date,
            "id": item.get("id"),
            "col": ordinal[key],
            "status": at["s"],
        })
    if not rows:
        return None
    BASELINE_DIR.mkdir(exist_ok=True)
    path = BASELINE_DIR / f"board-{cutoff_date}.json"
    path.write_text(json.dumps({"tarefas": rows}, ensure_ascii=False), encoding="utf-8")
    # retenção: 7 dias. Um run perdido não cega a comparação -- a tela usa a base mais
    # recente disponível e declara de que dia ela é.
    files = sorted(BASELINE_DIR.glob("board-*.json"))
    for old in files[:-BASELINE_KEEP_DAYS]:
        old.unlink()
    return path


def load_history() -> dict:
    if HISTORY_PATH.is_file():
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    return {}


def save_history(history: dict) -> None:
    # keep only the most recent HISTORY_KEEP_DAYS entries
    dates = sorted(history.keys())
    for d in dates[:-HISTORY_KEEP_DAYS]:
        del history[d]
    HISTORY_PATH.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")


def build() -> dict:
    with connect() as conn:
        with conn.cursor() as cur:
            companies_total = run_sql(cur, QUERIES / "companies_total.sql")[0]["c"]
            contacts_total = run_sql(cur, QUERIES / "contacts_total.sql")[0]["c"]
            company_map_raw = run_sql(cur, QUERIES / "company_customer_map.sql")
            orders_raw = run_sql(cur, QUERIES / "orders_ytd.sql")

    customer_to_company: dict[int, dict] = {
        r["customer_id"]: {"company_id": r["company_id"], "company_name": r["company_name"]}
        for r in company_map_raw
    }

    orders = [
        {
            "increment_id": o["increment_id"],
            "created_at": str(o["created_at"]),
            # "amount" = faturamento: pure sale value, net of discount, EXCLUDING
            # shipping and tax (per Maynara 2026-07-28 -- grand_total mixes those in).
            "amount": round(num(o["subtotal"]) + num(o["discount_amount"]), 2),
            "customer_id": o["customer_id"],
            "state": o["state"],
        }
        for o in orders_raw
    ]

    now = datetime.now(PHOENIX)
    today_str = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")

    orders_today = [o for o in orders if o["created_at"][:10] == today_str]
    orders_month = [o for o in orders if o["created_at"][:7] == month_str]
    orders_ytd = orders  # query is already floored at 2026-01-01

    orders_today_count = len(orders_today)
    revenue_today = round(sum(o["amount"] for o in orders_today), 2)
    orders_month_count = len(orders_month)
    revenue_month = round(sum(o["amount"] for o in orders_month), 2)
    orders_ytd_count = len(orders_ytd)

    highlight = None
    if orders_today:
        top = max(orders_today, key=lambda o: o["amount"])
        comp = customer_to_company.get(top["customer_id"])
        highlight = {
            "increment_id": top["increment_id"],
            "amount": top["amount"],
            "company_name": comp["company_name"] if comp else None,
        }

    companies_with_purchase = {
        customer_to_company[o["customer_id"]]["company_id"]
        for o in orders_ytd
        if o["customer_id"] in customer_to_company
    }
    companies_first_purchase_count = len(companies_with_purchase)
    pct_first_purchase = (
        round(companies_first_purchase_count / companies_total * 100, 2) if companies_total else 0.0
    )

    # 6-month trend: current month + 5 preceding
    months: list[str] = []
    cursor_dt = now.replace(day=1)
    for _ in range(6):
        months.append(cursor_dt.strftime("%Y-%m"))
        prev_month_end = cursor_dt - timedelta(days=1)
        cursor_dt = prev_month_end.replace(day=1)
    months.reverse()
    monthly_map: dict[str, dict] = {m: {"orders": 0, "revenue": 0.0} for m in months}
    for o in orders_ytd:
        ym = o["created_at"][:7]
        if ym in monthly_map:
            monthly_map[ym]["orders"] += 1
            monthly_map[ym]["revenue"] += o["amount"]
    monthly = [
        {"ym": m, "orders": monthly_map[m]["orders"], "revenue": round(monthly_map[m]["revenue"], 2)}
        for m in months
    ]

    # --- day-over-day deltas, via history.json ---
    history = load_history()
    prior_dates = sorted(d for d in history if d < today_str)
    prev = history[prior_dates[-1]] if prior_dates else None

    def delta(curr, key):
        if prev is None or prev.get(key) is None:
            return None
        return round(curr - prev[key], 2)

    deltas = {
        "companies_total": delta(companies_total, "companies_total"),
        "contacts_total": delta(contacts_total, "contacts_total"),
        "pct_first_purchase_pp": delta(pct_first_purchase, "pct_first_purchase"),
    }

    history[today_str] = {
        "companies_total": companies_total,
        "contacts_total": contacts_total,
        "companies_first_purchase_count": companies_first_purchase_count,
        "pct_first_purchase": pct_first_purchase,
    }
    save_history(history)

    return {
        "last_execution": now.strftime("%Y-%m-%d %H:%M:%S"),
        "report_date": today_str,
        "period": {"min": "2026-01-01", "max": today_str},
        # Raw rows + lookup maps so the dashboard's day-picker can recompute every
        # day-scoped KPI (orders/GMV/highlight/month-to-date/YTD-to-date) for ANY
        # selected date client-side, not just "today" -- mirrors the rest of the
        # repo's "base data in, aggregate in the browser" convention.
        "orders": orders,
        "company_map": {
            str(cid): v["company_name"] for cid, v in customer_to_company.items()
        },
        # Daily snapshots (companies/contacts/etc.) -- only dates we've actually
        # captured have real numbers; the dashboard shows "no snapshot" otherwise.
        "history": history,
        "kpis": {
            "companies_total": companies_total,
            "companies_total_delta": deltas["companies_total"],
            "contacts_total": contacts_total,
            "contacts_total_delta": deltas["contacts_total"],
            "companies_first_purchase_count": companies_first_purchase_count,
            "pct_first_purchase": pct_first_purchase,
            "pct_first_purchase_delta_pp": deltas["pct_first_purchase_pp"],
            "orders_today": orders_today_count,
            "revenue_today": revenue_today,
            "orders_month": orders_month_count,
            "revenue_month": revenue_month,
            "orders_ytd": orders_ytd_count,
            "visits_today": None,
            "conversion_today": None,
            "highlight_order": highlight,
        },
        "monthly": monthly,
        "tasks": load_clickup_tasks(now),
    }


def main() -> None:
    data = build()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    (HERE / "data.json").write_text(payload, encoding="utf-8")
    (HERE / "data.js").write_text(
        "window.DASHBOARD_DATA = " + payload + ";\n", encoding="utf-8"
    )

    k = data["kpis"]
    print("Wrote data.json (+ data.js)")
    print(f"  Companies          : {k['companies_total']:,} ({k['companies_total_delta']})")
    print(f"  Contacts           : {k['contacts_total']:,} ({k['contacts_total_delta']})")
    print(f"  Companies 1a compra: {k['companies_first_purchase_count']:,} (~{k['pct_first_purchase']}%)")
    print(f"  Pedidos hoje       : {k['orders_today']:,}  Faturamento hoje: {k['revenue_today']:,.2f}")
    print(f"  Pedidos mes        : {k['orders_month']:,}  Faturamento mes: {k['revenue_month']:,.2f}")
    print(f"  Pedidos YTD        : {k['orders_ytd']:,}")
    print(f"  Pedido destaque    : {k['highlight_order']}")
    print(f"  Last execution     : {data['last_execution']} (Phoenix)")


if __name__ == "__main__":
    main()
