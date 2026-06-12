"""
Dashboard generator for the Earthly registry monitor.

Reads monitor.db and writes a single self-contained dashboard.html with:
- Earthly brand styling
- Run metadata (last checked, total docs, project breakdown)
- Filterable, searchable, sortable document table
- Click-through links to Verra

The HTML is fully standalone - no external dependencies, no server needed.
Open by double-clicking in Finder.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Earthly · Registry Monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bright-green: #40E4AB;
    --text-green: #21A675;
    --keystone: #0D291C;
    --off-black: #201F1F;
    --light-grey: #F5F5F5;
    --mid-grey: #E5E5E5;
    --soft-grey: #8A8A8A;
    --white: #FFFFFF;
    --red: #E35E40;
    --blue: #3062C0;
    --turquoise: #76BEC6;
    --yellow: #D9CA80;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Inter', system-ui, sans-serif;
    background: var(--light-grey);
    color: var(--off-black);
    font-size: 14px;
    line-height: 1.5;
    padding: 32px 24px 80px;
  }

  .container {
    max-width: 1400px;
    margin: 0 auto;
  }

  /* HEADER */
  .header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    margin-bottom: 32px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--mid-grey);
    flex-wrap: wrap;
    gap: 16px;
  }
  .brand {
    display: flex;
    flex-direction: column;
  }
  .brand-eyebrow {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-green);
    margin-bottom: 4px;
  }
  .brand-title {
    font-family: 'Fraunces', Georgia, serif;
    font-size: 38px;
    font-weight: 500;
    letter-spacing: -0.02em;
    line-height: 1;
    color: var(--keystone);
  }
  .brand-subtitle {
    margin-top: 6px;
    font-size: 14px;
    color: var(--soft-grey);
  }
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--white);
    border: 1px solid var(--mid-grey);
    border-radius: 999px;
    padding: 8px 14px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--off-black);
  }
  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--bright-green);
    box-shadow: 0 0 0 3px rgba(64, 228, 171, 0.2);
  }

  /* METRICS */
  .metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin-bottom: 32px;
  }
  .metric {
    background: var(--white);
    border-radius: 12px;
    padding: 18px 20px;
    border: 1px solid var(--mid-grey);
  }
  .metric-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--soft-grey);
    margin-bottom: 6px;
  }
  .metric-value {
    font-family: 'Fraunces', serif;
    font-size: 32px;
    font-weight: 500;
    color: var(--keystone);
    line-height: 1;
  }
  .metric-trend {
    margin-top: 6px;
    font-size: 12px;
    color: var(--text-green);
  }

  /* PROJECT STRIP */
  .projects-strip {
    margin-bottom: 24px;
  }
  .projects-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--soft-grey);
    margin-bottom: 10px;
  }
  .project-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .project-chip {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--white);
    border: 1px solid var(--mid-grey);
    border-radius: 8px;
    padding: 8px 12px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .project-chip:hover {
    border-color: var(--text-green);
  }
  .project-chip.active {
    background: var(--keystone);
    color: var(--white);
    border-color: var(--keystone);
  }
  .project-chip-name {
    font-size: 13px;
    font-weight: 500;
  }
  .project-chip-count {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--soft-grey);
  }
  .project-chip.active .project-chip-count {
    color: var(--bright-green);
  }

  /* CONTROLS */
  .controls {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }
  .search {
    flex: 1;
    min-width: 240px;
    position: relative;
  }
  .search input {
    width: 100%;
    background: var(--white);
    border: 1px solid var(--mid-grey);
    border-radius: 8px;
    padding: 10px 14px 10px 38px;
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    color: var(--off-black);
    outline: none;
    transition: border 0.15s;
  }
  .search input:focus {
    border-color: var(--text-green);
  }
  .search::before {
    content: "⌕";
    position: absolute;
    left: 14px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 16px;
    color: var(--soft-grey);
  }
  .filter-select {
    background: var(--white);
    border: 1px solid var(--mid-grey);
    border-radius: 8px;
    padding: 10px 14px;
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    color: var(--off-black);
    outline: none;
    cursor: pointer;
    min-width: 180px;
  }
  .filter-select:focus { border-color: var(--text-green); }

  /* TABLE */
  .table-wrapper {
    background: var(--white);
    border-radius: 12px;
    border: 1px solid var(--mid-grey);
    overflow: hidden;
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th {
    text-align: left;
    background: var(--light-grey);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--soft-grey);
    padding: 12px 16px;
    border-bottom: 1px solid var(--mid-grey);
    font-weight: 500;
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  th:hover { color: var(--keystone); }
  th .sort-icon {
    display: inline-block;
    margin-left: 4px;
    color: var(--soft-grey);
    font-size: 10px;
  }
  td {
    padding: 14px 16px;
    border-bottom: 1px solid var(--light-grey);
    vertical-align: top;
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(64, 228, 171, 0.04); }

  .doc-title {
    font-weight: 500;
    color: var(--keystone);
    max-width: 480px;
  }
  .doc-title a {
    color: inherit;
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border 0.15s;
  }
  .doc-title a:hover {
    border-bottom-color: var(--text-green);
  }
  .doc-meta {
    font-size: 12px;
    color: var(--soft-grey);
    margin-top: 4px;
    font-family: 'JetBrains Mono', monospace;
  }
  .project-cell {
    font-size: 13px;
    color: var(--off-black);
    max-width: 200px;
  }
  .project-cell-country {
    font-size: 11px;
    color: var(--soft-grey);
    margin-top: 2px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .section-tag {
    display: inline-block;
    background: var(--light-grey);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    color: var(--keystone);
    white-space: nowrap;
  }
  .section-tag.vcs-issuance { background: rgba(64, 228, 171, 0.15); color: var(--text-green); }
  .section-tag.vcs-registration { background: rgba(118, 190, 198, 0.2); color: #4a8a92; }
  .section-tag.vcs-pipeline { background: rgba(217, 202, 128, 0.25); color: #7a6a30; }
  .section-tag.ccb-verification { background: rgba(48, 98, 192, 0.12); color: var(--blue); }
  .section-tag.ccb-validation { background: rgba(118, 190, 198, 0.15); color: #4a8a92; }
  .section-tag.sd-vista { background: rgba(227, 94, 64, 0.12); color: var(--red); }

  .date-cell {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: var(--off-black);
    white-space: nowrap;
  }

  /* EMPTY STATE */
  .empty {
    padding: 60px 20px;
    text-align: center;
    color: var(--soft-grey);
  }
  .empty-text {
    font-family: 'Fraunces', serif;
    font-size: 20px;
    color: var(--keystone);
    margin-bottom: 6px;
  }

  /* FOOTER */
  .footer {
    margin-top: 32px;
    padding-top: 20px;
    border-top: 1px solid var(--mid-grey);
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    color: var(--soft-grey);
    flex-wrap: wrap;
    gap: 12px;
  }
  .footer-brand {
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .result-count {
    font-family: 'JetBrains Mono', monospace;
  }

  @media (max-width: 768px) {
    body { padding: 20px 12px 40px; }
    .brand-title { font-size: 28px; }
    .doc-title { max-width: 200px; }
    th, td { padding: 10px 12px; font-size: 13px; }
  }
</style>
</head>
<body>
<div class="container">

  <header class="header">
    <div class="brand">
      <div class="brand-eyebrow">Earthly · Internal Tool</div>
      <h1 class="brand-title">Registry Monitor</h1>
      <div class="brand-subtitle">Tracking document activity across Earthly's Verra portfolio</div>
    </div>
    <div class="status-pill">
      <span class="status-dot"></span>
      <span>Last checked: __LAST_RUN__</span>
    </div>
  </header>

  <section class="metrics">
    <div class="metric">
      <div class="metric-label">Documents tracked</div>
      <div class="metric-value">__TOTAL_DOCS__</div>
    </div>
    <div class="metric">
      <div class="metric-label">Projects monitored</div>
      <div class="metric-value">__TOTAL_PROJECTS__</div>
    </div>
    <div class="metric">
      <div class="metric-label">Newest upload</div>
      <div class="metric-value" style="font-size: 18px; line-height: 1.3;">__NEWEST_DATE__</div>
      <div class="metric-trend">__NEWEST_PROJECT__</div>
    </div>
    <div class="metric">
      <div class="metric-label">Registry</div>
      <div class="metric-value" style="font-size: 22px;">Verra VCS</div>
      <div class="metric-trend">+ CCB · SD VISta</div>
    </div>
  </section>

  <section class="projects-strip">
    <div class="projects-title">Filter by project</div>
    <div class="project-chips" id="projectChips">
      <!-- Populated by JS -->
    </div>
  </section>

  <div class="controls">
    <div class="search">
      <input type="text" id="searchInput" placeholder="Search by document name, section, or project...">
    </div>
    <select class="filter-select" id="sectionFilter">
      <option value="">All sections</option>
    </select>
  </div>

  <div class="table-wrapper">
    <table id="docsTable">
      <thead>
        <tr>
          <th data-sort="date_updated">Date <span class="sort-icon">▼</span></th>
          <th data-sort="project_name">Project</th>
          <th data-sort="section">Section</th>
          <th data-sort="title">Document</th>
        </tr>
      </thead>
      <tbody id="docsBody">
        <!-- Populated by JS -->
      </tbody>
    </table>
  </div>

  <footer class="footer">
    <div class="footer-brand">Earthly — Registry Monitor v1</div>
    <div class="result-count" id="resultCount"></div>
  </footer>
</div>

<script>
  const DOCS = __DOCS_JSON__;
  const PROJECTS = __PROJECTS_JSON__;

  let activeProject = "all";
  let activeSection = "";
  let searchTerm = "";
  let sortKey = "date_updated";
  let sortDir = "desc";

  // Parse DD/MM/YYYY into a sortable Date
  function parseDate(s) {
    if (!s) return new Date(0);
    const parts = s.split('/');
    if (parts.length !== 3) return new Date(0);
    return new Date(parts[2], parts[1] - 1, parts[0]);
  }

  function sectionClass(section) {
    const s = section.toLowerCase();
    if (s.includes('issuance')) return 'vcs-issuance';
    if (s.includes('vcs registration')) return 'vcs-registration';
    if (s.includes('pipeline')) return 'vcs-pipeline';
    if (s.includes('ccb verification')) return 'ccb-verification';
    if (s.includes('ccb validation')) return 'ccb-validation';
    if (s.includes('sd vista')) return 'sd-vista';
    return '';
  }

  function renderProjectChips() {
    const chipsContainer = document.getElementById('projectChips');
    const allChip = `<div class="project-chip ${activeProject === 'all' ? 'active' : ''}" data-project="all">
      <span class="project-chip-name">All projects</span>
      <span class="project-chip-count">${DOCS.length}</span>
    </div>`;
    const projectChips = PROJECTS.map(p => `
      <div class="project-chip ${activeProject === p.name ? 'active' : ''}" data-project="${p.name}">
        <span class="project-chip-name">${p.name}</span>
        <span class="project-chip-count">${p.count}</span>
      </div>
    `).join('');
    chipsContainer.innerHTML = allChip + projectChips;

    chipsContainer.querySelectorAll('.project-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        activeProject = chip.dataset.project;
        renderProjectChips();
        renderTable();
      });
    });
  }

  function populateSectionFilter() {
    const sections = [...new Set(DOCS.map(d => d.section))].sort();
    const select = document.getElementById('sectionFilter');
    sections.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s;
      opt.textContent = s;
      select.appendChild(opt);
    });
    select.addEventListener('change', e => {
      activeSection = e.target.value;
      renderTable();
    });
  }

  function getFiltered() {
    return DOCS.filter(d => {
      if (activeProject !== 'all' && d.project_name !== activeProject) return false;
      if (activeSection && d.section !== activeSection) return false;
      if (searchTerm) {
        const t = searchTerm.toLowerCase();
        if (!d.title.toLowerCase().includes(t) &&
            !d.project_name.toLowerCase().includes(t) &&
            !d.section.toLowerCase().includes(t)) return false;
      }
      return true;
    });
  }

  function sortDocs(docs) {
    return [...docs].sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (sortKey === 'date_updated') {
        av = parseDate(av).getTime();
        bv = parseDate(bv).getTime();
      } else {
        av = (av || '').toLowerCase();
        bv = (bv || '').toLowerCase();
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }

  function renderTable() {
    const tbody = document.getElementById('docsBody');
    const filtered = sortDocs(getFiltered());

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4"><div class="empty">
        <div class="empty-text">No documents match these filters</div>
        <div>Try clearing the search or selecting a different project.</div>
      </div></td></tr>`;
    } else {
      tbody.innerHTML = filtered.map(d => `
        <tr>
          <td class="date-cell">${d.date_updated || '—'}</td>
          <td>
            <div class="project-cell">${d.project_name}</div>
            <div class="project-cell-country">${d.country || ''}</div>
          </td>
          <td><span class="section-tag ${sectionClass(d.section)}">${d.section}</span></td>
          <td>
            <div class="doc-title"><a href="${d.url}" target="_blank" rel="noopener">${d.title}</a></div>
            <div class="doc-meta">FileID ${d.file_id} · first seen ${d.first_seen_at.slice(0, 10)}</div>
          </td>
        </tr>
      `).join('');
    }

    document.getElementById('resultCount').textContent =
      `${filtered.length} of ${DOCS.length} document${DOCS.length === 1 ? '' : 's'}`;

    document.querySelectorAll('th[data-sort]').forEach(th => {
      const icon = th.querySelector('.sort-icon');
      if (th.dataset.sort === sortKey) {
        icon.textContent = sortDir === 'asc' ? '▲' : '▼';
        icon.style.color = 'var(--text-green)';
      } else {
        icon.textContent = '▼';
        icon.style.color = 'var(--soft-grey)';
      }
    });
  }

  document.getElementById('searchInput').addEventListener('input', e => {
    searchTerm = e.target.value;
    renderTable();
  });

  document.querySelectorAll('th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (key === sortKey) {
        sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        sortKey = key;
        sortDir = 'desc';
      }
      renderTable();
    });
  });

  renderProjectChips();
  populateSectionFilter();
  renderTable();
</script>
</body>
</html>
"""


