"""Cliente ClickUp para o quadro de tarefas do Marketing Daily Report.

Substitui o pull manual via MCP: com `CLICKUP_TOKEN` no `../.env`, este módulo monta o
quadro inteiro **sem humano no meio** -- inclusive as setas de tendência, que exigem uma
chamada de histórico por tarefa (é justamente isso que o portal não consegue fazer, ver
CLAUDE.md §9).

Fonte do quadro = a **view "Board" do go-live** (a mesma que o time usa), não as listas
inteiras. Quem entra no quadro é a curadoria da view; este módulo só decide em qual das 5
colunas cada tarefa cai.

Gotchas descobertos ao vivo em 2026-07-29 -- não "simplifique" nenhum deles:

* `last_page` do endpoint da view é **mentiroso**: vem `False` até na última página. Paginar
  confiando nele entra em loop infinito. Paramos quando a página não traz id novo.
* O endpoint da view dá **timeout esporádico** (uma varredura inteira passa, a seguinte
  estoura). Todo GET tem retry com backoff.
* `status_history[].since` é a **última** vez que a tarefa entrou naquele status, e
  `total_time` é acumulado entre todas as visitas. Logo o histórico é um **piso**: idas e
  voltas repetidas ao mesmo status ficam invisíveis. Para "onde ela estava no fechamento de
  ontem" isso é suficiente (pegamos o maior `since` <= cutoff), mas não trate a lista como
  a trilha completa.
* O `page` é opcional (sem ele devolve a página 0) e a página tem 30 itens.
* `status_history` **inclui o status atual** como última entrada (verificado ao vivo em
  2026-07-29 em 3 tarefas). É o que permite ao dashboard remontar o quadro de QUALQUER dia
  a partir do mesmo histórico e chegar, para hoje, exatamente ao quadro atual.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

BASE = "https://api.clickup.com/api/v2"

# View "Board" do go-live: https://app.clickup.com/31082060/v/b/6-901112863157-2
# O id do navegador entra literal na API (é uma "required view" de tipo board).
BOARD_VIEW_ID = "6-901112863157-2"

# As 5 etapas do report, na ordem -- é a numeração 1->5 que a seta compara.
COLUMNS = [
    {"key": "in_progress",     "label": "Em andamento",                         "icon": "play",      "color": "green",
     "statuses": ["researching", "to do (sprint)", "doing", "on hold", "blocked", "code review - stg"]},
    {"key": "ready_stg",       "label": "Prontas para validação (STG)",         "icon": "clock",     "color": "blue",
     "statuses": ["ready for testing - stg", "testing - stg", "fail - stg"]},
    {"key": "awaiting_deploy", "label": "Tarefas aguardando Deploy",            "icon": "rocket",    "color": "purple",
     "statuses": ["ready to deploy"]},
    {"key": "ready_prd",       "label": "Tarefas prontas para validação (PRD)", "icon": "clipboard", "color": "orange",
     "statuses": ["ready for testing - prd", "testing - prd", "fail - prd"]},
    {"key": "done_prd",        "label": "Conclusões mais recentes (PRD)",       "icon": "trophy",    "color": "gold",
     "statuses": ["approved by qa - prd", "closed"]},
]
DONE_KEY = "done_prd"
DONE_TOP_N = 10
IGNORED_STATUSES = {"backlog"}  # não iniciado != pipeline ativo

# Janela em que o quadro pode ser REMONTADO para uma data passada (filtro de data do
# dashboard). Para reconstruir o dia T precisamos do histórico de toda tarefa que ainda
# não estava concluída em T -- ou seja: as ativas de hoje + as que foram concluídas
# depois do início da janela. Quem fechou ANTES do início da janela já estava concluída
# em qualquer T da janela, então cai na coluna 5 só pela data de conclusão, sem
# chamada extra. É isto que segura o custo: em 2026-07-29 eram 36 ativas + 30
# concluídas nos últimos 60 dias = 66 chamadas, contra 169 se puxássemos tudo.
HISTORY_WINDOW_DAYS = 60

PIPELINE = [
    {"step": 1, "icon": "play",      "label": "Tarefa em andamento (início)"},
    {"step": 2, "icon": "flask",     "label": "Validação em ambiente de testes (STG)"},
    {"step": 3, "icon": "rocket",    "label": "Publicação da tarefa em PRD (Deploy)"},
    {"step": 4, "icon": "clipboard", "label": "Testes finais em ambiente real (PRD)"},
    {"step": 5, "icon": "trophy",    "label": "Conclusão da tarefa (etapa final)"},
]

_STATUS2KEY = {s: c["key"] for c in COLUMNS for s in c["statuses"]}
_KEY2ORDINAL = {c["key"]: i + 1 for i, c in enumerate(COLUMNS)}


class ClickUpError(RuntimeError):
    pass


# --------------------------------------------------------------------------- HTTP
def _get(token: str, path: str, params: dict | None = None, tries: int = 4):
    url = BASE + path + ("?" + urlencode(params) if params else "")
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"Authorization": token, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            # 4xx não melhora com retry (token inválido, view removida, sem permissão)
            if 400 <= e.code < 500 and e.code != 429:
                raise ClickUpError(f"HTTP {e.code} em {path}: {body}") from e
            last = ClickUpError(f"HTTP {e.code} em {path}: {body}")
        except Exception as e:  # timeout / conexão
            last = e
        if attempt < tries - 1:
            time.sleep(2 ** attempt)
    raise ClickUpError(f"{path} falhou após {tries} tentativas: {last}")


def fetch_view_tasks(token: str, view_id: str = BOARD_VIEW_ID) -> list[dict]:
    """Todas as tarefas da view. Para quando uma página não traz id novo -- `last_page`
    não é confiável neste endpoint."""
    out: list[dict] = []
    seen: set[str] = set()
    page = 0
    while page < 40:
        data = _get(token, f"/view/{view_id}/task", {"page": page})
        chunk = data.get("tasks", []) if isinstance(data, dict) else []
        new = [t for t in chunk if t.get("id") not in seen]
        for t in new:
            seen.add(t["id"])
        out.extend(new)
        if not chunk or not new:
            break
        page += 1
    return out


def fetch_status_history(token: str, task_id: str) -> list[dict]:
    """`status_history` da tarefa. Exige o ClickApp "Total time in Status" ligado no
    workspace; se vier vazio, a tarefa fica sem seta (trend 'new') em vez de mentir."""
    data = _get(token, f"/task/{task_id}/time_in_status")
    return data.get("status_history", []) if isinstance(data, dict) else []


# ------------------------------------------------------------------- normalização
def status_name(task: dict) -> str:
    s = task.get("status")
    if isinstance(s, dict):
        return str(s.get("status") or "").strip().lower()
    return str(s or "").strip().lower()


def column_key(status: str) -> str | None:
    return _STATUS2KEY.get(status.strip().lower())


def _ms(v) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def completed_ms(task: dict) -> int | None:
    """`date_closed` para status tipo *closed*; `date_done` para `approved by qa - prd`,
    que é tipo *done* e deixa `date_closed` nulo."""
    return _ms(task.get("date_closed")) or _ms(task.get("date_done"))


def history_since(h: dict) -> int | None:
    """O `since` de um item de `status_history` -- ele vive em DOIS lugares diferentes,
    dependendo de quem responde (verificado ao vivo em 2026-07-29):

        REST v2 cru : {"status":"doing", "total_time":{"by_minute":19834,"since":"178..."}}
        normalizado : {"status":"doing", "since":"178...", "total_time":"13d 16h 22m"}
                      (é o que as ferramentas MCP devolvem)

    Ler só `h["since"]` faz TODA tarefa parecer sem histórico -- e, como o fallback é
    'new', o quadro inteiro sai sem seta em vez de estourar erro. Sintoma silencioso;
    não "simplifique" esta função.
    """
    direct = _ms(h.get("since"))
    if direct is not None:
        return direct
    tt = h.get("total_time")
    if isinstance(tt, dict):
        return _ms(tt.get("since"))
    return None


def total_minutes(h: dict) -> int | None:
    """Minutos ACUMULADOS naquele status, somando todas as visitas. Duas formas, como em
    `history_since`: dict `{"by_minute": N}` no REST cru, string "13d 16h 22m" na forma
    normalizada (ferramentas MCP)."""
    tt = h.get("total_time")
    if isinstance(tt, dict):
        try:
            return int(tt.get("by_minute"))
        except (TypeError, ValueError):
            return None
    if isinstance(tt, str):
        mins = 0
        found = False
        for value, unit in re.findall(r"(\d+)\s*([dhm])", tt):
            found = True
            mins += int(value) * {"d": 1440, "h": 60, "m": 1}[unit]
        return mins if found else None
    if isinstance(h.get("total_time_minutes"), (int, float)):
        return int(h["total_time_minutes"])
    return None


def unsure_before(history: list[dict], now_ms: int, slack_min: int = 2) -> int | None:
    """A partir de que instante a trilha de status desta tarefa é confiável.

    `since` é a ÚLTIMA entrada em cada status, mas `total_time` é o acumulado de TODAS as
    visitas. Se o acumulado é maior que o tempo visível (do `since` até a entrada seguinte
    -- ou até agora, no status atual), então aquele status foi visitado antes e essa visita
    ficou invisível. Como toda visita escondida a um status é anterior ao `since` dele,
    devolver o MAIOR desses `since` dá o ponto a partir do qual a trilha está completa:
    reconstruir uma data anterior a ele pode colocar a tarefa numa etapa que não é a real.

    Isto não é hipótese: em 2026-07-29, "Dashboard Credit Limit - Dados" reconstruía como
    `doing` em 27/07, quando o registro do dia 28 mostra que ela estava em
    `approved by qa - prd` -- ela voltou para testing e foi aprovada de novo no dia 28, e o
    `since` da aprovação passou a apontar para a segunda vez. Sem esta marcação o quadro
    afirmaria uma etapa errada com a mesma cara de dado certo.

    None = nenhuma visita escondida detectada (trilha completa).
    """
    rows = []
    for h in history:
        ms = history_since(h)
        if ms is not None:
            rows.append((ms, total_minutes(h)))
    rows.sort()
    worst = None
    for i, (ms, mins) in enumerate(rows):
        visible = ((rows[i + 1][0] if i + 1 < len(rows) else now_ms) - ms) / 60000
        if mins is not None and mins > visible + slack_min:
            worst = ms if worst is None else max(worst, ms)
    return worst


def normalize_history(history: list[dict]) -> list[dict]:
    """`status_history` cru -> `[{"ms": epoch, "s": "status"}]` ordenado por tempo.

    É esta forma que vai para o `data.json` (o dashboard remonta o quadro de qualquer dia
    a partir dela) e é a mesma que `column_at` usa aqui, para que servidor e tela não
    possam divergir na leitura do histórico."""
    rows = []
    for h in history:
        ms = history_since(h)
        if ms is None:
            continue
        rows.append({"ms": ms, "s": str(h.get("status") or "").strip().lower()})
    rows.sort(key=lambda r: r["ms"])
    return rows


def status_at(rows: list[dict], cutoff_ms: int) -> dict | None:
    """A entrada de `normalize_history` com o maior `ms` <= cutoff, ou None se a tarefa
    não tinha status conhecido naquele instante (não existia / entrou depois)."""
    best = None
    for r in rows:
        if r["ms"] <= cutoff_ms and (best is None or r["ms"] > best["ms"]):
            best = r
    return best


def column_at(history: list[dict], cutoff_ms: int) -> str | None:
    """Coluna onde a tarefa estava no instante `cutoff_ms`: o status com o maior
    `since` <= cutoff. Devolve None se a tarefa não existia lá (nenhum `since` <= cutoff)."""
    best = status_at(normalize_history(history), cutoff_ms)
    return column_key(best["s"]) if best else None


def trend_between(prev_key: str | None, now_key: str) -> str:
    """▲ avanço / ▼ recuo / = mesma etapa. Sem 'ontem' conhecido -> 'new' (sem seta:
    fabricar '=' diria que a tarefa não se moveu, o que não sabemos)."""
    if prev_key is None or prev_key not in _KEY2ORDINAL:
        return "new"
    a, b = _KEY2ORDINAL[prev_key], _KEY2ORDINAL[now_key]
    return "up" if b > a else ("down" if b < a else "same")


# ------------------------------------------------------------------------- quadro
def build_board(token: str, cutoff_ms: int, cutoff_label: str, as_of: str,
                window_start_ms: int, history_from: str, now_ms: int) -> dict:
    """Monta o dict `tasks` que o dashboard.html consome.

    Emite as tarefas CRUAS (`items`, com o histórico de status normalizado junto), não as
    colunas já montadas: é o dashboard que distribui as tarefas nas 5 colunas, para a
    data selecionada no filtro do quadro -- mesma convenção do resto do repositório
    ("dado base no arquivo, agregação no navegador", igual aos pedidos do Magento).
    `columns` fica só com as definições (rótulo/ícone/cor), sem cartões dentro, para não
    existirem duas versões do mesmo quadro.

    `cutoff_ms`       -- fechamento de ontem, em epoch ms (base das setas de HOJE; a tela
                         recalcula a seta da data escolhida a partir do mesmo histórico)
    `window_start_ms` -- início da janela de reconstrução (ver HISTORY_WINDOW_DAYS)
    `history_from`    -- a mesma data em texto (YYYY-MM-DD): limite do seletor de data
    """
    tasks = fetch_view_tasks(token)

    items: list[dict] = []
    statuses: dict[str, dict] = {}   # catálogo p/ o filtro de status da tela
    unmapped: dict[str, int] = {}
    ignored = 0
    history_calls = 0
    no_history = 0
    no_usable_since = 0
    with_history = 0

    def see_status(name: str, color, key: str | None) -> None:
        """Registra o status (atual OU histórico) no catálogo do filtro. Os status
        históricos importam: uma data passada pode conter status que hoje ninguém tem."""
        if not name:
            return
        entry = statuses.setdefault(name, {"col": key, "color": color or None})
        if not entry.get("color") and color:
            entry["color"] = color

    for t in tasks:
        st = status_name(t)
        key = column_key(st)
        if st in IGNORED_STATUSES:
            ignored += 1
        elif key is None and st:
            unmapped[st] = unmapped.get(st, 0) + 1
        raw_status = t.get("status")
        see_status(st, raw_status.get("color") if isinstance(raw_status, dict) else None, key)

        done_ms = completed_ms(t)
        # Concluída antes da janela: em qualquer data reconstruível ela já estava
        # concluída, então a data de conclusão basta -- não gasta chamada.
        needs_history = key != DONE_KEY or (done_ms is not None and done_ms >= window_start_ms)

        hist_rows: list[dict] | None = None
        unsure_ms: int | None = None
        if needs_history:
            raw = fetch_status_history(token, t["id"])
            history_calls += 1
            if not raw:
                no_history += 1
            elif not any(history_since(h) is not None for h in raw):
                # histórico veio, mas nenhum `since` legível -> o formato do payload mudou.
                # Sem esta contagem o sintoma seria só "tudo virou 'new'", silenciosamente.
                no_usable_since += 1
            for h in raw:
                hs = str(h.get("status") or "").strip().lower()
                see_status(hs, h.get("color"), column_key(hs))
            hist_rows = normalize_history(raw)
            unsure_ms = unsure_before(raw, now_ms)
            if hist_rows:
                with_history += 1

        item = {
            "id": t.get("id"),
            "title": t.get("name") or "(sem título)",
            "status": st,
            "column": key,                      # coluna HOJE (None = fora do quadro)
            "url": t.get("url"),
            "list": (t.get("list") or {}).get("name"),
            "updated_ms": _ms(t.get("date_updated")),
            "created_ms": _ms(t.get("date_created")),
            "completed_ms": done_ms,
        }
        if hist_rows is not None:
            item["hist"] = hist_rows           # ausente = histórico não consultado
        if unsure_ms is not None:
            # antes deste instante a trilha desta tarefa tem visitas escondidas: a tela
            # mostra o cartão marcado com "?" em vez de afirmar a etapa (ver unsure_before)
            item["unsure_before"] = unsure_ms
        items.append(item)

    # Setas de HOJE, calculadas aqui só para as checagens de sanidade abaixo (a tela
    # recalcula as suas a partir de `hist`, para a data que estiver selecionada).
    active = [i for i in items if i["column"] not in (None, DONE_KEY)]
    for i in active:
        i["trend_today"] = trend_between(
            (lambda b: column_key(b["s"]) if b else None)(status_at(i.get("hist") or [], cutoff_ms)),
            i["column"],
        )

    lists_seen = sorted({(t.get("list") or {}).get("name", "") for t in tasks} - {""})

    # Um quadro inteiro sem base de comparação é implausível (significaria que TODAS as
    # tarefas nasceram hoje) -- é a assinatura de um `since` ilegível. Sinalizamos para
    # o sintoma não passar por "hoje ninguém se moveu".
    all_new = bool(active) and all(i.get("trend_today") == "new" for i in active)

    return {
        "source": "clickup_live_api",
        "as_of": as_of,
        "trend_cutoff": cutoff_label,
        "view": BOARD_VIEW_ID,
        "lists": lists_seen,
        # definições das colunas (sem cartões) + tarefas cruas: a tela monta o quadro
        "columns": [{k: c[k] for k in ("key", "label", "icon", "color")} for c in COLUMNS],
        "items": items,
        "statuses": statuses,
        "done_key": DONE_KEY,
        "done_top_n": DONE_TOP_N,
        "ignored_statuses": sorted(IGNORED_STATUSES),
        # limite do filtro de data: antes disto a reconstrução ficaria incompleta
        "history_from": history_from,
        "history_window_days": HISTORY_WINDOW_DAYS,
        "pipeline": PIPELINE,
        "stats": {
            "tasks_in_view": len(tasks),
            "ignored_backlog": ignored,
            "unmapped": unmapped,
            "done_total": sum(1 for i in items if i["column"] == DONE_KEY),
            "active_total": len(active),
            "history_calls": history_calls,
            "tasks_with_history": with_history,
            "tasks_without_history": no_history,
            "tasks_without_usable_since": no_usable_since,
            "tasks_with_hidden_visits": sum(1 for i in items if i.get("unsure_before")),
            "all_new_suspicious": all_new,
        },
    }
