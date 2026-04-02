"""
Dan's World of AI Magic -- Admin & Auth Server
Flask app serving: landing page, authentication, admin UI, HTML drop zone.
"""

import os
import pty
import select
import signal
import struct
import fcntl
import termios
import logging
import json
import uuid
import sqlite3
import datetime
import functools

import yaml
import jwt
import bcrypt
from flask import (
    Flask, request, redirect, url_for, render_template, jsonify,
    make_response, g, flash, send_from_directory
)
from flask_sock import Sock
from werkzeug.utils import secure_filename

app = Flask(__name__)
_secret = os.environ.get("AUTH_SECRET")
if not _secret:
    raise RuntimeError("AUTH_SECRET environment variable is required")
app.secret_key = _secret

sock = Sock(app)

# ---------------------------------------------------------------------------
# Terminal audit logger
# ---------------------------------------------------------------------------
terminal_audit = logging.getLogger("terminal_audit")
terminal_audit.setLevel(logging.INFO)
_audit_handler = logging.FileHandler("/app/data/terminal_audit.log")
_audit_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
terminal_audit.addHandler(_audit_handler)

DB_PATH = os.environ.get("DB_PATH", "/app/data/admin.db")
DROPZONE_PATH = os.environ.get("DROPZONE_PATH", "/app/dropzone")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
COOKIE_NAME = "dw_session"

# ---------------------------------------------------------------------------
# App registry -- loaded from registry.yaml (single source of truth)
# ---------------------------------------------------------------------------
REGISTRY_PATH = os.environ.get("REGISTRY_PATH", "/app/registry.yaml")


def load_registry():
    """Load apps + demos from registry.yaml into a flat list for the landing page."""
    with open(REGISTRY_PATH) as f:
        reg = yaml.safe_load(f)

    entries = []
    for app_def in reg.get("apps", []):
        entries.append({
            "id": app_def["id"],
            "name": app_def["name"],
            "description": app_def.get("description", ""),
            "url": app_def["url"],
            "icon": app_def.get("icon", "app"),
            "groups": app_def.get("groups", ["admin"]),
            "author": app_def.get("author", ""),
            "container": app_def.get("container"),
            "port": app_def.get("port"),
            "health": app_def.get("health"),
        })
    for demo in reg.get("demos", []):
        entries.append({
            "id": demo["id"],
            "name": demo["name"],
            "description": demo.get("description", ""),
            "url": demo["url"],
            "icon": demo.get("icon", "demo"),
            "groups": demo.get("groups", ["demos", "admin"]),
            "author": demo.get("author", ""),
        })
    return entries


