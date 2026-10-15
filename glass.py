#!/usr/bin/env python3
"""glass - phone screen-glass lookup for Absolute Mobile Screen.
Pure Python 3 standard library. Data: glass.sqlite next to this file."""
import argparse, difflib, hashlib, json, os, re, shlex, sqlite3, sys, tempfile, time
import urllib.error, urllib.request
from collections import OrderedDict, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "glass.sqlite")

# ---------------------------------------------------------------- self-update (GitHub feed)
# Public repo amscreensolution-a11y/glass-expert-feed; stable raw URLs per filename.
FEED_BASE = "https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/"
MANIFEST_URL = FEED_BASE + "manifest.json"
UPDATE_STAMP = os.path.join(HERE, ".glass_last_update")
UPDATE_INTERVAL = 24 * 3600  # seconds


def _feed_url(name):
    return FEED_BASE + name


def _http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "glass-expert/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        # Drive virus-scan HTML interstitial (rare with confirm=t); detect and bail
        ctype = (resp.headers.get("Content-Type") or "").lower()
        head = data[:2000].lstrip().lower()
        if "text/html" in ctype and (head.startswith(b"<!doctype") or head.startswith(b"<html")):
            if b"drive.google" in head or b"download_warning" in head or b"uc-download-link" in head:
                raise RuntimeError("Drive confirmation page; open URL in a browser once")
        return data


def _sha256(path_or_bytes):
    h = hashlib.sha256()
    if isinstance(path_or_bytes, (bytes, bytearray)):
        h.update(path_or_bytes)
        return h.hexdigest()
    with open(path_or_bytes, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_replace(src_tmp, dest):
    os.replace(src_tmp, dest)


def data_as_of_line(con=None):
    """Return 'data as of <date>' from local stamp or DB mtime."""
    version = None
    stamp = os.path.join(HERE, ".glass_version")
    if os.path.exists(stamp):
        try:
            version = open(stamp, encoding="utf-8").read().strip()
        except Exception:
            pass
    if not version and os.path.exists(DB):
        version = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(DB)))
    return "data as of %s" % (version or "unknown")


def _should_check_update(force=False):
    if force:
        return True
    try:
        if not os.path.exists(UPDATE_STAMP):
            return True
        age = time.time() - os.path.getmtime(UPDATE_STAMP)
        return age >= UPDATE_INTERVAL
    except Exception:
        return True


def _touch_update_stamp():
    try:
        open(UPDATE_STAMP, "w").close()
    except Exception:
        pass


def check_update(force=False, quiet=True):
    """Fetch manifest; if newer, download sqlite (and glass.py if changed). Fail silent offline."""
    if not _should_check_update(force):
        return False
    try:
        raw = _http_get(MANIFEST_URL, timeout=30)
        man = json.loads(raw.decode("utf-8"))
    except Exception as e:
        if force and not quiet:
            print("update check failed: %s" % e)
        _touch_update_stamp()  # don't hammer when offline
        return False
    local_ver = None
    stamp = os.path.join(HERE, ".glass_version")
    if os.path.exists(stamp):
        try:
            local_ver = open(stamp, encoding="utf-8").read().strip()
        except Exception:
            pass
    remote_ver = str(man.get("version") or "")
    if not force and local_ver and remote_ver and remote_ver <= local_ver:
        _touch_update_stamp()
        return False
    files = man.get("files") or {}
    updated = False
    # sqlite
    sq = files.get("glass.sqlite") or {}
    expect = (sq.get("sha256") or "").lower()
    try:
        data = _http_get(sq.get("url") or _feed_url("glass.sqlite"), timeout=120)
        if expect and _sha256(data) != expect:
            if force:
                print("sqlite sha256 mismatch; skipped")
            _touch_update_stamp()
            return False
        fd, tmp = tempfile.mkstemp(prefix="glass-", suffix=".sqlite", dir=HERE)
        os.close(fd)
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            _atomic_replace(tmp, DB)
        except Exception:
            try:
                os.remove(tmp)
            except Exception:
                pass
            raise
        updated = True
    except Exception as e:
        if force and not quiet:
            print("sqlite download failed: %s" % e)
        _touch_update_stamp()
        return False
    # glass.py (optional)
    py = files.get("glass.py") or {}
    pexpect = (py.get("sha256") or "").lower()
    try:
        local_py = os.path.join(HERE, "glass.py")
        if pexpect and os.path.exists(local_py) and _sha256(local_py) != pexpect:
            pdata = _http_get(py.get("url") or _feed_url("glass.py"), timeout=60)
            if pexpect and _sha256(pdata) != pexpect:
                raise RuntimeError("glass.py sha256 mismatch")
            fd, tmp = tempfile.mkstemp(prefix="glass-", suffix=".py", dir=HERE)
            os.close(fd)
            try:
                with open(tmp, "wb") as f:
                    f.write(pdata)
                os.chmod(tmp, 0o755)
                _atomic_replace(tmp, local_py)
            except Exception:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                raise
            updated = True
    except Exception as e:
        if force and not quiet:
            print("glass.py update skipped: %s" % e)
    try:
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(remote_ver + "\n")
    except Exception:
        pass
    _touch_update_stamp()
    if force or not quiet:
        print("updated to %s" % remote_ver)
    return updated


