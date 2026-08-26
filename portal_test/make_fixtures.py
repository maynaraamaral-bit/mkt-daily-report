"""Etapa 2 do harness: reconcilia 27/07 e escreve o dataset do ClickUp.

Puxa a **view real** do board de go-live pela API (token em ../../.env) — o mesmo endpoint
que o portal usa —, então o teste roda contra o payload verdadeiro, não uma imitação.
Se não houver token, cai para `clickup_mcp_pull.json` e avisa.

Ao final injeta 2 linhas no **formato compacto** (`status` como string, sem `date_updated`),
que é o que as ferramentas MCP devolvem. As duas formas coexistem no mesmo dataset de
propósito: a página tem que aguentar as duas.
"""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
DASH = HERE.parent
ROOT = DASH.parent
SITE = HERE / "site"
DATA = SITE / "data"

BOARD_VIEW_ID = "6-901112863157-2"
BASE = "https://api.clickup.com/api/v2"

orders = json.loads((DATA / "mkt_orders.json").read_text(encoding="utf-8"))

# ---------------------------------------------------------------- reconciliação 27/07
D = "2026-07-27"
amt = lambda rows_: round(sum(float(o["amount"]) for o in rows_), 2)
july_to_27 = [o for o in orders if o["created_at"][:7] == "2026-07" and o["created_at"][:10] <= D]
day = [o for o in orders if o["created_at"][:10] == D]
ytd_to_27 = [o for o in orders if o["created_at"][:10] <= D]
comp_to_27 = {o["company_id"] for o in ytd_to_27 if o["company_id"] is not None}
top = max(day, key=lambda o: float(o["amount"]))

print("=" * 74)
print("compute('2026-07-27') — âncora histórica, estes números NÃO mudam")
print("-" * 74)
print(f"  pedidos no dia        : {len(day)}          (referência 32)   {'OK' if len(day)==32 else 'FALHOU'}")
print(f"  faturamento no dia    : {amt(day):,.2f}")
print(f"  pedidos no mês (<=27) : {len(july_to_27)}         (referência 449)  {'OK' if len(july_to_27)==449 else 'FALHOU'}")
print(f"  faturamento no mês    : {amt(july_to_27):,.2f}")
print(f"  destaque              : {float(top['amount']):,.2f}  #{top['increment_id']}  {top['company_name']}")
print(f"  companies 1ª compra   : {len(comp_to_27)}")


# ---------------------------------------------------------------- dataset do ClickUp
def load_env(path: Path) -> dict:
    env = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


TOKEN = load_env(ROOT / ".env").get("CLICKUP_TOKEN", "").strip()


def get_page(page: int, tries: int = 4) -> list:
    """Uma página da view, com retry/backoff — a API do ClickUp dá timeout esporádico
    (visto em 29/07: uma passada inteira ok, a seguinte estourou 45s)."""
    url = f"{BASE}/view/{BOARD_VIEW_ID}/task?" + urlencode({"page": page})
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"Authorization": TOKEN, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8")).get("tasks", [])
        except Exception as e:  # noqa: BLE001  (timeout, 5xx, conexão)
            last = e
            if attempt < tries - 1:
                wait = 2 ** attempt
                print(f"     ... página {page} falhou ({type(e).__name__}), retry em {wait}s")
                time.sleep(wait)
    raise RuntimeError(f"página {page} falhou após {tries} tentativas: {last}")


TEAM_ID = "31082060"
DONE_LIST_IDS = ["901112863157", "901110423629", "901113068292"]
DONE_STATUSES = ["Closed", "approved by qa - prd"]
DONE_WINDOW_DAYS = 60


def get_team_done(tries: int = 4) -> list:
    """A consulta da coluna 5: concluídas das listas do board na janela de 60 dias.
    Uma requisição (100/página) — é o que substitui as 4 páginas de concluídas da view."""
    params = [("page", 0), ("include_closed", "true"),
              ("date_updated_gt", int((time.time() - DONE_WINDOW_DAYS * 86400) * 1000))]
    params += [("list_ids[]", i) for i in DONE_LIST_IDS]
    params += [("statuses[]", s) for s in DONE_STATUSES]
    url = f"{BASE}/team/{TEAM_ID}/task?" + urlencode(params)
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"Authorization": TOKEN, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode("utf-8"))
                if d.get("last_page") is False:
                    print("     !! a consulta de conclusões voltou com last_page=False "
                          "(truncada em 100): reduza a janela no manifesto")
                return d.get("tasks", [])
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < tries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"consulta de conclusões falhou após {tries} tentativas: {last}")


# O portal faz 3 requisições; as fixtures reproduzem EXATAMENTE essas 3 -- se aqui
# virasse uma varredura completa, o teste passaria num dado que o portal nunca recebe.
pg0: list = []
pg1: list = []
done_rows: list = []
source = ""
if TOKEN:
    try:
        pg0 = get_page(0)
        pg1 = get_page(1)
        done_rows = get_team_done()
        source = f"API ao vivo (view {BOARD_VIEW_ID} pág. 0 e 1 + conclusões por equipe)"
    except urllib.error.HTTPError as e:
        print(f"\n!! HTTP {e.code} ao puxar do ClickUp: {e.read().decode('utf-8','replace')[:200]}")
    except Exception as e:  # noqa: BLE001
        print(f"\n!! erro ao puxar do ClickUp: {e}")

