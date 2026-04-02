"""
Dan's World Reports -- Standalone report browser.
Reads from admin DB (read-only mount) and serves categorized reports.
"""

import os
import sqlite3

from flask import Flask, g, render_template, jsonify, request, redirect

app = Flask(__name__)
app.secret_key = os.environ.get("AUTH_SECRET", "reports-default")

ADMIN_DB_PATH = os.environ.get("ADMIN_DB_PATH", "/data/admin.db")

REPORT_CATEGORIES = [
    "Integration Capability Briefs",
    "ITDR / Managed Identity",
    "Customer Security Reports",
    "Anonymized / Sample Reports",
    "Churn Analysis",
    "Threat Hunting & R&D",
    "Dynaframe Dashboards",
    "Internal / Operational",
    "Training & Service Delivery",
    "Uncategorized",
]


class PrefixMiddleware:
    """WSGI middleware for reverse proxy subpath deployment."""
    def __init__(self, wsgi_app):
        self.app = wsgi_app

    def __call__(self, environ, start_response):
        script_name = environ.get("HTTP_X_SCRIPT_NAME", "")
        if script_name:
            environ["SCRIPT_NAME"] = script_name
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith(script_name):
                environ["PATH_INFO"] = path_info[len(script_name):]
        return self.app(environ, start_response)


app.wsgi_app = PrefixMiddleware(app.wsgi_app)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(ADMIN_DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA query_only = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.route("/")
def reports_page():
    db = get_db()
    reports = db.execute(
        "SELECT * FROM dropzone WHERE is_report = 1 ORDER BY category, report_title, uploaded_at DESC"
    ).fetchall()

    grouped = {}
    for cat in REPORT_CATEGORIES:
        grouped[cat] = []
    for r in reports:
        cat = r["category"] or "Uncategorized"
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(r)
    grouped = {k: v for k, v in grouped.items() if v}

    user = request.headers.get("X-Auth-User", "anonymous")
    return render_template("reports.html", grouped=grouped, user=user,
                           categories=REPORT_CATEGORIES)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "reports"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010, debug=False)