# ---------------------------------------------------------------- colour
def _colour_ok():
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            os.system("")  # enables ANSI escapes on Windows 10+
        except Exception:
            return False
    return True
COLOR = _colour_ok()
def c(s, code):
    return "\033[%sm%s\033[0m" % (code, s) if COLOR else str(s)
B = lambda s: c(s, "1"); CY = lambda s: c(s, "1;36"); GR = lambda s: c(s, "32")
YE = lambda s: c(s, "1;33"); RE_ = lambda s: c(s, "31"); DIM = lambda s: c(s, "2")

# ---------------------------------------------------------------- names
ALIASES = {"sam": "samsung", "samsung": "samsung", "galaxy": "samsung", "vivo": "vivo",
           "iqoo": "iqoo", "iq00": "iqoo", "iqo0": "iqoo", "iq0o": "iqoo", "oppo": "oppo",
           "realme": "realme", "relme": "realme", "rm": "redmi", "redmi": "redmi", "poco": "poco",
           "mi": "xiaomi", "xiaomi": "xiaomi", "xiomi": "xiaomi", "oneplus": "oneplus",
           "1plus": "oneplus", "1+": "oneplus", "op": "oneplus", "hw": "huawei", "huawei": "huawei",
           "honor": "honor", "moto": "motorola", "motorola": "motorola", "mt": "motorola",
           "infinix": "infinix", "inf": "infinix", "tecno": "tecno", "itel": "itel",
           "nokia": "nokia", "apple": "apple", "google": "google", "nothing": "nothing",
           "cmf": "nothing", "sony": "sony", "lava": "lava"}
DROP = {"by", "version", "verison", "global", "india", "in", "cn", "pk", "intl"}
FAM_LABEL = {"samsung": "Samsung", "vivo": "vivo", "iqoo": "iQOO", "oppo": "OPPO", "realme": "realme",
             "redmi": "Redmi", "poco": "POCO", "xiaomi": "Xiaomi", "oneplus": "OnePlus",
             "huawei": "Huawei", "honor": "Honor", "motorola": "Motorola", "infinix": "Infinix",
             "tecno": "Tecno", "itel": "itel", "nokia": "Nokia", "apple": "Apple", "google": "Google",
             "nothing": "Nothing", "sony": "Sony", "lava": "Lava", "": "Unknown brand"}