if not pg0:
    # Sem token/API: divide o pull antigo em 2 "páginas" e deriva as conclusões dele.
    # Não é o payload real do portal — a saída avisa.
    fb = json.loads((HERE / "clickup_mcp_pull.json").read_text(encoding="utf-8"))["tasks"]

    def _is_done(t):
        s = t.get("status")
        name = (s.get("status") if isinstance(s, dict) else s) or ""
        return str(name).lower() in ("closed", "approved by qa - prd")

    ativas = [t for t in fb if not _is_done(t)]
    pg0, pg1 = ativas[:30], ativas[30:60] + [t for t in fb if _is_done(t)][:24]
    done_rows = [t for t in fb if _is_done(t)]
    source = "fallback clickup_mcp_pull.json (sem token ou API indisponível)"

# 2 linhas no formato COMPACTO, para exercitar o caminho defensivo da página:
# status como string simples e nenhum date_updated.
compact = [
    {"id": "cmpct-1", "name": "[fixture compacta] status como string, sem date_updated",
     "status": "on hold", "date_closed": None,
     "list": {"id": "901112863157", "name": "Incident Support | Go-Live"}},
    {"id": "cmpct-2", "name": "[fixture compacta] backlog deve ficar FORA do quadro",
     "status": "backlog", "date_closed": None,
     "list": {"id": "901112863157", "name": "Incident Support | Go-Live"}},
    # status inexistente no mapa: precisa virar AVISO no rodapé, não desaparecer calado.
    # Cobre o caso real "alguém criou um status novo no ClickUp".
    {"id": "cmpct-3", "name": "[fixture compacta] status fora do mapa deve gerar aviso",
     "status": "status novo do clickup", "date_closed": None,
     "list": {"id": "901112863157", "name": "Incident Support | Go-Live"}},
]
# as linhas compactas entram na página 1 (a 2ª), para os casos-limite (backlog, status
# fora do mapa, payload compacto) passarem pelo mesmo caminho das ativas
pg1 = pg1 + compact
rows = pg0 + pg1  # usado só nos resumos abaixo

DATA.mkdir(parents=True, exist_ok=True)
(DATA / "clickup_board_pg0.json").write_text(
    json.dumps(pg0, ensure_ascii=False), encoding="utf-8")
(DATA / "clickup_board_pg1.json").write_text(
    json.dumps(pg1, ensure_ascii=False), encoding="utf-8")
(DATA / "clickup_concluidas.json").write_text(
    json.dumps(done_rows, ensure_ascii=False), encoding="utf-8")
# limpa datasets de desenhos anteriores, para o teste não ler arquivo velho
for old in ("clickup_incident_golive.json", "clickup_hyva_backlog.json",
            "clickup_golive_board.json"):
    p = DATA / old
    if p.is_file():
        p.unlink()
        print(f"\n  (removido dataset obsoleto: {old})")


# Base do dia anterior: se o `build_data.py` já gravou alguma, copia a mais recente para
# `site/data/board_baseline.json` -- é o que o portal serviria se o dataset estivesse
# ativo. Sem nenhuma, o harness exercita o caminho "base ausente" (sem setas, sem erro).
BASELINE_SRC = sorted((DASH / "board_baseline").glob("board-*.json")) \
    if (DASH / "board_baseline").is_dir() else []
baseline_note = "nenhuma (caminho 'sem setas' será exercitado)"
if BASELINE_SRC:
    src = BASELINE_SRC[-1]
    payload = json.loads(src.read_text(encoding="utf-8"))
    linhas = payload.get("tarefas", payload if isinstance(payload, list) else [])
    (DATA / "board_baseline.json").write_text(
        json.dumps(linhas, ensure_ascii=False), encoding="utf-8")
    baseline_note = f"{src.name} → {len(linhas)} linhas"
elif (DATA / "board_baseline.json").is_file():
    (DATA / "board_baseline.json").unlink()


def st(t):
    s = t.get("status")
    return (s.get("status") if isinstance(s, dict) else s) or ""


print("\n" + "=" * 74)
print(f"3 datasets do ClickUp · fonte: {source}")
print(f"  clickup_board_pg0.json  — {len(pg0)} linhas")
print(f"  clickup_board_pg1.json  — {len(pg1)} linhas (inclui {len(compact)} fixtures compactas)")
print(f"  clickup_concluidas.json — {len(done_rows)} linhas"
      + ("  !! >=100: truncado" if len(done_rows) >= 100 else ""))
print(f"  board_baseline.json     — {baseline_note}")
print("-" * 74)
counts: dict = {}
for t in rows:
    counts[st(t)] = counts.get(st(t), 0) + 1
for s, n in sorted(counts.items(), key=lambda kv: -kv[1]):
    print(f"   {n:>4}  {s}")
listas = sorted({(t.get("list") or {}).get("name", "") for t in rows} - {""})
print(f"\n   listas representadas: {listas}")
print(f"   formatos no dataset : objeto={sum(1 for t in rows if isinstance(t.get('status'), dict))} · "
      f"string={sum(1 for t in rows if isinstance(t.get('status'), str))}")
print("\nDONE")
