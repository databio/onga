#!/usr/bin/env python3
"""Generate a self-contained interactive distribution.html from seed_term_frequency.tsv.

The TSV data is embedded inline so the page works when opened via file://
(no fetch/CORS). Re-run after refreshing the frequency table.

    python make_chart.py
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TSV = HERE / "seed_term_frequency.tsv"
OUT = HERE / "distribution.html"


def load():
    rows = []
    with open(TSV) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            rows.append({
                "term": r["term"],
                "in_encode": r.get("in_encode", "").lower() in ("yes", "true", "1"),
                "file_count": int(r.get("file_count") or 0),
                "dataset_count": int(r.get("dataset_count") or 0),
            })
    return rows


def main():
    rows = load()
    rows.sort(key=lambda d: d["file_count"], reverse=True)
    total_files = sum(r["file_count"] for r in rows)
    zero = sum(1 for r in rows if r["file_count"] == 0)
    data_json = json.dumps(rows)

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ENCODE output_type usage frequency</title>
<style>
  :root { --bar:#2563eb; --bar-zero:#dc2626; --bg:#f8fafc; --fg:#0f172a; --muted:#64748b; }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--fg); }
  header { padding:20px 24px 8px; }
  h1 { margin:0 0 4px; font-size:20px; }
  .sub { color:var(--muted); font-size:13px; }
  .controls { position:sticky; top:0; z-index:5; background:var(--bg);
              padding:12px 24px; border-bottom:1px solid #e2e8f0;
              display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
  .controls input[type=search]{ padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px; min-width:220px; }
  .controls label { display:flex; gap:6px; align-items:center; color:var(--muted); cursor:pointer; user-select:none; }
  .stats { margin-left:auto; color:var(--muted); font-size:13px; }
  main { padding:8px 24px 60px; }
  .row { display:grid; grid-template-columns: 320px 1fr 120px; gap:10px; align-items:center;
         padding:2px 0; border-bottom:1px solid #eef2f7; }
  .term { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .term.zero { color:var(--bar-zero); }
  .track { background:#e9eef5; border-radius:4px; height:16px; position:relative; }
  .fill { background:var(--bar); height:100%; border-radius:4px; min-width:1px; transition:width .15s; }
  .fill.zero { background:var(--bar-zero); opacity:.55; }
  .count { text-align:right; font-variant-numeric:tabular-nums; color:var(--muted); }
  .legend { display:flex; gap:18px; font-size:12px; color:var(--muted); margin-top:4px; }
  .chip { display:inline-block; width:10px; height:10px; border-radius:2px; vertical-align:middle; margin-right:4px; }
</style>
</head>
<body>
<header>
  <h1>ENCODE <code>output_type</code> usage frequency</h1>
  <div class="sub">__NTERMS__ seed terms · __TOTAL__ total ENCODE files · __ZERO__ terms with zero usage (candidates for review)</div>
  <div class="legend">
    <span><span class="chip" style="background:var(--bar)"></span>used in ENCODE</span>
    <span><span class="chip" style="background:var(--bar-zero)"></span>zero usage</span>
  </div>
</header>
<div class="controls">
  <input id="q" type="search" placeholder="Filter terms…" autocomplete="off">
  <label><input type="checkbox" id="logscale" checked> log scale</label>
  <label><input type="checkbox" id="zeroonly"> zero-usage only</label>
  <label>sort
    <select id="sort">
      <option value="file_desc">file count ↓</option>
      <option value="file_asc">file count ↑</option>
      <option value="dataset_desc">dataset count ↓</option>
      <option value="alpha">A–Z</option>
    </select>
  </label>
  <span class="stats" id="stats"></span>
</div>
<main id="chart"></main>

<script>
const DATA = __DATA__;
const maxFile = Math.max(...DATA.map(d => d.file_count), 1);
const chart = document.getElementById('chart');
const q = document.getElementById('q');
const logEl = document.getElementById('logscale');
const zeroEl = document.getElementById('zeroonly');
const sortEl = document.getElementById('sort');
const stats = document.getElementById('stats');

function width(n){
  if (n <= 0) return 0;
  if (logEl.checked){
    return 100 * Math.log10(n+1) / Math.log10(maxFile+1);
  }
  return 100 * n / maxFile;
}
function fmt(n){ return n.toLocaleString(); }

function render(){
  const term = q.value.trim().toLowerCase();
  let rows = DATA.filter(d => !term || d.term.toLowerCase().includes(term));
  if (zeroEl.checked) rows = rows.filter(d => d.file_count === 0);
  const s = sortEl.value;
  rows = rows.slice().sort((a,b)=>{
    if (s==='file_asc') return a.file_count-b.file_count;
    if (s==='dataset_desc') return b.dataset_count-a.dataset_count;
    if (s==='alpha') return a.term.localeCompare(b.term);
    return b.file_count-a.file_count;
  });
  chart.innerHTML = rows.map(d => {
    const z = d.file_count === 0;
    return `<div class="row">
      <div class="term ${z?'zero':''}" title="${d.term}">${d.term}</div>
      <div class="track"><div class="fill ${z?'zero':''}" style="width:${width(d.file_count).toFixed(2)}%"></div></div>
      <div class="count">${fmt(d.file_count)}<span style="opacity:.5"> / ${fmt(d.dataset_count)}</span></div>
    </div>`;
  }).join('');
  stats.textContent = `${rows.length} shown`;
}
[q,logEl,zeroEl,sortEl].forEach(el => el.addEventListener('input', render));
render();
</script>
</body>
</html>
"""
    html = (html
            .replace("__DATA__", data_json)
            .replace("__NTERMS__", str(len(rows)))
            .replace("__TOTAL__", f"{total_files:,}")
            .replace("__ZERO__", str(zero)))
    OUT.write_text(html)
    print(f"Wrote {OUT} ({len(rows)} terms, {zero} zero-usage)")


if __name__ == "__main__":
    main()