def parse_name(text, brand_hint=""):
    """-> (family, core key, net). 'SAM A05S' -> ('samsung','a05s','')"""
    s = (text or "").lower().replace("1+", " 1plus ").replace("+", " plus ")
    s = s.replace("iq00", "iqoo")
    toks = re.findall(r"[a-z0-9]+", s)
    fam, core, net = "", [], ""
    for t in toks:
        if t in ALIASES and not core:
            f = ALIASES[t]
            # sub-brands win over parents: vivo iqoo -> iqoo, xiaomi redmi -> redmi
            if not fam or f in ("iqoo", "redmi", "poco") or fam == "samsung" and f == "samsung":
                fam = f
            continue
        if t in ("4g", "5g"):
            net = t; continue
        if t in DROP or t == "galaxy":
            continue
        core.append(t)
    if not fam and brand_hint:
        fam = parse_name(brand_hint)[0]
    return fam, "".join(core), net

# ---------------------------------------------------------------- db helpers
def db():
    if not os.path.exists(DB):
        sys.exit("glass.sqlite not found next to glass.py (%s)" % DB)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

_INDEX = None
def index(con):
    global _INDEX
    if _INDEX is None:
        _INDEX = con.execute("select * from name_index").fetchall()
    return _INDEX

def score(q, cand):
    qf, qk, qn = q
    if not qk:
        return 0
    f, k, n = cand["fam"], cand["core"], cand["net"]
    if qf and f and qf != f:
        return 0
    r = 1.0 if qk == k else difflib.SequenceMatcher(None, qk, k).ratio()
    if not k:
        return 0
    if qk != k and (k.startswith(qk) or qk.startswith(k)) and \
            min(len(qk), len(k)) / max(len(qk), len(k)) >= 0.6:
        r = max(r, 0.8)
    if qf and not f:
        r -= 0.05
    if qn and n and qn != n:
        r -= 0.02
    return r

def find(con, text, n=8):
    q = parse_name(text)
    best = {}
    for row in index(con):
        s = score(q, row)
        key = (row["fam"], row["core"])
        if s > best.get(key, (0,))[0]:
            best[key] = (s, row["label"])
    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])
    return q, [(k, v[0], v[1]) for k, v in ranked[:n] if v[0] > 0.45]

def tier_of(con, code):
    return con.execute("select * from tiers where code=?", (code,)).fetchone()

def tier_txt(t):
    if not t:
        return DIM("tier: no demand data")
    col = {"A": GR, "B": CY, "C": YE}.get(t["tier"], DIM)
    return "%s  rank #%s, %.2f%% of India demand" % (col("Tier " + str(t["tier"])), t["rank_all"], t["demand_idx"])

def group_mates(con, group_id):
    return con.execute("""select m.model_name, m.fam from ps_group_models gm join ps_models m
        using(model_id) where gm.group_id=? order by gm.position""", (group_id,)).fetchall()

def by_brand(rows):
    d = OrderedDict()
    for name, fam in sorted(rows, key=lambda r: (FAM_LABEL.get(r[1] or "", r[1] or "zz").lower(), r[0])):
        d.setdefault(FAM_LABEL.get(fam or "", fam), []).append(name)
    return d

def print_brands(rows, indent="      ", skip=()):
    rows = [r for r in rows if r[0] not in skip]
    if not rows:
        print(indent + DIM("(no other models on this glass)")); return
    for brand, names in by_brand(rows).items():
        print(indent + B(brand + ":") + " " + ", ".join(names))

# ---------------------------------------------------------------- commands
def cmd_model(con, text):
    q, hits = find(con, text)
    if not hits or hits[0][1] < 0.72:
        print(RE_("No confident match for '%s'." % text))
        if hits:
            print("Closest: " + "; ".join(h[2] for h in hits[:6]))
        return
    (fam, core), sc, _ = hits[0]
    show_phone(con, fam, core)
    near = [h[2] for h in hits[1:6] if h[1] >= 0.75]
    if sc < 1:
        print(DIM("\n(matched '%s' by similarity %.0f%%)" % (text, sc * 100)))
    if near:
        print(DIM("Similar names: " + "; ".join(near)))

