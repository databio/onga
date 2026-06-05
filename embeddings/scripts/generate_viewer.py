#!/usr/bin/env python3
"""Generate HTML viewer with embedded JSON data."""
import json
from pathlib import Path

REPORTS_DIR = Path(__file__).parent.parent / "outputs" / "reports"
OUTPUT = Path(__file__).parent.parent / "outputs" / "viewer.html"

def main():
    mapping_raw = json.loads((REPORTS_DIR / "mapping_report.json").read_text())
    internal_raw = json.loads((REPORTS_DIR / "internal_similarity.json").read_text())
    gaps_raw = json.loads((REPORTS_DIR / "gap_analysis.json").read_text())
    
    mapping = mapping_raw.get("terms", mapping_raw)
    internal = internal_raw.get("pairs", internal_raw)
    gaps = gaps_raw.get("terms", gaps_raw)
    
    well_mapped = len([t for t in mapping if t.get("max_similarity", 0) >= 0.7])
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ONGA Embedding Comparison</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen">
    <div class="max-w-7xl mx-auto px-4 py-8">
        <header class="mb-6">
            <h1 class="text-3xl font-bold text-gray-900">ONGA Embedding Comparison</h1>
            <p class="text-gray-600">Comparing {len(mapping)} ONGA terms against EDAM, OBI, GO</p>
        </header>

        <div class="border-b mb-6">
            <nav class="flex gap-6">
                <button onclick="showTab('mapping')" id="tab-mapping" class="py-2 border-b-2 border-blue-500 text-blue-600 font-medium">
                    Mappings ({len(mapping)})
                </button>
                <button onclick="showTab('internal')" id="tab-internal" class="py-2 text-gray-500 hover:text-gray-700">
                    Similar Pairs ({len(internal)})
                </button>
                <button onclick="showTab('gaps')" id="tab-gaps" class="py-2 text-gray-500 hover:text-gray-700">
                    Gaps ({len(gaps)})
                </button>
            </nav>
        </div>

        <div class="grid grid-cols-4 gap-4 mb-6">
            <div class="bg-white rounded-lg p-4 shadow text-center">
                <div class="text-2xl font-bold">{len(mapping)}</div>
                <div class="text-sm text-gray-500">Total</div>
            </div>
            <div class="bg-white rounded-lg p-4 shadow text-center">
                <div class="text-2xl font-bold text-green-600">{well_mapped}</div>
                <div class="text-sm text-gray-500">Strong (≥0.7)</div>
            </div>
            <div class="bg-white rounded-lg p-4 shadow text-center">
                <div class="text-2xl font-bold text-yellow-600">{len(internal)}</div>
                <div class="text-sm text-gray-500">Similar Pairs</div>
            </div>
            <div class="bg-white rounded-lg p-4 shadow text-center">
                <div class="text-2xl font-bold text-red-600">{len(gaps)}</div>
                <div class="text-sm text-gray-500">Gaps</div>
            </div>
        </div>

        <div class="bg-white rounded-lg shadow p-4 mb-6 flex gap-4 items-center">
            <input type="text" id="search" placeholder="Search..." class="px-3 py-1 border rounded" oninput="filter()">
            <select id="cat" class="px-3 py-1 border rounded" onchange="filter()">
                <option value="">All Categories</option>
                <option value="DataType">DataType</option>
                <option value="FeatureType">FeatureType</option>
            </select>
            <label class="text-sm text-gray-600">Min sim: <span id="simVal">0.00</span></label>
            <input type="range" id="sim" min="0" max="100" value="0" oninput="document.getElementById('simVal').textContent=(this.value/100).toFixed(2);filter()">
        </div>

        <div id="panel-mapping"></div>
        <div id="panel-internal" class="hidden"></div>
        <div id="panel-gaps" class="hidden"></div>
    </div>

    <script>
        const M = {json.dumps(mapping)};
        const I = {json.dumps(internal)};
        const G = {json.dumps(gaps)};

        function showTab(t) {{
            ['mapping','internal','gaps'].forEach(x => {{
                document.getElementById('panel-'+x).classList.toggle('hidden', x!==t);
                document.getElementById('tab-'+x).classList.toggle('border-b-2', x===t);
                document.getElementById('tab-'+x).classList.toggle('border-blue-500', x===t);
                document.getElementById('tab-'+x).classList.toggle('text-blue-600', x===t);
                document.getElementById('tab-'+x).classList.toggle('text-gray-500', x!==t);
            }});
        }}

        function filter() {{
            const q = document.getElementById('search').value.toLowerCase();
            const c = document.getElementById('cat').value;
            const s = document.getElementById('sim').value/100;
            document.querySelectorAll('.card').forEach(el => {{
                const show = el.dataset.name.includes(q) && (!c || el.dataset.cat===c) && parseFloat(el.dataset.sim)>=s;
                el.classList.toggle('hidden', !show);
            }});
        }}

        function renderM() {{
            const sorted = [...M].sort((a,b) => (b.max_similarity||0)-(a.max_similarity||0));
            document.getElementById('panel-mapping').innerHTML = '<div class="space-y-2">' + sorted.map(t => {{
                const sim = t.max_similarity || 0;
                const col = sim >= 0.7 ? 'green' : sim >= 0.5 ? 'yellow' : 'red';
                const matches = (t.suggested_mappings || []).slice(0,3);
                return `<div class="card bg-white rounded shadow p-3" data-name="${{t.onga_term.toLowerCase()}}" data-cat="${{t.onga_category}}" data-sim="${{sim}}">
                    <div class="flex justify-between mb-1">
                        <div><span class="font-medium">${{t.onga_term}}</span>
                        <span class="text-xs ml-1 px-1 rounded ${{t.onga_category==='DataType'?'bg-blue-100 text-blue-700':'bg-green-100 text-green-700'}}">${{t.onga_category}}</span></div>
                        <span class="font-bold text-${{col}}-600">${{sim.toFixed(2)}}</span>
                    </div>
                    ${{matches.length ? '<div class="text-sm text-gray-600 space-y-0.5">'+matches.map(m=>`<div class="flex gap-2"><span class="w-10 text-gray-400 text-xs">${{m.ontology}}</span><span class="w-8">${{m.similarity.toFixed(2)}}</span><span class="truncate">${{m.term_name}}</span></div>`).join('')+'</div>' : ''}}
                </div>`;
            }}).join('') + '</div>';
        }}

        function renderI() {{
            const sorted = [...I].sort((a,b) => b.similarity-a.similarity);
            document.getElementById('panel-internal').innerHTML = '<div class="space-y-2">' + sorted.map(p => {{
                const col = p.similarity >= 0.9 ? 'red' : 'yellow';
                return `<div class="card bg-white rounded shadow p-3 flex items-center" data-name="${{p.term1.toLowerCase()}} ${{p.term2.toLowerCase()}}" data-cat="" data-sim="${{p.similarity}}">
                    <div class="flex-1"><span class="font-medium">${{p.term1}}</span> <span class="text-xs px-1 rounded ${{p.category1==='DataType'?'bg-blue-100':'bg-green-100'}}">${{p.category1}}</span></div>
                    <div class="text-lg font-bold text-${{col}}-600 px-4">${{p.similarity.toFixed(2)}}</div>
                    <div class="flex-1 text-right"><span class="font-medium">${{p.term2}}</span> <span class="text-xs px-1 rounded ${{p.category2==='DataType'?'bg-blue-100':'bg-green-100'}}">${{p.category2}}</span></div>
                </div>`;
            }}).join('') + '</div>';
        }}

        function renderG() {{
            const byCat = {{}};
            G.forEach(t => {{ byCat[t.onga_category] = byCat[t.onga_category] || []; byCat[t.onga_category].push(t); }});
            document.getElementById('panel-gaps').innerHTML = Object.entries(byCat).map(([cat, terms]) => `
                <div class="mb-4"><h3 class="font-semibold mb-2">${{cat}} (${{terms.length}})</h3>
                <div class="grid grid-cols-3 gap-2">${{terms.map(t => `<div class="card bg-white rounded shadow p-2 text-sm" data-name="${{t.onga_term.toLowerCase()}}" data-cat="${{t.onga_category}}" data-sim="0">
                    <div class="font-medium">${{t.onga_term}}</div><div class="text-xs text-gray-400">best: ${{(t.max_similarity||0).toFixed(2)}}</div>
                </div>`).join('')}}</div></div>
            `).join('');
        }}

        renderM(); renderI(); renderG();
    </script>
</body>
</html>'''
    
    OUTPUT.write_text(html)
    print(f"Generated: {OUTPUT}")

if __name__ == "__main__":
    main()
