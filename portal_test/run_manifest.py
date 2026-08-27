"""Test harness: extract the ```mysql blocks FROM THE MANIFEST ITSELF, run them against
live Magento, and write data/<name>.json exactly the way the portal would serve them.

This guarantees what I test is literally what's in portal_jem_marketing_daily.md.
"""
import json
import re
from decimal import Decimal
from datetime import date, datetime
from pathlib import Path

import pymysql

HERE = Path(__file__).resolve().parent
DASH = HERE.parent                      # "JEM Marketing Daily Report"
ROOT = DASH.parent                      # repo root (holds the shared .env)
MD = DASH / "portal_jem_marketing_daily.md"
HTML = DASH / "portal_jem_marketing_daily.html"
OUT = HERE / "site" / "data"
OUT.mkdir(parents=True, exist_ok=True)
# keep the served copy of the page in sync, so test_portal.mjs always exercises the
# CURRENT html rather than a stale copy
import shutil
shutil.copyfile(HTML, HERE / "site" / "index.html")


def load_env(path):
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


# --- extract the blocks FROM THE MANIFEST ------------------------------------------
# Format (verified 2026-08-25, enforced by the ai-dashboard skill): YAML frontmatter +
# YAML block BODIES -- `name:`/`connector:` inside the block, SQL under `query: |`.
# The portal's own instruction text describes `name=` on the fence line; that does NOT
# run, and this parser deliberately REFUSES it so a half-reverted manifest fails loudly
# here instead of silently in production.
text = MD.read_text(encoding="utf-8")

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("pyyaml necessário: pip install pyyaml")

# 1. frontmatter -------------------------------------------------------------------
fm_m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
assert fm_m, (
    "manifesto sem frontmatter YAML. O formato verificado exige "
    "---\\ntitle:...\\ncredentials: shared\\nconnectors:\\n  - ...\\n--- no topo."
)
fm = yaml.safe_load(fm_m.group(1)) or {}
for key in ("title", "credentials", "connectors"):
    assert key in fm, f"frontmatter sem `{key}:`"
assert fm["credentials"] == "shared", f"credentials deveria ser 'shared', é {fm['credentials']!r}"
print(f"Frontmatter: title={fm['title']!r} credentials={fm['credentials']!r} "
      f"connectors={fm['connectors']}")

# 2. blocos executáveis (só cerca na coluna 0 -- os indentados são alternativas
#    desativadas de propósito no .md e NÃO devem ser executados) --------------------
raw_blocks = re.findall(r"^```(\w+)\r?\n(.*?)^```", text, re.S | re.M)

assert not re.search(r"^```\w+ +\S+=", text, re.M), (
    "bloco com atributo na linha da cerca (`name=`/`connector=`): esse é o formato da "
    "tela de instruções do portal, que NÃO roda. Ver a seção '⚠ Formato deste arquivo' no .md."
)

parsed = []
rest_blocks = []
for lang, body in raw_blocks:
    d = yaml.safe_load(body)
    assert isinstance(d, dict), f"corpo do bloco ```{lang} não é um mapa YAML"
    assert "name" in d, f"bloco ```{lang} sem `name:` no corpo"
    assert "connector" in d, f"bloco ```{lang} sem `connector:` (obrigatório em TODO bloco)"
    if lang == "mysql":
        assert "query" in d, f"bloco mysql {d['name']} sem `query: |`"
        parsed.append((d["name"], d["connector"], d["query"].strip()))
        print(f"  - mysql {d['name']}  (connector={d['connector']})")
    elif lang == "rest":
        rest_blocks.append(d)
    else:
        print(f"  - {lang} {d['name']}  (não executado por este harness)")

print(f"Found {len(parsed)} mysql block(s) in the manifest")

# declared connectors must cover what the blocks actually use
used = {c for _, c, _ in parsed} | {d["connector"] for d in rest_blocks}
missing = used - set(fm["connectors"] or [])
assert not missing, f"connector usado nos blocos e ausente da frontmatter: {sorted(missing)}"

# also list the rest blocks so I can eyeball them
print(f"\nFound {len(rest_blocks)} rest block(s):")
for d in rest_blocks:
    print(f"  - {d.get('name')}: {d.get('method')} {d.get('path')} select={d.get('select')} "
          f"paginate={d.get('paginate')} credentials={d.get('credentials')}")
    print(f"      query: {d.get('query')}")

env = load_env(ROOT / ".env")
conn = pymysql.connect(
    host=env["MAGENTO_DB_HOST"], port=int(env.get("MAGENTO_DB_PORT", "3306")),
    user=env["MAGENTO_DB_USER"], password=env["MAGENTO_DB_PASSWORD"],
    database=env["MAGENTO_DB_NAME"], cursorclass=pymysql.cursors.DictCursor,
    connect_timeout=20, read_timeout=120,
)


def jsonable(v):
    """Mimic how the portal would hand values to the browser: MySQL decimals and
    dates arrive as STRINGS, ints as numbers."""
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime)):
        return str(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v


print("\n" + "=" * 72)
for name, connector, sql in parsed:
    import time
    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = [{k: jsonable(v) for k, v in r.items()} for r in cur.fetchall()]
    dt = time.time() - t0
    (OUT / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"{name:22s} {len(rows):>6,} rows  {dt:5.2f}s  -> data/{name}.json")
    if rows:
        print(f"{'':22s} sample: {json.dumps(rows[0], ensure_ascii=False)[:200]}")

conn.close()

# --- reconciliation against the known-good reference figures ------------------
orders = json.loads((OUT / "mkt_orders.json").read_text(encoding="utf-8"))
totals = json.loads((OUT / "mkt_totais.json").read_text(encoding="utf-8"))[0]

d = "2026-07-27"
day = [o for o in orders if o["created_at"][:10] == d]
month = [o for o in orders if o["created_at"][:7] == "2026-07"]
amt = lambda rows: round(sum(float(o["amount"]) for o in rows), 2)
top = max(day, key=lambda o: float(o["amount"]))
comp = {o["company_id"] for o in orders if o["company_id"] is not None}

print("\n" + "=" * 72)
print("RECONCILIATION vs the 'Report 27 de Julho' reference")
print("-" * 72)
print(f"  Pedidos 27/07          : {len(day):>10}   (referencia: 32)")
print(f"  Faturamento 27/07      : {amt(day):>10,.2f}")
print(f"  Pedidos no mes (07)    : {len(month):>10}   (referencia: 449 em 27/07)")
print(f"  Pedido destaque 27/07  : {float(top['amount']):,.2f}  #{top['increment_id']}  {top['company_name']}")
print(f"     (referencia: 6,392.75  #JEMUS000002914  Briscoe Protective - Pye-Barker NY)")
print(f"  Companies 1a compra    : {len(comp):>10}   (referencia: 416)")
print(f"  companies_total        : {totals['companies_total']:>10}   (referencia: 2993)")
print(f"  contacts_total         : {totals['contacts_total']:>10}   (referencia: 12036)")
print(f"  db_today / db_now      : {totals['db_today']}  /  {totals['db_now']}")
print("\nDONE")