def show_phone(con, fam, core):
    ps = con.execute("select * from ps_models where fam=? and core=?", (fam, core)).fetchall()
    gs = con.execute("select * from gsm where fam=? and core=? order by announced desc", (fam, core)).fetchall()
    title = (gs[0]["full_name"] if gs else ps[0]["model_name"])
    print(CY("=" * 64)); print(CY(" " + title)); print(CY("=" * 64))
    if ps:
        print(DIM("Princeshop listing names: " + ", ".join(sorted({p["model_name"] for p in ps}))))
    for g in gs[:3]:
        bits = [g["full_name"]]
        if g["series"]: bits.append("series " + B(g["series"]))
        if g["generation"]: bits.append("gen " + B(g["generation"]))
        if g["announced"]: bits.append("announced " + g["announced"])
        if g["display_in"]: bits.append('%.2f"' % g["display_in"])
        print("  " + " | ".join(bits))
    # product lines
    groups = OrderedDict()
    own = set()
    for p in ps:
        own.add(p["model_name"])
        for gr in con.execute("""select g.*, gm.raw_model from ps_group_models gm join ps_groups g using(group_id)
                where gm.model_id=? order by g.line_order""", (p["model_id"],)):
            groups[gr["group_id"]] = gr
    codes_seen = {g["sku_code"] for g in groups.values() if g["sku_code"]}
    extra = []
    for g in gs:
        for part in (g["glass_detail"] or "").split(";"):
            if ":" in part:
                line, code = [x.strip() for x in part.split(":", 1)]
                if code not in codes_seen:
                    codes_seen.add(code)
                    rows = con.execute("select * from ps_groups where sku_code=? order by line_order", (code,)).fetchall()
                    if rows:
                        for r in rows: groups[r["group_id"]] = r
                    else:
                        extra.append((line, code))
    if groups or extra:
        print(B("\nGLASS CODES"))
        for g in groups.values():
            code = g["sku_code"] or DIM("(no code on site, group %s)" % g["group_id"])
            print("  %-26s %s" % (g["line"], YE(code)))
            if g["notes"]:
                print("      note: " + g["notes"])
            print_brands([(m["model_name"], m["fam"]) for m in group_mates(con, g["group_id"])], skip=own)
        for line, code in extra:
            print("  %-26s %s" % (line, YE(code)))
        arc = [g["sku_code"] for g in groups.values() if g["sku_code"] and g["line"] == "ARC"]
        priv_own = [g["sku_code"] for g in groups.values() if g["sku_code"] and g["line"] == "ARC Privacy"]
        print(B("\nDEMAND"))
        for code in sorted({g["sku_code"] for g in groups.values() if g["sku_code"]} | {e[1] for e in extra}):
            print("  %-8s %s" % (code, tier_txt(tier_of(con, code))))
        print(B("\nPRIVACY PAIR"))
        if priv_own:
            print("  This model's ARC Privacy glass: " + YE(", ".join(priv_own)))
        shown = False
        for a in arc:
            p = con.execute("select * from privacy_pairs where arc_code=?", (a,)).fetchone()
            if p:
                shown = True
                print("  ARC %s -> privacy %s (%.0f%% of %s demand also fits it)" % (a, YE(p["privacy_code"]), p["share"] * 100, a))
        if not shown and not priv_own:
            print(DIM("  No privacy pairing on record."))
    else:
        print(B("\nGLASS CODES"))
        print(RE_("  Not listed by Princeshop."))
        pr = [g for g in gs if g["pred_code"]]
        if pr:
            g = pr[0]
            print("  Predicted ARC code: %s  (confidence: %s%s)  %s" % (
                YE(g["pred_code"]), g["pred_confidence"] or "?",
                ", alternatives " + g["pred_alt"] if g["pred_alt"] else "", RE_("TEST-FIT FIRST")))
            print("      " + tier_txt(tier_of(con, g["pred_code"])))
        else:
            print(DIM("  No prediction available either - check by physical fit."))