def build_dashboard(db_path: Path, output_path: Path, projects_config: list[dict]) -> int:
    """
    Read monitor.db and write a self-contained dashboard.html.
    Returns the number of documents rendered.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT file_id, project_id, project_name, section, title,
               date_updated, url, first_seen_at, last_seen_at
        FROM documents
        """
    ).fetchall()
    conn.close()

    # Country lookup from config
    country_by_pid = {p["id"]: p["country"] for p in projects_config}

    docs = []
    for r in rows:
        docs.append({
            "file_id": r["file_id"],
            "project_id": r["project_id"],
            "project_name": r["project_name"],
            "section": r["section"],
            "title": r["title"],
            "date_updated": r["date_updated"],
            "url": r["url"],
            "first_seen_at": r["first_seen_at"],
            "country": country_by_pid.get(r["project_id"], ""),
        })

    # Project summary stats (count per project)
    project_counts = {}
    for d in docs:
        project_counts[d["project_name"]] = project_counts.get(d["project_name"], 0) + 1

    projects = [
        {"name": p["name"], "id": p["id"], "country": p["country"],
         "count": project_counts.get(p["name"], 0)}
        for p in projects_config
    ]

    # Find newest upload
    def parse_date(s):
        if not s:
            return datetime(1900, 1, 1)
        try:
            parts = s.split("/")
            return datetime(int(parts[2]), int(parts[1]), int(parts[0]))
        except (ValueError, IndexError):
            return datetime(1900, 1, 1)

    newest_date = "—"
    newest_project = ""
    if docs:
        newest = max(docs, key=lambda d: parse_date(d["date_updated"]))
        newest_date = newest["date_updated"] or "—"
        newest_project = newest["project_name"]

    last_run = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    html = (HTML_TEMPLATE
            .replace("__DOCS_JSON__", json.dumps(docs))
            .replace("__PROJECTS_JSON__", json.dumps(projects))
            .replace("__TOTAL_DOCS__", str(len(docs)))
            .replace("__TOTAL_PROJECTS__", str(len(projects)))
            .replace("__NEWEST_DATE__", newest_date)
            .replace("__NEWEST_PROJECT__", newest_project)
            .replace("__LAST_RUN__", last_run))

    output_path.write_text(html, encoding="utf-8")
    return len(docs)