APP_REGISTRY = load_registry()

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            last_login TEXT
        );

        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS user_groups (
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, group_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS app_overrides (
            app_id TEXT PRIMARY KEY,
            is_hidden INTEGER DEFAULT 0,
            is_deleted INTEGER DEFAULT 0,
            groups_override TEXT DEFAULT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS dropzone (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            is_public INTEGER DEFAULT 0,
            uploaded_by TEXT NOT NULL,
            uploaded_at TEXT DEFAULT (datetime('now')),
            description TEXT,
            is_report INTEGER DEFAULT 0,
            report_title TEXT,
            category TEXT DEFAULT 'Uncategorized'
        );
    """)

    # Migrate: add groups_override to app_overrides
    try:
        db.execute("ALTER TABLE app_overrides ADD COLUMN groups_override TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    # Migrate: add columns to existing dropzone tables
    for col, defn in [("is_report", "INTEGER DEFAULT 0"), ("report_title", "TEXT"),
                       ("category", "TEXT DEFAULT 'Uncategorized'")]:
        try:
            db.execute(f"ALTER TABLE dropzone ADD COLUMN {col} {defn}")
        except sqlite3.OperationalError:
            pass  # column already exists

    # Seed default groups
    for grp in ["admin", "demos", "analytics", "engineering"]:
        db.execute(
            "INSERT OR IGNORE INTO groups (name, description) VALUES (?, ?)",
            (grp, f"Access to {grp} apps"),
        )

    # Seed admin user if it doesn't exist
    admin_exists = db.execute(
        "SELECT 1 FROM users WHERE username = 'admin'"
    ).fetchone()
    if not admin_exists:
        admin_pw = os.environ.get("ADMIN_PASSWORD", "changeme")
        pw_hash = bcrypt.hashpw(admin_pw.encode(), bcrypt.gensalt()).decode()
        db.execute(
            "INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)",
            ("admin", pw_hash, "Administrator"),
        )
        admin_id = db.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()["id"]
        admin_group = db.execute("SELECT id FROM groups WHERE name = 'admin'").fetchone()["id"]
        db.execute(
            "INSERT OR IGNORE INTO user_groups (user_id, group_id) VALUES (?, ?)",
            (admin_id, admin_group),
        )

    db.commit()


with app.app_context():
    init_db()

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_token(username, groups):
    payload = {
        "sub": username,
        "groups": groups,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, app.secret_key, algorithm=JWT_ALGORITHM)


def decode_token(token):
    try:
        return jwt.decode(token, app.secret_key, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def get_current_user():
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return decode_token(token)


def require_auth(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("auth_login", next=request.url))
        g.user = user
        return f(*args, **kwargs)
    return wrapper


def require_admin(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("auth_login", next=request.url))
        if "admin" not in user.get("groups", []):
            return "Forbidden", 403
        g.user = user
        return f(*args, **kwargs)
    return wrapper

# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/auth/login", methods=["GET", "POST"])
def auth_login():
    if request.method == "GET":
        return render_template("login.html", next=request.args.get("next", "/"))

    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    next_url = request.form.get("next", "/")
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"

    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
    ).fetchone()

    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        flash("Invalid username or password.", "error")
        return render_template("login.html", next=next_url), 401

    # Get user groups
    groups = [
        row["name"] for row in db.execute(
            """SELECT g.name FROM groups g
               JOIN user_groups ug ON g.id = ug.group_id
               WHERE ug.user_id = ?""",
            (user["id"],),
        ).fetchall()
    ]

    # Update last login
    db.execute(
        "UPDATE users SET last_login = datetime('now') WHERE id = ?", (user["id"],)
    )
    db.commit()

    token = create_token(username, groups)
    resp = make_response(redirect(next_url))
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True,
        samesite="Lax",
        max_age=JWT_EXPIRY_HOURS * 3600,
    )
    return resp


@app.route("/auth/logout")
def auth_logout():
    resp = make_response(redirect(url_for("auth_login")))
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.route("/auth/change-password", methods=["GET", "POST"])
@require_auth
def auth_change_password():
    if request.method == "GET":
        return render_template("change_password.html", user=g.user)

    current_pw = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    confirm_pw = request.form.get("confirm_password", "")

    if not current_pw or not new_pw:
        flash("All fields are required.", "error")
        return render_template("change_password.html", user=g.user), 400

    if new_pw != confirm_pw:
        flash("New passwords do not match.", "error")
        return render_template("change_password.html", user=g.user), 400

    if len(new_pw) < 6:
        flash("Password must be at least 6 characters.", "error")
        return render_template("change_password.html", user=g.user), 400

    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1",
        (g.user["sub"],),
    ).fetchone()

    if not user or not bcrypt.checkpw(current_pw.encode(), user["password_hash"].encode()):
        flash("Current password is incorrect.", "error")
        return render_template("change_password.html", user=g.user), 401

    pw_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user["id"]))
    db.commit()

    flash("Password changed.", "success")
    return redirect(url_for("landing"))


@app.route("/auth/validate")
def auth_validate():
    """nginx auth_request target. Returns 200 + user headers, or 401."""
    user = get_current_user()
    if not user:
        return "", 401

    resp = make_response("", 200)
    resp.headers["X-Auth-User"] = user["sub"]
    resp.headers["X-Auth-Groups"] = ",".join(user.get("groups", []))
    return resp


@app.route("/auth/validate-dropzone")
def auth_validate_dropzone():
    """Validates drop zone access. Public items pass without auth."""
    original_uri = request.headers.get("X-Original-URI", "")
    # Extract UUID from /d/<uuid>.html
    file_id = original_uri.replace("/d/", "").replace(".html", "").strip("/")

    db = get_db()
    item = db.execute("SELECT * FROM dropzone WHERE id = ?", (file_id,)).fetchone()

    if not item:
        return "", 404

    if item["is_public"]:
        return "", 200

    # Private item -- require auth
    user = get_current_user()
    if not user:
        return "", 401
    return "", 200

# ---------------------------------------------------------------------------
# App visibility helpers
# ---------------------------------------------------------------------------

def get_app_overrides():
    db = get_db()
    rows = db.execute("SELECT app_id, is_hidden, is_deleted, groups_override FROM app_overrides").fetchall()
    return {row["app_id"]: dict(row) for row in rows}


def get_visible_apps(user_groups, include_hidden=False):
    overrides = get_app_overrides()
    visible = []
    for app_def in APP_REGISTRY:
        app_id = app_def["id"]
        ovr = overrides.get(app_id, {})
        if ovr.get("is_deleted"):
            continue
        if ovr.get("is_hidden") and not include_hidden:
            continue
        entry = dict(app_def)
        # Apply group override if set
        if ovr.get("groups_override"):
            entry["groups"] = [g.strip() for g in ovr["groups_override"].split(",") if g.strip()]
        required = set(entry["groups"])
        if user_groups & required:
            entry["is_hidden"] = ovr.get("is_hidden", 0)
            visible.append(entry)
    return visible


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

@app.route("/")
@require_auth
def landing():
    user = g.user
    user_groups = set(user.get("groups", []))

    visible_apps = get_visible_apps(user_groups)

    return render_template(
        "landing.html",
        apps=visible_apps,
        user=user,
    )

# ---------------------------------------------------------------------------
# Admin UI
# ---------------------------------------------------------------------------

@app.route("/admin/")
@require_admin
def admin_dashboard():
    db = get_db()
    users = db.execute(
        """SELECT u.*, GROUP_CONCAT(g.name) as group_names
           FROM users u
           LEFT JOIN user_groups ug ON u.id = ug.user_id
           LEFT JOIN groups g ON ug.group_id = g.id
           GROUP BY u.id
           ORDER BY u.username"""
    ).fetchall()

    groups = db.execute("SELECT * FROM groups ORDER BY name").fetchall()
    drops = db.execute("SELECT * FROM dropzone ORDER BY uploaded_at DESC").fetchall()

    all_apps = get_visible_apps({"admin"}, include_hidden=True)

    return render_template(
        "admin.html",
        users=users,
        groups=groups,
        drops=drops,
        user=g.user,
        apps=all_apps,
    )


@app.route("/admin/users/add", methods=["POST"])
@require_admin
def admin_add_user():
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    display_name = request.form.get("display_name", "").strip() or username
    group_ids = request.form.getlist("groups")

    if not username or not password:
        flash("Username and password are required.", "error")
        return redirect(url_for("admin_dashboard"))

    db = get_db()
    try:
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        db.execute(
            "INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)",
            (username, pw_hash, display_name),
        )
        user_id = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"]

        for gid in group_ids:
            db.execute(
                "INSERT INTO user_groups (user_id, group_id) VALUES (?, ?)",
                (user_id, int(gid)),
            )
        db.commit()
        flash(f"User '{username}' created.", "success")
    except sqlite3.IntegrityError:
        flash(f"Username '{username}' already exists.", "error")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users/<int:user_id>/edit", methods=["POST"])
@require_admin
def admin_edit_user(user_id):
    db = get_db()
    display_name = request.form.get("display_name", "").strip()
    is_active = request.form.get("is_active") == "on"
    new_password = request.form.get("password", "").strip()
    group_ids = request.form.getlist("groups")

    if display_name:
        db.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, user_id))
    db.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))

    if new_password:
        pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))

    # Replace group memberships
    db.execute("DELETE FROM user_groups WHERE user_id = ?", (user_id,))
    for gid in group_ids:
        db.execute(
            "INSERT INTO user_groups (user_id, group_id) VALUES (?, ?)",
            (user_id, int(gid)),
        )
    db.commit()
    flash("User updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@require_admin
def admin_delete_user(user_id):
    db = get_db()
    user = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    if user and user["username"] == "admin":
        flash("Cannot delete the admin user.", "error")
        return redirect(url_for("admin_dashboard"))

    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("User deleted.", "success")
    return redirect(url_for("admin_dashboard"))

# ---------------------------------------------------------------------------
# App Management
# ---------------------------------------------------------------------------

@app.route("/admin/apps/<app_id>/toggle-hidden", methods=["POST"])
@require_admin
def admin_toggle_app_hidden(app_id):
    db = get_db()
    existing = db.execute("SELECT is_hidden FROM app_overrides WHERE app_id = ?", (app_id,)).fetchone()
    if existing:
        new_val = 0 if existing["is_hidden"] else 1
        db.execute(
            "UPDATE app_overrides SET is_hidden = ?, updated_at = datetime('now') WHERE app_id = ?",
            (new_val, app_id),
        )
    else:
        db.execute(
            "INSERT INTO app_overrides (app_id, is_hidden) VALUES (?, 1)", (app_id,)
        )
    db.commit()
    flash(f"App '{app_id}' visibility toggled.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/apps/<app_id>/edit", methods=["POST"])
@require_admin
def admin_edit_app(app_id):
    groups = request.form.getlist("groups")
    if not groups:
        flash("At least one group is required.", "error")
        return redirect(url_for("admin_dashboard"))
    groups_str = ",".join(groups)
    db = get_db()
    db.execute(
        "INSERT INTO app_overrides (app_id, groups_override) VALUES (?, ?) "
        "ON CONFLICT(app_id) DO UPDATE SET groups_override = ?, updated_at = datetime('now')",
        (app_id, groups_str, groups_str),
    )
    db.commit()
    flash(f"App '{app_id}' groups updated to: {', '.join(groups)}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/apps/<app_id>/delete", methods=["POST"])
@require_admin
def admin_delete_app(app_id):
    db = get_db()
    db.execute(
        "INSERT INTO app_overrides (app_id, is_deleted) VALUES (?, 1) "
        "ON CONFLICT(app_id) DO UPDATE SET is_deleted = 1, updated_at = datetime('now')",
        (app_id,),
    )
    db.commit()
    flash(f"App '{app_id}' deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/apps/<app_id>/restore", methods=["POST"])
@require_admin
def admin_restore_app(app_id):
    db = get_db()
    db.execute("DELETE FROM app_overrides WHERE app_id = ?", (app_id,))
    db.commit()
    flash(f"App '{app_id}' restored.", "success")
    return redirect(url_for("admin_dashboard"))


# ---------------------------------------------------------------------------
# Drop Zone
# ---------------------------------------------------------------------------

@app.route("/admin/dropzone", methods=["GET"])
@require_admin
def admin_dropzone():
    db = get_db()
    drops = db.execute("SELECT * FROM dropzone ORDER BY uploaded_at DESC").fetchall()
    return render_template("dropzone.html", drops=drops, user=g.user,
                           categories=REPORT_CATEGORIES)


@app.route("/admin/dropzone/upload", methods=["POST"])
@require_admin
def admin_dropzone_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for("admin_dropzone"))

    if not file.filename.endswith(".html"):
        flash("Only .html files are allowed.", "error")
        return redirect(url_for("admin_dropzone"))

    file_id = str(uuid.uuid4())
    filename = f"{file_id}.html"
    is_public = request.form.get("is_public") == "on"
    description = request.form.get("description", "").strip()
    report_title = request.form.get("report_title", "").strip()
    category = request.form.get("category", "Uncategorized").strip()
    is_report = 1 if request.form.get("is_report") == "on" else 0

    os.makedirs(DROPZONE_PATH, exist_ok=True)
    file.save(os.path.join(DROPZONE_PATH, filename))

    db = get_db()
    db.execute(
        """INSERT INTO dropzone (id, filename, original_name, is_public, uploaded_by, description,
                                 report_title, category, is_report)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (file_id, filename, secure_filename(file.filename), 1 if is_public else 0,
         g.user["sub"], description, report_title or None, category, is_report),
    )
    db.commit()

    host = request.host
    scheme = request.scheme
    link = f"{scheme}://{host}/d/{file_id}.html"
    flash(f"Uploaded. Link: {link}", "success")
    return redirect(url_for("admin_dropzone"))


@app.route("/admin/dropzone/<drop_id>/delete", methods=["POST"])
@require_admin
def admin_dropzone_delete(drop_id):
    db = get_db()
    item = db.execute("SELECT * FROM dropzone WHERE id = ?", (drop_id,)).fetchone()
    if item:
        filepath = os.path.join(DROPZONE_PATH, item["filename"])
        if os.path.exists(filepath):
            os.remove(filepath)
        db.execute("DELETE FROM dropzone WHERE id = ?", (drop_id,))
        db.commit()
        flash("Drop zone item deleted.", "success")
    return redirect(url_for("admin_dropzone"))


@app.route("/admin/dropzone/<drop_id>/toggle", methods=["POST"])
@require_admin
def admin_dropzone_toggle(drop_id):
    db = get_db()
    db.execute(
        "UPDATE dropzone SET is_public = CASE WHEN is_public = 1 THEN 0 ELSE 1 END WHERE id = ?",
        (drop_id,),
    )
    db.commit()
    flash("Visibility toggled.", "success")
    return redirect(url_for("admin_dropzone"))

# ---------------------------------------------------------------------------
# Shared Reports (all logged-in users)
# ---------------------------------------------------------------------------

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


@app.route("/reports")
@require_auth
def shared_reports():
    db = get_db()
    reports = db.execute(
        "SELECT * FROM dropzone WHERE is_report = 1 ORDER BY category, report_title, uploaded_at DESC"
    ).fetchall()

    # Group by category, preserving defined order
    grouped = {}
    for cat in REPORT_CATEGORIES:
        grouped[cat] = []
    for r in reports:
        cat = r["category"] or "Uncategorized"
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(r)
    # Remove empty categories
    grouped = {k: v for k, v in grouped.items() if v}

    return render_template("reports.html", grouped=grouped, user=g.user,
                           categories=REPORT_CATEGORIES)


# ---------------------------------------------------------------------------
# Web Terminal
# ---------------------------------------------------------------------------

@app.route("/admin/terminal")
@require_admin
def admin_terminal():
    return render_template("terminal.html", user=g.user)


@sock.route("/admin/terminal/ws")
def terminal_ws(ws):
    """WebSocket endpoint that bridges xterm.js to a real PTY shell."""
    import threading

    # Authenticate via JWT cookie (flask-sock doesn't run @require_admin)
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        ws.close(1008, "Authentication required")
        return
    user = decode_token(token)
    if not user or "admin" not in user.get("groups", []):
        ws.close(1008, "Forbidden")
        return

    username = user["sub"]
    terminal_audit.info("SESSION_START user=%s remote=%s", username, request.remote_addr)

    # Fork a PTY with bash
    child_pid, fd = pty.fork()
    if child_pid == 0:
        # Child process -- exec bash
        os.environ["TERM"] = "xterm-256color"
        os.environ["DW_USER"] = username
        os.environ["PS1"] = f"{username}@dw-admin:\\w$ "
        os.execlp("bash", "bash", "--norc", "--noprofile")

    done = threading.Event()

    def pty_to_ws():
        """Background thread: read PTY output and send to WebSocket."""
        try:
            while not done.is_set():
                rlist, _, _ = select.select([fd], [], [], 0.1)
                if fd in rlist:
                    output = os.read(fd, 4096)
                    if not output:
                        break
                    ws.send(output)
        except Exception:
            pass
        finally:
            done.set()

    reader = threading.Thread(target=pty_to_ws, daemon=True)
    reader.start()

    # Main thread: read WebSocket input and write to PTY
    try:
        while not done.is_set():
            try:
                msg = ws.receive(timeout=5)
            except Exception:
                if done.is_set():
                    break
                continue
            if msg is None:
                break
            try:
                data = json.loads(msg) if isinstance(msg, str) else {"type": "input", "data": msg}
            except json.JSONDecodeError:
                continue

            if data.get("type") == "input":
                os.write(fd, data["data"].encode())
            elif data.get("type") == "resize":
                rows = data.get("rows", 24)
                cols = data.get("cols", 80)
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except Exception:
        pass
    finally:
        done.set()
        reader.join(timeout=2)
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.kill(child_pid, signal.SIGTERM)
            os.waitpid(child_pid, 0)
        except (OSError, ChildProcessError):
            pass
        terminal_audit.info("SESSION_END user=%s remote=%s", username, request.remote_addr)


# ---------------------------------------------------------------------------
# System Status
# ---------------------------------------------------------------------------

@app.route("/admin/status")
@require_admin
def system_status():
    return render_template("status.html", user=g.user)


@app.route("/admin/status/data")
@require_admin
def system_status_data():
    import subprocess
    import re
    from datetime import datetime as _dt, timezone as _tz

    result = {}

    # --- App Health (check via dw-net from admin container) ---
    import urllib.request
    import urllib.error

    health = []
    endpoints = [
        ("Gateway (nginx)", "gateway", 80, "/", "301"),
        ("Admin (Flask)", "admin", 5050, "/health", "200"),
    ]
    for entry in APP_REGISTRY:
        container = entry.get("container")
        port = entry.get("port")
        health_path = entry.get("health")
        if container and port and health_path:
            # Use docker compose service name (container name minus 'dw-' prefix)
            svc_name = container.replace("dw-", "")
            endpoints.append((entry["name"], svc_name, port, health_path, "200"))

    for name, host, port, path, expected in endpoints:
        try:
            url = f"http://{host}:{port}{path}"
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=5)
            code = str(resp.status)
            health.append({"name": name, "status": "up", "detail": f"HTTP {code}"})
        except urllib.error.HTTPError as e:
            code = str(e.code)
            # 401/403 means the app is running (just requires auth)
            if e.code in (401, 403):
                health.append({"name": name, "status": "up", "detail": f"HTTP {code} (auth required)"})
            else:
                health.append({"name": name, "status": "down", "detail": f"HTTP {code}"})
        except Exception as e:
            health.append({"name": name, "status": "down", "detail": str(e)[:80]})
    result["health"] = health

    # --- System Resources ---
    resources = {}
    try:
        # CPU
        cpu_out = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "localhost", "true"],  # skip, use /proc
            capture_output=True, text=True, timeout=3,
        )
        # Read /proc/loadavg for load average
        load_out = subprocess.run(["cat", "/proc/loadavg"], capture_output=True, text=True, timeout=3)
        if load_out.returncode == 0:
            load_1m = float(load_out.stdout.split()[0])
            # Estimate CPU% from load avg vs nproc
            nproc_out = subprocess.run(["nproc"], capture_output=True, text=True, timeout=3)
            ncpu = int(nproc_out.stdout.strip()) if nproc_out.returncode == 0 else 1
            resources["cpu"] = min(round(load_1m / ncpu * 100, 1), 100)

        # Memory
        mem_out = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=3)
        if mem_out.returncode == 0:
            mem_line = mem_out.stdout.splitlines()[1].split()
            total_mb = int(mem_line[1])
            used_mb = int(mem_line[2])
            resources["memory"] = {
                "total": f"{total_mb}MB",
                "used": f"{used_mb}MB",
                "pct": round(used_mb / total_mb * 100) if total_mb else 0,
            }

        # Disk /
        df_root = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=3)
        if df_root.returncode == 0:
            parts = df_root.stdout.splitlines()[1].split()
            resources["disk_root"] = {"total": parts[1], "used": parts[2], "pct": int(parts[4].rstrip("%"))}

        # Disk /mnt/data
        df_data = subprocess.run(["df", "-h", "/mnt/data"], capture_output=True, text=True, timeout=3)
        if df_data.returncode == 0:
            parts = df_data.stdout.splitlines()[1].split()
            resources["disk_data"] = {"total": parts[1], "used": parts[2], "pct": int(parts[4].rstrip("%"))}
    except Exception:
        pass
    result["resources"] = resources

    # --- Docker Containers ---
    containers = []
    try:
        ps_out = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.State}}"],
            capture_output=True, text=True, timeout=5,
        )
        stats_out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"],
            capture_output=True, text=True, timeout=10,
        )
        stats_map = {}
        for line in stats_out.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                stats_map[parts[0]] = {"cpu": parts[1], "memory": parts[2]}

        for line in ps_out.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                name = parts[0]
                s = stats_map.get(name, {})
                # Extract uptime from status string
                uptime = parts[1].replace("Up ", "") if "Up" in parts[1] else parts[1]
                containers.append({
                    "name": name,
                    "running": parts[2] == "running",
                    "uptime": uptime,
                    "cpu": s.get("cpu", "-"),
                    "memory": s.get("memory", "-"),
                })
    except Exception:
        pass
    result["containers"] = containers

    # --- SSL Certificate ---
    ssl_info = {}
    try:
        ssl_out = subprocess.run(
            ["openssl", "x509", "-in", "/etc/nginx/ssl/octo.crt",
             "-noout", "-enddate", "-issuer"],
            capture_output=True, text=True, timeout=5,
        )
        if ssl_out.returncode != 0:
            # Try from the gateway container
            ssl_out = subprocess.run(
                ["docker", "exec", "dw-gateway", "openssl", "x509",
                 "-in", "/etc/nginx/ssl/octo.crt", "-noout", "-enddate", "-issuer"],
                capture_output=True, text=True, timeout=5,
            )
        if ssl_out.returncode == 0:
            for line in ssl_out.stdout.splitlines():
                if line.startswith("notAfter="):
                    date_str = line.split("=", 1)[1]
                    expiry = _dt.strptime(date_str.strip(), "%b %d %H:%M:%S %Y %Z")
                    days_left = (expiry - _dt.now()).days
                    ssl_info["expiry"] = expiry.strftime("%Y-%m-%d")
                    ssl_info["days_left"] = days_left
                elif line.startswith("issuer="):
                    ssl_info["issuer"] = line.split("=", 1)[1].strip()[:80]
    except Exception:
        pass
    result["ssl"] = ssl_info

    # --- Active Users (from nginx access log) ---
    active_users = []
    try:
        log_out = subprocess.run(
            ["docker", "exec", "dw-gateway", "tail", "-n", "500", "/var/log/nginx/access.log"],
            capture_output=True, text=True, timeout=5,
        )
        user_pages = {}
        user_last = {}
        for line in log_out.stdout.splitlines():
            # Format: IP - user [time] "METHOD /path ..." status bytes ...
            m = re.match(r'^(\S+)\s+-\s+(\S+)\s+\[([^\]]+)\]\s+"(\S+)\s+(\S+)', line)
            if m and m.group(2) != "-":
                user = m.group(2)
                path = m.group(5)
                time_str = m.group(3)
                if user not in user_pages:
                    user_pages[user] = set()
                user_pages[user].add(path)
                user_last[user] = time_str

        for user, pages in sorted(user_pages.items(), key=lambda x: len(x[1]), reverse=True):
            last = user_last.get(user, "")
            # Extract just the time part
            time_part = last.split(":")[1] + ":" + last.split(":")[2] if ":" in last else last
            active_users.append({
                "user": user,
                "pages": len(pages),
                "last_seen": time_part[:5] if len(time_part) >= 5 else time_part,
            })
    except Exception:
        pass
    result["active_users"] = active_users

    # --- Recent Errors (from per-container docker logs) ---
    recent_errors = []
    try:
        for svc in CONTAINER_SERVICES:
            err_out = subprocess.run(
                ["docker", "logs", "--tail", "10", svc["container"]],
                capture_output=True, text=True, timeout=5,
            )
            for line in err_out.stderr.splitlines():
                if "error" in line.lower() or "emerg" in line.lower() or "traceback" in line.lower():
                    recent_errors.append({"source": svc["name"], "line": line[:200]})
    except Exception:
        pass
    result["recent_errors"] = recent_errors[-20:]  # Last 20

    return jsonify(result)


