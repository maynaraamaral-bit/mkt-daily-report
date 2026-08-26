"""Probe: descobre o que o board de go-live realmente mostra, antes de mexer no dashboard.

Roda assim que o CLICKUP_TOKEN existir no ../.env:

    C:/Users/MaynaraAmaral/anaconda3/python.exe probe_clickup_view.py

Responde, em uma passada:
  1. Quais views existem nas 2 listas, com o id que A API aceita (e se ele bate com o
     fragmento da URL do navegador, 6-901112863157-2).
  2. Os filtros/agrupamento configurados na view do board -- ou seja, QUAL o critério do
     time, que hoje o dashboard reimplementa por conta própria.
  3. Exatamente quais tarefas a view devolve, e o que ela ESCONDE em relação à lista
     inteira (a diferença é o que sairia do quadro).
  4. Se a view traz tarefas fechadas (decide se a coluna "Conclusões mais recentes (PRD)"
     precisa vir da lista em separado).

Só leitura -- nenhum POST/PUT. Usa a stdlib (urllib), sem dependência nova.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE = "https://api.clickup.com/api/v2"

# escopo atual do dashboard (ver CLAUDE.md §2)
LISTS = {
    "901112863157": "Incident Support | Go-Live",
    "901110423629": "Hyvä Backlog",
}
# view do board que a Maynara apontou: https://app.clickup.com/31082060/v/b/6-901112863157-2
BOARD_VIEW_ID = "6-901112863157-2"
BULK_PACK_ID = "868ggetw0"  # tarefa-controle: está na Hyvä Backlog, não na Incident


def load_env(path: Path) -> dict[str, str]:
    env = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


ENV = load_env(ROOT / ".env")
TOKEN = ENV.get("CLICKUP_TOKEN", "").strip()
if not TOKEN:
    sys.exit(
        "CLICKUP_TOKEN ausente em ../.env.\n"
        "Adicione a linha (sem aspas):  CLICKUP_TOKEN=pk_...\n"
        "Token: https://app.clickup.com/settings/apps -> API Token -> Generate"
    )


def api(path: str, params: dict | None = None):
    """GET no ClickUp. Devolve (status_code, payload|texto_do_erro)."""
    url = BASE + path
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={
        "Authorization": TOKEN,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        return e.code, body
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("-" * 78)


def status_of(t: dict) -> str:
    s = t.get("status")
    if isinstance(s, dict):
        return str(s.get("status", ""))
    return str(s or "")


def status_type(t: dict) -> str:
    s = t.get("status")
    return str(s.get("type", "")) if isinstance(s, dict) else ""


def paged_tasks(path: str, extra: dict | None = None, cap_pages: int = 25):
    """Varre as páginas de um endpoint que devolve {tasks:[...], last_page:bool}."""
    out, page = [], 0
    while page < cap_pages:
        params = {"page": page}
        if extra:
            params.update(extra)
        code, data = api(path, params)
        if code != 200:
            return code, data, out
        chunk = data.get("tasks", []) if isinstance(data, dict) else []
        out.extend(chunk)
        if not isinstance(data, dict) or data.get("last_page") or not chunk:
            break
        page += 1
    return 200, None, out


# ---------------------------------------------------------------- 1. views das listas
hr("1. VIEWS EXISTENTES NAS DUAS LISTAS (com o id que a API aceita)")
view_index = {}
for list_id, list_name in LISTS.items():
    code, data = api(f"/list/{list_id}/view")
    print(f"\nLista {list_id}  ({list_name})   HTTP {code}")
    if code != 200:
        print(f"   !! {data}")
        continue
    views = (data or {}).get("views", []) or []
    default = (data or {}).get("required_views", {}) or {}
    for v in views:
        vid, vname, vtype = v.get("id"), v.get("name"), v.get("type")
        view_index[vid] = (vname, vtype, list_id)
        print(f"   id={vid!r:34} type={vtype!r:12} name={vname!r}")
    for key, v in default.items():
        if isinstance(v, dict) and v.get("id"):
            view_index[v["id"]] = (v.get("name"), v.get("type"), list_id)
            print(f"   [required:{key}] id={v['id']!r:22} type={v.get('type')!r:10} name={v.get('name')!r}")

print(f"\n   O id da URL do navegador é {BOARD_VIEW_ID!r} -> "
      f"{'ENCONTRADO nas views acima' if BOARD_VIEW_ID in view_index else 'NÃO apareceu na listagem (pode ser view pessoal ou de outro nível)'}")

# ---------------------------------------------------------------- 2. definição da view
hr(f"2. DEFINIÇÃO DA VIEW DO BOARD ({BOARD_VIEW_ID}) — filtros e agrupamento do time")
code, data = api(f"/view/{BOARD_VIEW_ID}")
print(f"HTTP {code}")
if code == 200 and isinstance(data, dict):
    v = data.get("view", data) or {}
    print(f"   name    : {v.get('name')!r}")
    print(f"   type    : {v.get('type')!r}")
    print(f"   parent  : {v.get('parent')!r}")
    print(f"   grouping: {json.dumps(v.get('grouping'), ensure_ascii=False)}")
    print(f"   filters : {json.dumps(v.get('filters'), ensure_ascii=False)}")
    print(f"   settings: {json.dumps(v.get('settings'), ensure_ascii=False)[:400]}")
else:
    print(f"   !! {data}")
    print("   >> Se deu 401/404 aqui, o id da URL não serve direto na API:"
          " use o id que apareceu no passo 1.")

# ---------------------------------------------------------------- 3. tarefas da view
hr(f"3. TAREFAS QUE A VIEW DEVOLVE  (GET /view/{BOARD_VIEW_ID}/task)")
code, err, vtasks = paged_tasks(f"/view/{BOARD_VIEW_ID}/task")
if code != 200:
    print(f"HTTP {code}  !! {err}")
    print("   >> Sem isso não dá para replicar o board; tente o id do passo 1.")
    vtasks = []
else:
    print(f"HTTP 200 · {len(vtasks)} tarefas")
    by_status: dict[str, int] = {}
    for t in vtasks:
        by_status[status_of(t)] = by_status.get(status_of(t), 0) + 1
    print("\n   contagem por status:")
    for s, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"     {n:>4}  {s}")
    closed = [t for t in vtasks if status_type(t) in ("closed", "done")]
    print(f"\n   tarefas de status closed/done na view: {len(closed)}"
          f"   -> coluna 'Conclusões' {'PODE sair da view' if closed else 'PRECISA vir da lista (a view esconde fechadas)'}")
    lists_seen = {(t.get("list") or {}).get("name") for t in vtasks}
    print(f"   listas representadas na view: {sorted(x for x in lists_seen if x)}")
    print(f"   Bulk Pack ({BULK_PACK_ID}) está na view? "
          f"{'SIM' if any(t.get('id') == BULK_PACK_ID for t in vtasks) else 'NÃO'}")
    print("\n   primeiras 40 tarefas:")
    for t in vtasks[:40]:
        print(f"     [{status_of(t):<24}] {str(t.get('name'))[:72]}")

# ------------------------------------------------- 4. o que a view esconde vs a lista
hr("4. DIFERENÇA VIEW × LISTA INTEIRA (o que sairia do quadro)")
code, err, ltasks = paged_tasks(
    f"/list/901112863157/task", {"archived": "false", "include_closed": "true"}
)
if code != 200:
    print(f"HTTP {code}  !! {err}")
else:
    print(f"lista Incident Support | Go-Live: {len(ltasks)} tarefas (com include_closed)")
    if vtasks:
        vids = {t.get("id") for t in vtasks}
        hidden = [t for t in ltasks if t.get("id") not in vids]
        print(f"escondidas pela view: {len(hidden)}")
        hs: dict[str, int] = {}
        for t in hidden:
            hs[status_of(t)] = hs.get(status_of(t), 0) + 1
        for s, n in sorted(hs.items(), key=lambda kv: -kv[1]):
            print(f"     {n:>4}  {s}")
        print("\n   amostra do que a view esconde:")
        for t in hidden[:15]:
            print(f"     [{status_of(t):<24}] {str(t.get('name'))[:72]}")

print("\nFIM")