def cmd_code(con, code):
    code = code.strip().upper()
    rows = con.execute("select * from ps_groups where upper(sku_code)=? order by line_order", (code,)).fetchall()
    if not rows:
        codes = [r[0] for r in con.execute("select distinct sku_code from ps_groups where sku_code is not null")]
        print(RE_("No code %s." % code) + " Closest: " + ", ".join(difflib.get_close_matches(code, codes, 6, 0.5)))
        return
    print(CY("Code %s" % code) + "   " + tier_txt(tier_of(con, code)))
    for g in rows:
        mates = [(m["model_name"], m["fam"]) for m in group_mates(con, g["group_id"])]
        print(B("\n%s  -  %d models" % (g["line"], len(mates))))
        if g["notes"]: print("  note: " + g["notes"])
        print_brands(mates, indent="  ")
    p = con.execute("select * from privacy_pairs where arc_code=?", (code,)).fetchone()
    if p:
        print("\nPrivacy pair: %s (%.0f%%)" % (YE(p["privacy_code"]), p["share"] * 100))

def code_str(g):
    if g["glass_detail"]:
        return "  ".join(OrderedDict.fromkeys(x.strip() for x in g["glass_detail"].split(";")))
    if g["pred_code"]:
        return "predicted %s (%s, test-fit first)" % (g["pred_code"], g["pred_confidence"])
    return DIM("-")

def list_models(rows, title):
    print(CY("%s  (%d models)" % (title, len(rows))))
    for g in rows:
        print("  %-8s %-34s %s" % (g["announced"] or "", g["full_name"][:34], code_str(g)))

def cmd_series(con, name, year=None):
    names = [r[0] for r in con.execute("select distinct series from gsm where series is not null")]
    match = [n for n in names if n.lower() == name.lower()]
    if not match:
        close = difflib.get_close_matches(name, names, 6, 0.5)
        print(RE_("No series '%s'." % name) + (" Closest: " + ", ".join(close) if close else "")); return
    sql = "select * from gsm where lower(series)=? and device_type in ('smartphone','phone')"
    args = [name.lower()]
    if year: sql += " and year=?"; args.append(year)
    list_models(con.execute(sql + " order by brand, announced desc", args).fetchall(), "Series " + match[0])

def cmd_brand(con, name, year=None):
    fam = parse_name(name)[0] or name.lower()
    sql = "select * from gsm where fam=? and device_type='smartphone'"
    args = [fam]
    if year: sql += " and year=?"; args.append(year)
    rows = con.execute(sql + " order by announced desc", args).fetchall()
    if not rows:
        print(RE_("No models for brand '%s'%s." % (name, " in %s" % year if year else ""))); return
    list_models(rows, "%s%s" % (FAM_LABEL.get(fam, fam), " " + str(year) if year else ""))

def cmd_top(con, n=25, line=None):
    sql, args = "select * from tiers", []
    if line: sql += " where lower(line) like ?"; args.append("%" + line.lower() + "%")
    rows = con.execute(sql + " order by demand_idx desc limit ?", args + [n]).fetchall()
    print(CY("Top %d codes by India demand" % len(rows)))
    print(DIM("  rank code     tier  demand%  line                 top phones"))
    for i, r in enumerate(rows, 1):
        print("  %4d %-8s %-5s %6.2f   %-20s %s" % (i, YE(r["code"]) if COLOR else r["code"], r["tier"],
              r["demand_idx"], (r["line"] or "")[:20], (r["top_phones"] or "")[:60]))

def cmd_new(con, n=25):
    rows = con.execute("""select * from gsm where device_type='smartphone' and announced is not null
        order by announced desc limit ?""", (n,)).fetchall()
    list_models(rows, "Most recent launches")

