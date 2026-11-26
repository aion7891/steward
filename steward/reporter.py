"""Periodic Markdown and HTML report generator using Jinja2 templates."""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment


class ReportGenerator:
    """Aggregates storage, activity, software, and recommendation data into Markdown/HTML."""

    MARKDOWN_TEMPLATE = """# {{ title }} ({{ period }})

- **Generated:** `{{ generated_at }}`
- **Tracked Files:** {{ total_files }} ({{ total_size_mb }} MB)
- **Potential Reclaimable Space:** {{ total_reclaimable_mb }} MB
- **Installed Software:** {{ software.total }} (recent: {{ software.recent }}, rarely used: {{ software.rarely_used }})
- **OKF Knowledge Graph:** {{ okf_graph.nodes }} nodes, {{ okf_graph.edges }} edges

## File Categories
| Category | Files | Size (MB) |
| :--- | ---: | ---: |
{% for row in categories -%}
| `{{ row.category }}` | {{ row.count }} | {{ row.size_mb }} |
{% endfor %}

## Top Folders by Disk Usage
{% for folder in top_folders -%}
- `{{ folder.folder }}` — {{ folder.count }} file(s), {{ folder.size_mb }} MB
{% endfor %}

## Activity Over Time
{% if activity_days -%}
{% for day in activity_days -%}
- `{{ day.date }}`: {{ day.count }} file/download event(s)
{% endfor %}
{% else -%}
- No dated activity recorded yet.
{% endif %}

## Learned Work Patterns
{% if patterns -%}
{% for p in patterns -%}
- **{{ p.name }}**: {{ p.description }}
{% endfor %}
{% else -%}
- No recurring patterns detected yet.
{% endif %}

## Cleanup & Organization Suggestions
{% if suggestions -%}
{% for s in suggestions -%}
- **[{{ s.priority | upper }}] {{ s.title }}** ({{ s.reclaimable_mb }} MB) — {{ s.reason }}
{% endfor %}
{% else -%}
- Everything looks clean! No immediate cleanup actions needed.
{% endif %}
"""

    HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{{ title }} ({{ period }})</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 920px; margin: 2rem auto; padding: 0 1.2rem; color: #1f2937; line-height: 1.5; }
  h1, h2 { color: #111827; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin: 1.2rem 0; }
  .card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 1rem; }
  .card strong { display: block; font-size: 1.4rem; color: #0f172a; }
  table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
  th, td { text-align: left; padding: 0.55rem 0.75rem; border-bottom: 1px solid #e5e7eb; }
  th { background: #f1f5f9; }
  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
  .high { background: #fee2e2; color: #991b1b; }
  .medium { background: #fef3c7; color: #92400e; }
  .low { background: #e0f2fe; color: #075985; }
</style>
</head>
<body>
  <h1>{{ title }} ({{ period }})</h1>
  <p>Generated: <code>{{ generated_at }}</code></p>
  <div class="cards">
    <div class="card"><span>Tracked Files</span><strong>{{ total_files }}</strong></div>
    <div class="card"><span>Disk Usage</span><strong>{{ total_size_mb }} MB</strong></div>
    <div class="card"><span>Reclaimable</span><strong>{{ total_reclaimable_mb }} MB</strong></div>
    <div class="card"><span>OKF Graph</span><strong>{{ okf_graph.nodes }} nodes</strong></div>
  </div>
  <h2>File Categories</h2>
  <table><thead><tr><th>Category</th><th>Files</th><th>Size (MB)</th></tr></thead><tbody>
  {% for row in categories %}<tr><td>{{ row.category }}</td><td>{{ row.count }}</td><td>{{ row.size_mb }}</td></tr>{% endfor %}
  </tbody></table>
  <h2>Cleanup &amp; Organization Suggestions</h2>
  <ul>{% for s in suggestions %}<li><span class="badge {{ s.priority }}">{{ s.priority }}</span> <strong>{{ s.title }}</strong> ({{ s.reclaimable_mb }} MB) &mdash; {{ s.reason }}</li>{% else %}<li>No immediate cleanup actions needed.</li>{% endfor %}</ul>
  <h2>Learned Work Patterns</h2>
  <ul>{% for p in patterns %}<li><strong>{{ p.name }}</strong>: {{ p.description }}</li>{% else %}<li>No recurring patterns detected yet.</li>{% endfor %}</ul>
  <h2>Software Usage</h2>
  <p>Total: {{ software.total }} | Recent: {{ software.recent }} | Rarely Used: {{ software.rarely_used }}</p>
</body>
</html>
"""

    def __init__(self, config, db, scanner, graph, recommender, okf_bundle=None, logger=None):
        """Initialize ReportGenerator with data sources and autoescaping Jinja2 env."""
        self.config = config
        self.db = db
        self.scanner = scanner
        self.graph = graph
        self.recommender = recommender
        self.okf_bundle = okf_bundle
        self.logger = logger
        self.md_env = Environment(autoescape=False)
        self.html_env = Environment(autoescape=True)

    def collect_report_data(self, period="weekly", persist_patterns=True):
        """Aggregate disk usage, categories, timeline, software, and recommendations."""
        files = self.db.list_files()
        cat_counts, cat_bytes, folder_stats, day_counts = Counter(), Counter(), {}, Counter()
        total_bytes = 0

        for item in files:
            size = int(item.get("size_bytes", 0))
            total_bytes += size
            cat = item.get("category") or "other"
            cat_counts[cat] += 1
            cat_bytes[cat] += size
            folder = item.get("folder") or "unknown"
            entry = folder_stats.setdefault(folder, {"folder": folder, "count": 0, "bytes": 0})
            entry["count"] += 1
            entry["bytes"] += size
            mod = str(item.get("modified_at") or "")[:10]
            if len(mod) == 10:
                day_counts[mod] += 1

        for ev in self.db.list_activity_events(limit=200):
            day = str(ev.get("timestamp") or "")[:10]
            if len(day) == 10:
                day_counts[day] += 1

        categories = [
            {"category": c, "count": cat_counts[c], "size_mb": round(cat_bytes[c] / (1024 * 1024), 2)}
            for c in sorted(cat_counts.keys())
        ]
        top_folders = [
            {"folder": v["folder"], "count": v["count"], "size_mb": round(v["bytes"] / (1024 * 1024), 2)}
            for v in sorted(folder_stats.values(), key=lambda x: -x["bytes"])[:8]
        ]
        activity_days = [{"date": d, "count": day_counts[d]} for d in sorted(day_counts.keys(), reverse=True)[:14]]

        apps = self.db.list_software()
        recent_apps = sum(1 for a in apps if a.get("status") == "recent")
        rare_apps = sum(1 for a in apps if a.get("status") == "rarely_used")
        rec = self.recommender.generate_recommendations(persist_patterns=persist_patterns)

        return {
            "period": period,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_files": len(files),
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            "total_reclaimable_mb": rec["total_reclaimable_mb"],
            "categories": categories,
            "top_folders": top_folders,
            "activity_days": activity_days,
            "software": {"total": len(apps), "recent": recent_apps, "rarely_used": rare_apps},
            "patterns": rec["patterns"],
            "suggestions": rec["suggestions"],
            "okf_graph": self.graph.stats(),
        }

    def generate_report(self, period="weekly", output_format="markdown", title="Steward Activity Report", save_okf=True):
        """Render Markdown, HTML, or both reports to reports/, log in SQLite, and save OKF concept."""
        fmt = str(output_format).strip().lower()
        if fmt not in ("markdown", "html", "both"):
            raise ValueError("output_format must be 'markdown', 'html', or 'both'.")

        data = self.collect_report_data(period=period)
        data["title"] = title
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        reports_dir = self.config.get_path("reports_dir")
        reports_dir.mkdir(parents=True, exist_ok=True)

        written = {}
        if fmt in ("markdown", "both"):
            md_path = reports_dir / f"steward_{period}_{stamp}.md"
            md_path.write_text(self.md_env.from_string(self.MARKDOWN_TEMPLATE).render(**data), encoding="utf-8")
            self.db.record_report(period, str(md_path))
            written["markdown"] = str(md_path)
        if fmt in ("html", "both"):
            html_path = reports_dir / f"steward_{period}_{stamp}.html"
            html_path.write_text(self.html_env.from_string(self.HTML_TEMPLATE).render(**data), encoding="utf-8")
            self.db.record_report(period, str(html_path))
            written["html"] = str(html_path)

        primary_path = written.get("markdown") or written.get("html")
        okf_rel = self._save_okf_concept(period, stamp, primary_path, data) if save_okf and self.okf_bundle else None
        return {
            "status": "ok",
            "message": f"Generated {fmt} {period} report ({len(data['suggestions'])} suggestion(s)).",
            "report_path": primary_path,
            "files": written,
            "okf_concept": okf_rel,
            "stats": data,
        }

    def _save_okf_concept(self, period, stamp, report_path, data):
        """Store a concise summary of the generated report in knowledge/reports/."""
        rel_path = f"reports/steward-{self.okf_bundle.slugify(period)}-{stamp}.md"
        saved = self.okf_bundle.write_concept(
            rel_path,
            {
                "type": "report",
                "title": f"{data['title']} ({period})",
                "description": f"{data['total_files']} files ({data['total_size_mb']} MB), {len(data['suggestions'])} suggestion(s).",
                "tags": ["report", period],
                "sources": [report_path] if report_path else [],
                "x-steward-report-path": report_path,
                "x-steward-reclaimable-mb": data["total_reclaimable_mb"],
            },
            f"# {data['title']} ({period})\n\nReport saved at `{report_path}`.\n\n- Suggestions: {len(data['suggestions'])}\n- Reclaimable: {data['total_reclaimable_mb']} MB",
        )
        self.okf_bundle.refresh_index()
        self.graph.update_node(saved)
        return saved