# ---------------------------------------------------------------------------
# Log Viewer (Dozzle-style)
# ---------------------------------------------------------------------------

# Build container list from registry for log viewer
CONTAINER_SERVICES = [
    {"name": "gateway", "container": "dw-gateway"},
    {"name": "admin", "container": "dw-admin"},
]
for _entry in APP_REGISTRY:
    if _entry.get("container"):
        _svc_name = _entry["id"]
        CONTAINER_SERVICES.append({"name": _svc_name, "container": _entry["container"]})


@app.route("/admin/logs")
@require_admin
def log_viewer():
    services = [s["name"] for s in CONTAINER_SERVICES]
    return render_template("logs.html", user=g.user, services=services)


@app.route("/admin/logs/stream")
@require_admin
def log_stream():
    import subprocess
    import threading
    import queue
    import time as _time

    q = queue.Queue(maxsize=2000)

    def tail_docker(container, source_name):
        """Tail a Docker container's stdout logs."""
        try:
            proc = subprocess.Popen(
                ["docker", "logs", "-f", "--tail", "50", "--timestamps", container],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue
                # Docker timestamps: 2026-04-02T20:44:38.123456789Z <msg>
                ts = ""
                msg = line
                if len(line) > 30 and line[4] == "-" and "Z " in line[:35]:
                    parts = line.split(" ", 1)
                    ts = parts[0][:19].replace("T", " ")
                    msg = parts[1] if len(parts) > 1 else ""
                try:
                    q.put_nowait({"source": source_name, "line": msg, "ts": ts})
                except queue.Full:
                    pass
        except Exception:
            pass

    def generate():
        # Start a tailer thread for each container
        threads = []
        for svc in CONTAINER_SERVICES:
            t = threading.Thread(
                target=tail_docker, args=(svc["container"], svc["name"]), daemon=True
            )
            t.start()
            threads.append(t)

        try:
            while True:
                try:
                    data = q.get(timeout=15)
                    yield f"data: {json.dumps(data)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass

    return app.response_class(generate(), mimetype="text/event-stream")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "admin"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
