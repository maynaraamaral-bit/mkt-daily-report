"""Log de mudanças de status de UMA tarefa, com a coluna (1..5) e a setinha.

    python task_log.py 868ggetw0
    python task_log.py "bulk pack"            # casa por pedaço do título, dentro da view
    python task_log.py 868ggetw0 --cutoff 2026-07-26

Usa as MESMAS funções que o dashboard (`clickup_client`): mapa de status -> coluna,
`history_since`, `column_at` e `trend_between`. Se a regra da seta mudar lá, muda aqui
junto -- é de propósito, para a tabela nunca divergir do que o quadro mostra.

Só leitura. Precisa de CLICKUP_TOKEN no ../.env.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

try:  # acento no console cp1252 mata o script no meio; já aconteceu com o probe
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")  # as mensagens de erro também têm acento
except Exception:  # noqa: BLE001
    pass

import clickup_client as cc

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PHOENIX = cc.__dict__.get("PHOENIX") or __import__("datetime").timezone(timedelta(hours=-7))

GLYPH = {"up": "▲", "down": "▼", "same": "=", "new": "novo"}
COL_KEYS = [c["key"] for c in cc.COLUMNS]
COL_LABEL = {c["key"]: c["label"] for c in cc.COLUMNS}


def load_env(path: Path) -> dict:
    env = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def ordinal(key: str | None) -> str:
    return str(COL_KEYS.index(key) + 1) if key in COL_KEYS else "--"


def phx(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, PHOENIX).strftime("%d/%m/%Y %H:%M:%S")


def dur(h: dict) -> str:
    """`total_time` vem como dict {'by_minute': N} no REST cru, ou string já formatada
    na forma normalizada (ferramentas MCP)."""
    tt = h.get("total_time")
    if isinstance(tt, str):
        return tt
    mins = 0
    if isinstance(tt, dict):
        mins = int(tt.get("by_minute") or 0)
    elif isinstance(h.get("total_time_minutes"), (int, float)):
        mins = int(h["total_time_minutes"])
    d, rem = divmod(mins, 1440)
    hh, mm = divmod(rem, 60)
    return (f"{d}d " if d else "") + (f"{hh}h " if (hh or d) else "") + f"{mm}m"


def resolve_task(token: str, arg: str) -> tuple[str, str]:
    """Devolve (task_id, título). Aceita id direto ou pedaço do título."""
    # Não dá para adivinhar id pela forma da string ("dashboard" tem 9 chars e nenhum
    # espaço, igual a um id como "868ggetw0"). Então PERGUNTA à API: se existe tarefa com
    # esse id, é id; se der 404, trata como pedaço de título.
    if " " not in arg:
        try:
            return arg, str(cc._get(token, f"/task/{arg}").get("name") or "")
        except cc.ClickUpError:
            pass  # não é id -> segue para a busca por título
    tasks = cc.fetch_view_tasks(token)
    hits = [t for t in tasks if arg.lower() in str(t.get("name", "")).lower()]
    if not hits:
        sys.exit(f'Nenhuma tarefa da view com "{arg}" no título. '
                 f"(A view tem {len(tasks)} tarefas; passe o id se ela estiver fora dela.)")
    if len(hits) > 1:
        print(f'{len(hits)} tarefas casam com "{arg}":')
        for t in hits:
            print(f"   {t['id']}  {t.get('name')}")
        sys.exit("Rode de novo com o id exato.")
    return hits[0]["id"], hits[0].get("name", "")


def main() -> None:
    args = [a for a in sys.argv[1:]]
    if not args:
        sys.exit(__doc__)

    cutoff_arg = None
    if "--cutoff" in args:
        i = args.index("--cutoff")
        cutoff_arg = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    if not args:
        sys.exit("Falta o id ou o título da tarefa.")

    token = load_env(ROOT / ".env").get("CLICKUP_TOKEN", "").strip()
    if not token:
        sys.exit("CLICKUP_TOKEN ausente em ../.env")

    task_id, title = resolve_task(token, " ".join(args))
    hist = cc.fetch_status_history(token, task_id)
    if not hist:
        sys.exit(f"{task_id}: sem status_history (ClickApp 'Total time in Status' desligado?)")

    usable = [h for h in hist if cc.history_since(h) is not None]
    if not usable:
        sys.exit(f"{task_id}: {len(hist)} entradas de histórico, mas nenhuma com `since` legível "
                 f"-- o formato do payload mudou; ver clickup_client.history_since()")

    seq = sorted(usable, key=cc.history_since)

    print("=" * 104)
    print(f"{title or task_id}")
    print(f"https://app.clickup.com/t/{task_id}")
    print("=" * 104)
    print(f"{'#':>2}  {'quando (Phoenix)':<21} {'status':<26} {'col':>3}  {'seta':<5} tempo acumulado")
    print("-" * 104)

    prev_key = None
    for i, h in enumerate(seq, 1):
        st = str(h.get("status") or "").strip().lower()
        key = cc.column_key(st)
        if prev_key is None or key is None:
            arrow = "-"          # primeira entrada, ou status fora do mapa: sem base
        else:
            arrow = GLYPH[cc.trend_between(prev_key, key)]
        print(f"{i:>2}  {phx(cc.history_since(h)):<21} {st:<26} {ordinal(key):>3}  {arrow:<5} {dur(h)}")
        if key is not None:
            prev_key = key

    # --- o que o report diário mostraria ------------------------------------------
    now = datetime.now(PHOENIX)
    if cutoff_arg:
        d = datetime.strptime(cutoff_arg, "%Y-%m-%d")
        cutoff = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=PHOENIX)
    else:
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)

    cur_st = str(seq[-1].get("status") or "").strip().lower()
    cur_key = cc.column_key(cur_st)
    prev_at = cc.column_at(usable, int(cutoff.timestamp() * 1000))
    trend = cc.trend_between(prev_at, cur_key) if cur_key else "new"

    print("-" * 104)
    print(f"Corte da comparação : {cutoff.strftime('%d/%m/%Y %H:%M:%S')} Phoenix"
          f"{'  (--cutoff)' if cutoff_arg else '  (fechamento de ontem)'}")
    print(f"No corte            : coluna {ordinal(prev_at)} "
          f"{'(' + COL_LABEL.get(prev_at, '—') + ')' if prev_at else '(a tarefa não existia / sem base)'}")
    print(f"Agora               : coluna {ordinal(cur_key)} "
          f"({COL_LABEL.get(cur_key, cur_st)}) · status `{cur_st}`")
    print(f"SETA NO REPORT      : {GLYPH[trend]}   ({trend})")

    # Mesma conta que decide o "?" no quadro: até onde dá para confiar nesta trilha.
    unsure = cc.unsure_before(usable, int(now.timestamp() * 1000))
    print(f"Trilha confiável de : "
          + ("sempre (nenhuma visita escondida detectada)" if unsure is None
             else f"{phx(unsure)} em diante — antes disso a tarefa repetiu status, então o "
                  f"quadro mostra '?' em vez de afirmar a etapa"))

    print()
    print("⚠ Este log é um PISO, não a trilha completa: `since` é a ÚLTIMA vez que a tarefa entrou")
    print("  em cada status e `total_time` é acumulado entre todas as visitas, então idas e voltas")
    print("  repetidas ao mesmo status ficam invisíveis. (Sinal disso: tempo acumulado maior que o")
    print("  intervalo desde o `since`.) A API também devolve ordenado pela posição do status no")
    print("  workflow, não por data -- a ordem acima foi refeita por tempo.")


if __name__ == "__main__":
    # A API do ClickUp dá timeout esporádico (o cliente já tenta 4x com backoff). Se ainda
    # falhar, mostrar uma linha em vez de traceback -- isto aqui é ferramenta de uso diário.
    try:
        main()
    except cc.ClickUpError as e:
        sys.exit(f"ClickUp: {e}\n"
                 f"  · timeout / 5xx  -> é intermitente nesse endpoint, rode de novo\n"
                 f"  · 401            -> confira o CLICKUP_TOKEN em ../.env\n"
                 f"  · 404            -> a tarefa ou a view não existe mais")
    except KeyboardInterrupt:
        sys.exit(130)
