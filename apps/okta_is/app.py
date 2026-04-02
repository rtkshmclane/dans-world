"""
Okta Identity Inspector -- Decode and display JWT claims from Okta/Prisma ZTNA gateway.
Shows all headers, cookies, and decoded JWT tokens for authorization planning.
"""

import base64
import json
import os
import re
from datetime import datetime, timezone

from flask import Flask, request, render_template_string

app = Flask(__name__)

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Okta Identity Inspector</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f1923; color: #e0e0e0; padding: 1.5rem; }
h1 { color: #F37021; margin-bottom: .25rem; font-size: 1.6rem; }
.subtitle { color: #8899aa; margin-bottom: 1.5rem; font-size: .9rem; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
@media (max-width: 1000px) { .grid { grid-template-columns: 1fr; } }
.card { background: #1a2736; border-radius: 10px; padding: 1.25rem; border: 1px solid #2a3a4a; }
.card h2 { color: #F37021; font-size: 1.1rem; margin-bottom: .75rem; display: flex; align-items: center; gap: .5rem; }
.card h2 .count { background: #F37021; color: #fff; font-size: .7rem; padding: 2px 8px; border-radius: 10px; }
.full { grid-column: 1 / -1; }
table { width: 100%; border-collapse: collapse; font-size: .85rem; }
th { text-align: left; color: #8899aa; font-weight: 500; padding: .5rem .75rem; border-bottom: 1px solid #2a3a4a; white-space: nowrap; }
td { padding: .5rem .75rem; border-bottom: 1px solid #1e2e3e; word-break: break-all; }
tr:hover td { background: #1e2e3e; }
.tag { display: inline-block; background: #253655; color: #7eb8ff; padding: 2px 8px; border-radius: 4px; font-size: .78rem; margin: 2px; }
.tag.group { background: #2a4535; color: #7effaa; }
.tag.scope { background: #452a35; color: #ff7eaa; }
.tag.role { background: #45402a; color: #ffe07e; }
.tag.authz { background: #F37021; color: #fff; }
.jwt-part { margin-bottom: 1rem; }
.jwt-label { font-size: .8rem; color: #8899aa; margin-bottom: .25rem; text-transform: uppercase; letter-spacing: .5px; }
.jwt-raw { background: #0d1520; padding: .75rem; border-radius: 6px; font-family: "SF Mono", Monaco, monospace; font-size: .78rem; word-break: break-all; max-height: 200px; overflow-y: auto; color: #88aacc; border: 1px solid #1e2e3e; }
.claim-value { color: #7eb8ff; }
.claim-key { color: #F37021; font-weight: 500; }
.timestamp { color: #8899aa; font-size: .75rem; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: .75rem; font-weight: 600; }
.badge.valid { background: #1a3a2a; color: #4ade80; }
.badge.expired { background: #3a1a1a; color: #ef4444; }
.badge.unknown { background: #2a2a1a; color: #eab308; }
.authz-section { margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #2a3a4a; }
.authz-title { color: #F37021; font-size: .9rem; font-weight: 600; margin-bottom: .5rem; }
.authz-hint { color: #8899aa; font-size: .8rem; margin-bottom: .5rem; }
pre { white-space: pre-wrap; word-break: break-all; }
.empty { color: #556677; font-style: italic; padding: 1rem; text-align: center; }
.refresh { float: right; background: #253655; color: #7eb8ff; border: 1px solid #3a5a7a; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: .8rem; }
.refresh:hover { background: #3a5a7a; }
</style>
</head>
<body>
<div style="display:flex;justify-content:space-between;align-items:flex-start;">
  <div>
    <h1>Okta Identity Inspector</h1>
    <p class="subtitle">JWT claims and headers from Okta / Prisma ZTNA gateway</p>
  </div>
  <button class="refresh" onclick="location.reload()">Refresh</button>
</div>

<div class="grid">

  <!-- Decoded JWT Claims -->
  {% for jwt_info in jwts %}
  <div class="card full">
    <h2>JWT Token {% if jwt_info.source %}({{ jwt_info.source }}){% endif %}
      {% if jwt_info.expired is not none %}
        {% if jwt_info.expired %}<span class="badge expired">EXPIRED</span>
        {% else %}<span class="badge valid">VALID</span>{% endif %}
      {% else %}<span class="badge unknown">NO EXP</span>{% endif %}
    </h2>

    <div class="jwt-part">
      <div class="jwt-label">Header</div>
      <div class="jwt-raw"><pre>{{ jwt_info.header_json }}</pre></div>
    </div>

    <table>
      <tr><th>Claim</th><th>Value</th><th>Authz Use</th></tr>
      {% for claim in jwt_info.claims %}
      <tr>
        <td><span class="claim-key">{{ claim.key }}</span></td>
        <td>
          {% if claim.is_list %}
            {% for v in claim.value %}<span class="tag {{ claim.tag_class }}">{{ v }}</span>{% endfor %}
          {% elif claim.is_timestamp %}
            <span class="claim-value">{{ claim.display }}</span>
            <span class="timestamp">{{ claim.human }}</span>
          {% else %}
            <span class="claim-value">{{ claim.value }}</span>
          {% endif %}
        </td>
        <td>{% if claim.authz_hint %}<span class="tag authz">{{ claim.authz_hint }}</span>{% endif %}</td>
      </tr>
      {% endfor %}
    </table>

    <div class="authz-section">
      <div class="authz-title">Authorization Attributes Available</div>
      <div class="authz-hint">These claims can be used for role-based or attribute-based access control:</div>
      <table>
        <tr><th>Strategy</th><th>Claim</th><th>Example Usage</th></tr>
        {% for sug in jwt_info.suggestions %}
        <tr>
          <td><span class="tag authz">{{ sug.strategy }}</span></td>
          <td><span class="claim-key">{{ sug.claim }}</span></td>
          <td style="color:#8899aa;font-size:.8rem;">{{ sug.example }}</td>
        </tr>
        {% endfor %}
        {% if not jwt_info.suggestions %}
        <tr><td colspan="3" class="empty">No obvious authorization claims found</td></tr>
        {% endif %}
      </table>
    </div>

    <div class="jwt-part" style="margin-top:1rem;">
      <div class="jwt-label">Raw Token ({{ jwt_info.raw|length }} chars)</div>
      <div class="jwt-raw"><pre>{{ jwt_info.raw[:500] }}{% if jwt_info.raw|length > 500 %}...{% endif %}</pre></div>
    </div>
  </div>
  {% endfor %}

  {% if not jwts %}
  <div class="card full">
    <h2>No JWT Tokens Found</h2>
    <p class="empty">No JWT tokens detected in Authorization header, cookies, or custom headers.<br>
    Check if the Prisma ZTNA gateway is passing tokens through.</p>
  </div>
  {% endif %}

  <!-- Request Headers -->
  <div class="card">
    <h2>Request Headers <span class="count">{{ headers|length }}</span></h2>
    <table>
      <tr><th>Header</th><th>Value</th></tr>
      {% for h in headers %}
      <tr>
        <td><span class="claim-key">{{ h.name }}</span></td>
        <td style="max-width:400px;overflow:hidden;text-overflow:ellipsis;">{{ h.value[:200] }}{% if h.value|length > 200 %}...{% endif %}</td>
      </tr>
      {% endfor %}
    </table>
  </div>

  <!-- Cookies -->
  <div class="card">
    <h2>Cookies <span class="count">{{ cookies|length }}</span></h2>
    {% if cookies %}
    <table>
      <tr><th>Name</th><th>Value</th></tr>
      {% for c in cookies %}
      <tr>
        <td><span class="claim-key">{{ c.name }}</span></td>
        <td style="max-width:400px;">{{ c.value[:100] }}{% if c.value|length > 100 %}...{% endif %}</td>
      </tr>
      {% endfor %}
    </table>
    {% else %}
    <p class="empty">No cookies present</p>
    {% endif %}
  </div>

</div>
</body>
</html>"""

# Claims that are useful for authorization
AUTHZ_CLAIMS = {
    "groups": "RBAC",
    "roles": "RBAC",
    "role": "RBAC",
    "scp": "Scope",
    "scope": "Scope",
    "permissions": "ABAC",
    "entitlements": "ABAC",
    "email": "Identity",
    "sub": "Identity",
    "preferred_username": "Identity",
    "department": "ABAC",
    "title": "ABAC",
    "org_id": "Tenant",
    "tenant": "Tenant",
    "amr": "Auth Method",
    "acr": "Auth Level",
    "auth_time": "Session",
}

TAG_CLASSES = {
    "groups": "group",
    "roles": "role",
    "role": "role",
    "scp": "scope",
    "scope": "scope",
    "permissions": "scope",
}

TIMESTAMP_CLAIMS = {"exp", "iat", "nbf", "auth_time", "updated_at"}


def decode_jwt_part(part):
    """Base64url decode a JWT segment."""
    padding = 4 - len(part) % 4
    if padding != 4:
        part += "=" * padding
    try:
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception:
        return None


def find_jwts(headers, cookies):
    """Find all JWTs in headers and cookies."""
    jwts = []
    jwt_re = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

    # Check Authorization header
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if jwt_re.match(token):
            jwts.append(("Authorization: Bearer", token))

    # Check all headers for JWT-like values
    jwt_headers = [
        "X-Jwt-Assertion", "X-User-Token", "X-Id-Token", "X-Access-Token",
        "X-Forwarded-Access-Token", "X-Auth-Token", "X-Amzn-Oidc-Data",
        "X-Amzn-Oidc-Accesstoken", "X-Ms-Token-Aad-Id-Token",
        "X-Palo-Alto-User-Token", "X-Prisma-Access-Token",
        "Cf-Access-Jwt-Assertion",
    ]
    for name in jwt_headers:
        val = headers.get(name, "")
        if val and jwt_re.match(val):
            jwts.append((name, val))

    # Check all headers (catch custom ones)
    for name, val in headers.items():
        if name in ("Authorization",):
            continue
        if val and jwt_re.match(val):
            source = name
            if not any(s == source for s, _ in jwts):
                jwts.append((source, val))

    # Check cookies
    for name, val in cookies.items():
        if val and jwt_re.match(val):
            jwts.append((f"Cookie: {name}", val))

    return jwts


def process_jwt(source, raw):
    """Decode a JWT and extract claims with authz hints."""
    parts = raw.split(".")
    if len(parts) < 2:
        return None

    header = decode_jwt_part(parts[0])
    payload = decode_jwt_part(parts[1])
    if not payload:
        return None

    now = datetime.now(timezone.utc).timestamp()
    expired = None
    if "exp" in payload:
        expired = payload["exp"] < now

    claims = []
    for key, value in payload.items():
        is_list = isinstance(value, list)
        is_ts = key in TIMESTAMP_CLAIMS and isinstance(value, (int, float))
        display = value
        human = ""
        if is_ts:
            try:
                dt = datetime.fromtimestamp(value, tz=timezone.utc)
                human = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                display = str(value)
            except Exception:
                display = str(value)

        claims.append({
            "key": key,
            "value": value if is_list else (display if not is_list else value),
            "is_list": is_list,
            "is_timestamp": is_ts,
            "display": str(display),
            "human": human,
            "tag_class": TAG_CLASSES.get(key, ""),
            "authz_hint": AUTHZ_CLAIMS.get(key, ""),
        })

    # Build authorization suggestions
    suggestions = []
    for key, value in payload.items():
        if key == "groups" and isinstance(value, list):
            suggestions.append({
                "strategy": "RBAC",
                "claim": "groups",
                "example": f'if "admin" in token.groups: grant_admin()',
            })
        elif key == "roles" or key == "role":
            suggestions.append({
                "strategy": "RBAC",
                "claim": key,
                "example": f"Map {key} to Dan's World group permissions",
            })
        elif key in ("scp", "scope"):
            suggestions.append({
                "strategy": "Scope",
                "claim": key,
                "example": "Restrict API access based on granted scopes",
            })
        elif key == "email":
            suggestions.append({
                "strategy": "Identity",
                "claim": "email",
                "example": "Auto-provision user account from email domain",
            })
        elif key == "department":
            suggestions.append({
                "strategy": "ABAC",
                "claim": "department",
                "example": "Gate access to analytics apps by department",
            })
        elif key == "amr":
            suggestions.append({
                "strategy": "MFA Check",
                "claim": "amr",
                "example": 'Require "mfa" in amr[] for admin routes',
            })

    return {
        "source": source,
        "raw": raw,
        "header": header,
        "header_json": json.dumps(header, indent=2) if header else "{}",
        "claims": claims,
        "expired": expired,
        "suggestions": suggestions,
    }


@app.route("/")
@app.route("/health")
def index():
    if request.path == "/health":
        return "ok"

    headers_dict = dict(request.headers)
    cookies_dict = dict(request.cookies)

    # Find and decode JWTs
    raw_jwts = find_jwts(headers_dict, cookies_dict)
    jwts = []
    for source, raw in raw_jwts:
        info = process_jwt(source, raw)
        if info:
            jwts.append(info)

    # Prepare headers for display (mask sensitive values)
    header_list = []
    for name, value in sorted(headers_dict.items()):
        header_list.append({"name": name, "value": value})

    cookie_list = []
    for name, value in sorted(cookies_dict.items()):
        cookie_list.append({"name": name, "value": value})

    return render_template_string(
        TEMPLATE,
        jwts=jwts,
        headers=header_list,
        cookies=cookie_list,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=True)