def cmd_compare(con, a, b):
    sides = []
    for t in (a, b):
        q, hits = find(con, t)
        if not hits or hits[0][1] < 0.72:
            print(RE_("Can't identify '%s'." % t) + (" Closest: " + "; ".join(h[2] for h in hits[:5]) if hits else ""))
            return
        fam, core = hits[0][0]
        codes = {}
        for r in con.execute("""select g.line, g.sku_code, g.group_id from ps_models m join ps_group_models gm using(model_id)
                join ps_groups g using(group_id) where m.fam=? and m.core=?""", (fam, core)):
            codes.setdefault(r["line"], set()).add(r["sku_code"] or r["group_id"])
        for g in con.execute("select glass_detail from gsm where fam=? and core=?", (fam, core)):
            for part in (g[0] or "").split(";"):
                if ":" in part:
                    l, cd = [x.strip() for x in part.split(":", 1)]
                    codes.setdefault(l, set()).add(cd)
        sides.append((hits[0][2], codes))
    (na, ca), (nb, cb) = sides
    print(CY("%s  vs  %s" % (na, nb)))
    same = False
    for line in sorted(set(ca) | set(cb)):
        x, y = ca.get(line, set()), cb.get(line, set())
        shared = x & y
        same |= bool(shared)
        mark = GR("SAME") if shared else (RE_("different") if x and y else DIM("only one listed"))
        print("  %-24s %-14s %-14s %s" % (line, ",".join(sorted(x)) or "-", ",".join(sorted(y)) or "-", mark))
    print(B("\nResult: ") + (GR("they share at least one glass (see SAME rows).") if same
                              else RE_("no shared glass on record - do not swap.")))

def cmd_stats(con):
    for t in ("ps_models", "ps_groups", "gsm", "tiers", "privacy_pairs"):
        print("%-14s %d rows" % (t, con.execute("select count(*) from " + t).fetchone()[0]))

HELP = """Commands:
  <model name>              look up a phone, e.g.  vivo V80 / sam a05s / reno 14 pro
  code F018                 every model on a glass code
  series Reno [--year 2025] models in a series with their codes
  brand vivo [--year 2025]  models of a brand
  top [N]                   top codes by demand
  new [N]                   most recent launches
  compare "A" "B"           do two phones share a glass?
  update                   fetch latest data from the feed (once/day auto on start)
  help / quit"""

def run(con, argv):
    if not argv: return
    cmd = argv[0].lower()
    year = None
    if "--year" in argv:
        i = argv.index("--year"); year = int(argv[i + 1]); argv = argv[:i] + argv[i + 2:]
    rest = " ".join(argv[1:])
    if cmd == "code" and rest: cmd_code(con, rest)
    elif cmd == "series" and rest: cmd_series(con, rest, year)
    elif cmd == "brand" and rest: cmd_brand(con, rest, year)
    elif cmd == "top": cmd_top(con, int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 25)
    elif cmd == "new": cmd_new(con, int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 25)
    elif cmd == "compare" and len(argv) == 3: cmd_compare(con, argv[1], argv[2])
    elif cmd == "compare": print('Usage: compare "model A" "model B"  (use quotes)')
    elif cmd in ("help", "-h", "--help", "?"): print(HELP)
    elif cmd == "stats": cmd_stats(con)
    elif cmd == "update":
        check_update(force=True, quiet=False)
        print(DIM(data_as_of_line()))
    elif len(argv) == 1 and re.fullmatch(r"[A-Za-z]{1,3}\d{2,4}", argv[0]) and \
            con.execute("select 1 from ps_groups where upper(sku_code)=?", (argv[0].upper(),)).fetchone():
        cmd_code(con, argv[0])
    else: cmd_model(con, " ".join(argv))

def shell(con):
    print(CY("glass - Absolute Mobile Screen glass finder.") + " Type a model, 'help' or 'quit'.")
    while True:
        try:
            line = input(B("glass> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if line.lower() in ("q", "quit", "exit"): break
        try:
            run(con, shlex.split(line))
        except ValueError as e:
            print(RE_(str(e)))
        print()

def main():
    # auto-update at most once per 24h (silent offline); `glass update` forces
    if not (len(sys.argv) > 1 and sys.argv[1].lower() == "update"):
        check_update(force=False, quiet=True)
    if len(sys.argv) > 1 and sys.argv[1].lower() == "update":
        check_update(force=True, quiet=False)
        # reopen after possible swap
        print(DIM(data_as_of_line()))
        return
    con = db()
    if len(sys.argv) == 1:
        print(DIM(data_as_of_line()))
        shell(con)
    else:
        run(con, sys.argv[1:])

if __name__ == "__main__":
    main()
