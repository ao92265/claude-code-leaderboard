#!/usr/bin/env python3
"""build_board.py [--validate-only] [--out site/index.html]

Reads scores/<handle>/<YYYY-MM-DD>.json submissions, validates each against the
strict allowlist (the ONLY data this project may ever hold), computes per-handle
improvement deltas, and renders the static leaderboard page.

Ranking: Δ composite — latest submission vs the handle's earliest submission
(your own past self is the only opponent). No absolute grades on the board.
Qualification: latest corpus must have >= MIN_SESSIONS and >= MIN_FACETS;
otherwise the handle sits in the Calibrating section.

No network. No dependencies beyond the standard library.
"""
import json, os, re, sys, glob, html, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORES = os.path.join(ROOT, "scores")
MIN_SESSIONS, MIN_FACETS = 50, 15          # straw-man thresholds; tune after first cohort
MIN_SUBMISSIONS_FOR_DELTA = 2

ALLOWED_TOP = {"schema_version", "formula_version", "corpus", "factors",
               "composite", "grade", "skill_version"}
ALLOWED_CORPUS = {"n_sessions", "n_facets", "active_days", "as_of"}
ALLOWED_FACTOR = {"name", "score", "kind", "w"}
HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,30}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
E = html.escape


def fail(msg):
    print(f"VALIDATION FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def validate(path, d):
    rel = os.path.relpath(path, ROOT)
    handle, fname = path.split(os.sep)[-2], os.path.basename(path)
    if not HANDLE_RE.match(handle):
        fail(f"{rel}: handle dir must match {HANDLE_RE.pattern}")
    if not DATE_RE.match(fname[:-5]) or not fname.endswith(".json"):
        fail(f"{rel}: filename must be YYYY-MM-DD.json")
    if set(d) != ALLOWED_TOP:
        fail(f"{rel}: top-level keys must be exactly {sorted(ALLOWED_TOP)}, got {sorted(d)}")
    if set(d["corpus"]) != ALLOWED_CORPUS:
        fail(f"{rel}: corpus keys must be exactly {sorted(ALLOWED_CORPUS)}")
    if not (isinstance(d["factors"], list) and len(d["factors"]) == 9):
        fail(f"{rel}: factors must be a list of 9")
    for f in d["factors"]:
        if set(f) != ALLOWED_FACTOR:
            fail(f"{rel}: factor keys must be exactly {sorted(ALLOWED_FACTOR)}")
        if not (isinstance(f["score"], (int, float)) and 0 <= f["score"] <= 100):
            fail(f"{rel}: factor score out of [0,100]")
    if not (isinstance(d["composite"], (int, float)) and 0 <= d["composite"] <= 100):
        fail(f"{rel}: composite out of [0,100]")
    for k in ("n_sessions", "n_facets", "active_days"):
        v = d["corpus"][k]
        if not (isinstance(v, int) and 0 <= v <= 1_000_000):
            fail(f"{rel}: corpus.{k} must be a sane non-negative int")
    if d["corpus"]["as_of"] != fname[:-5]:
        fail(f"{rel}: corpus.as_of must equal the filename date")


def load_all():
    board = {}
    for path in sorted(glob.glob(os.path.join(SCORES, "*", "*.json"))):
        d = json.load(open(path))
        validate(path, d)
        board.setdefault(path.split(os.sep)[-2], []).append(d)
    for subs in board.values():
        subs.sort(key=lambda d: d["corpus"]["as_of"])
    return board


def render(board, out_path):
    ranked, baseline, calibrating = [], [], []
    for handle, subs in board.items():
        latest, earliest = subs[-1], subs[0]
        qualified = (latest["corpus"]["n_sessions"] >= MIN_SESSIONS
                     and latest["corpus"]["n_facets"] >= MIN_FACETS)
        entry = dict(handle=handle, n=len(subs),
                     delta=round(latest["composite"] - earliest["composite"], 1),
                     pb=latest["composite"] >= max(s["composite"] for s in subs),
                     since=earliest["corpus"]["as_of"], latest=latest)
        if not qualified:
            calibrating.append(entry)
        elif len(subs) >= MIN_SUBMISSIONS_FOR_DELTA:
            ranked.append(entry)
        else:
            baseline.append(entry)
    ranked.sort(key=lambda e: -e["delta"])

    def row(i, e):
        cls = "up" if e["delta"] > 0 else ("down" if e["delta"] < 0 else "flat")
        pb = "✦ new PB" if (e["pb"] and e["delta"] > 0) else "—"
        return (f'<div class="row"><span class="rank">{i}</span>'
                f'<span class="handle">{E(e["handle"])}</span>'
                f'<span class="delta {cls}">{e["delta"]:+.1f}</span>'
                f'<span class="pb">{pb}</span>'
                f'<span class="streak">{e["n"]} subs · since {E(e["since"])}</span></div>')

    rows = "".join(row(i, e) for i, e in enumerate(ranked, 1)) or \
        '<div class="row"><span class="rank">—</span><span class="handle" style="color:var(--muted)">no ranked entries yet — deltas need two submissions</span><span></span><span></span><span></span></div>'
    base_rows = "".join(
        f'<div class="row"><span class="rank">·</span><span class="handle">{E(e["handle"])}</span>'
        f'<span class="delta flat">baseline set</span><span class="pb">—</span>'
        f'<span class="streak">1 sub · {E(e["since"])}</span></div>' for e in baseline)
    cal_rows = "".join(
        f'<div class="row cal2"><div><span class="handle">{E(e["handle"])}</span>'
        f'<div class="meta">{e["latest"]["corpus"]["n_sessions"]} / {MIN_SESSIONS} sessions · '
        f'{e["latest"]["corpus"]["n_facets"]} / {MIN_FACETS} analyzed</div></div>'
        f'<div class="prog"><span style="width:{min(100, 100*e["latest"]["corpus"]["n_sessions"]/MIN_SESSIONS):.0f}%"></span></div></div>'
        for e in calibrating) or '<div class="row"><span class="handle" style="color:var(--muted)">nobody calibrating</span></div>'

    built = datetime.date.today().isoformat()
    n_players = len(board)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Harris Claude Code Leaderboard</title>
<style>
:root{{--bg:#08090A;--panel:#0F1011;--elev:#1C1C1F;--ink:#F7F8F8;--body:#D0D6E0;--muted:#8A8F98;--faint:#62666D;--line:#23252A;--line2:#34343A;--link:#7070FF;--hover:#828FFF;--teal:#00B8CC;--green:#27A644;--yellow:#F0BF00;--red:#EB5757}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Inter Variable","SF Pro Display",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;line-height:1.6;letter-spacing:-.011em}}
.wrap{{max-width:880px;margin:0 auto;padding:48px 24px 64px}}
.mono{{font-family:"Berkeley Mono",ui-monospace,"SF Mono",Menlo,monospace}}
.eyebrow{{font-family:ui-monospace,monospace;font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--link);margin:0 0 10px;font-weight:510}}
h1{{font-size:30px;line-height:1.14;margin:0 0 10px;font-weight:590;letter-spacing:-.022em}}
.lede{{color:var(--muted);font-size:14.5px;max-width:64ch;margin:0 0 6px}}
h2{{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-family:ui-monospace,monospace;margin:42px 0 14px;font-weight:510}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:6px 20px;box-shadow:0 3px 12px rgba(0,0,0,.09)}}
.row{{display:grid;grid-template-columns:44px 1fr 110px 110px 170px;gap:12px;align-items:center;padding:13px 0;border-bottom:1px solid var(--line)}}
.row:last-child{{border:none}}
.row.head{{color:var(--faint);font-family:ui-monospace,monospace;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;padding:11px 0 9px}}
.rank{{font-family:ui-monospace,monospace;font-size:14px;color:var(--faint);font-weight:590}}
.handle{{font-weight:590;font-size:14.5px}}
.delta{{font-family:ui-monospace,monospace;font-size:15px;font-weight:590;font-variant-numeric:tabular-nums}}
.up{{color:var(--green)}} .flat{{color:var(--faint)}} .down{{color:var(--red)}}
.pb{{font-family:ui-monospace,monospace;font-size:12px;color:var(--teal)}}
.streak{{font-family:ui-monospace,monospace;font-size:11.5px;color:var(--muted);text-align:right}}
.cap{{color:var(--muted);font-size:12.5px;font-style:italic;margin:12px 2px 0;line-height:1.55}}
.row.cal2{{grid-template-columns:1fr 220px}}
.prog{{background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:6px;height:10px;overflow:hidden}}
.prog span{{display:block;height:100%;background:var(--yellow);border-radius:5px}}
.meta{{font-family:ui-monospace,monospace;font-size:11px;color:var(--faint);margin-top:4px}}
.how{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px 20px;font-size:13.5px;color:var(--body)}}
.how code{{font-family:ui-monospace,monospace;font-size:12px;background:#08090A;border:1px solid var(--line);border-radius:6px;padding:1px 7px}}
.how ol{{margin:8px 0 0;padding-left:20px}} .how li{{margin:5px 0}}
footer{{margin-top:46px;padding:16px 18px;border:1px solid var(--line2);border-radius:12px;background:var(--elev);color:var(--body);font-size:13px;line-height:1.6}}
footer b{{color:var(--ink)}}
.foot2{{margin-top:14px;color:var(--faint);font-size:11.5px;font-family:ui-monospace,monospace;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}}
a{{color:var(--hover)}}
@media(max-width:640px){{.row{{grid-template-columns:34px 1fr 90px}}.pb,.streak{{display:none}}}}
</style>
</head>
<body>
<div class="wrap">
  <p class="eyebrow">Harris · Claude Code · community board</p>
  <h1>Most improved — vs your own baseline</h1>
  <p class="lede">Opt-in, pseudonymous, scores-only. The board ranks <b>Δ composite against your own first submission</b> — quality-weighted (65% of the composite is landing rate, clean first pass, approach accuracy, survival), throughput factors capped, and no lines-of-code anywhere. No absolute grades are shown.</p>

  <h2>Leaderboard — {len(ranked)} ranked · {n_players} players</h2>
  <div class="card">
    <div class="row head"><span>#</span><span>handle</span><span>Δ composite</span><span>personal best</span><span class="streak">history</span></div>
    {rows}
    {base_rows}
  </div>
  <p class="cap">Baseline rows have one submission — the delta race starts on their second. Submissions are strict-allowlist JSON (25 numbers); every row is publicly auditable in <a href="https://github.com/ao92265/claude-code-leaderboard/tree/main/scores">scores/</a>.</p>

  <h2>Calibrating — building corpus to qualify</h2>
  <div class="card">{cal_rows}</div>
  <p class="cap">Qualification: ≥{MIN_SESSIONS} sessions and ≥{MIN_FACETS} analyzed sessions in your latest corpus.</p>

  <h2>How to compete</h2>
  <div class="how">
    <ol>
      <li>Install the <a href="https://github.com/ao92265/claude-code-playbook/tree/main/skills/myinsights">myinsights skill</a> and run <code>/myinsights</code> once.</li>
      <li>Run <code>python3 ~/.claude/skills/myinsights/export_scores.py</code> — it prints your delta and writes <code>scores.json</code> (exactly 25 numbers; review it, that's everything that leaves your machine).</li>
      <li>Fork this repo, add your file as <code>scores/&lt;your-handle&gt;/&lt;YYYY-MM-DD&gt;.json</code>, open a PR. CI validates the allowlist; merge = on the board.</li>
      <li>Resubmit whenever you like. Delete your directory any time — no questions.</li>
    </ol>
  </div>

  <footer>
    <b>This is a voluntary community game, not a performance instrument.</b> Participation is opt-in, handles are pseudonymous, submissions are a strict allowlist (never transcripts, projects, hours, or code), deletion is self-service, and this board must never be used in performance reviews, ranking discussions, or management reporting. If that framing breaks, the board shuts down.
  </footer>
  <div class="foot2">
    <span>built {built} · static · zero trackers</span>
    <span>scores-only by design · <a href="https://github.com/ao92265/claude-code-leaderboard">source</a></span>
  </div>
</div>
</body>
</html>
"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w").write(page)
    print(f"built {out_path}: {len(ranked)} ranked, {len(baseline)} baseline, {len(calibrating)} calibrating")


def main():
    board = load_all()
    total = sum(len(s) for s in board.values())
    print(f"validated {total} submissions from {len(board)} handles")
    if "--validate-only" in sys.argv:
        return
    out = "site/index.html"
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    render(board, os.path.join(ROOT, out) if not os.path.isabs(out) else out)


if __name__ == "__main__":
    main()
