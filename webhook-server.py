"""
Flask server that receives CourtListener Docket Alert webhooks,
formats each alert as HTML, and appends it to alerts.html
in the GitHub repo via the GitHub Contents API.
"""
import os
import json
import hashlib
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

GITHUB_TOKEN        = os.environ["GITHUB_TOKEN"]
GITHUB_OWNER        = os.environ.get("GITHUB_OWNER", "jtst0830")
GITHUB_REPO         = os.environ.get("GITHUB_REPO", "court-alerts")
GITHUB_BRANCH       = os.environ.get("GITHUB_BRANCH", "main")
ALERTS_FILE_PATH    = os.environ.get("ALERTS_FILE_PATH", "alerts.html")
COURTLISTENER_IPS   = os.environ.get("COURTLISTENER_IPS", "").split(",")

# In-memory set for idempotency keys we've already processed
_seen_keys = set()

# Map docket IDs to human-readable case names
DOCKET_NAMES = {
    "71994556": "United States v. Cole (Docket 71994556)",
    "72099987": "United States v. Cole (Docket 72099987)",
    "72236187": "United States v. Brian Cole Jr. (Docket 72236187)",
    "73220023": "Kerkhoff v. Blaze Media LLC (Docket 73220023)",
}


def github_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_file_sha():
    """Get the current SHA of alerts.html so we can update it."""
    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/contents/{ALERTS_FILE_PATH}?ref={GITHUB_BRANCH}"
    )
    r = requests.get(url, headers=github_headers())
    if r.status_code == 200:
        return r.json().get("sha")
    return None  # file doesn't exist yet


def read_current_html():
    """Download the raw current content of alerts.html."""
    url = (
        f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/{GITHUB_BRANCH}/{ALERTS_FILE_PATH}"
    )
    r = requests.get(url)
    if r.status_code == 200:
        return r.text
    return None


def push_html(new_html, sha=None):
    """Push updated HTML to GitHub, creating or updating the file."""
    import base64
    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/contents/{ALERTS_FILE_PATH}"
    )
    payload = {
        "message": "Update alerts.html with new docket alert",
        "branch": GITHUB_BRANCH,
        "content": base64.b64encode(new_html.encode("utf-8")).decode("utf-8"),
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=github_headers(), json=payload)
    if r.status_code in (200, 201):
        print(f"[OK] Pushed update to {ALERTS_FILE_PATH}")
    else:
        print(f"[ERROR] GitHub API returned {r.status_code}: {r.text}")
    return r.status_code in (200, 201)


def format_alert_html(entry, docket_id, case_name):
    """Convert a single docket entry dict into an HTML alert block."""
    import html
    date_filed  = entry.get("date_filed", "Unknown date")
    description = entry.get("description", "No description available")
    entry_num   = entry.get("entry_number", "?")
    doc_url     = ""

    # If there are RECAP documents attached, link to the first one
    recap_docs = entry.get("recap_documents", [])
    if recap_docs:
        doc_url = recap_docs[0].get("filepath_local", "")

    alert_html = f"""
    <div class="alert-entry" data-docket="{html.escape(str(docket_id))}">
      <h3>{html.escape(case_name)}</h3>
      <p><strong>Entry #{html.escape(str(entry_num))}</strong> — {html.escape(str(date_filed))}</p>
      <p>{html.escape(description)}</p>
      {"<p><a href='" + html.escape(doc_url) + "' target='_blank'>View document</a></p>" if doc_url else ""}
      <hr>
    </div>
"""
    return alert_html


def insert_alert_before_closing(current_html, alert_block):
    """
    Insert the new alert block just before </body> so the newest
    alerts appear at the top (we insert after the opening of the
    alerts container).
    """
    marker = "<!-- NEW ALERTS BELOW THIS LINE -->"
    if marker in current_html:
        return current_html.replace(marker, marker + "\n" + alert_block)
    # Fallback: insert before </body>
    return current_html.replace("</body>", alert_block + "\n</body>")


@app.route("/webhook", methods=["POST"])
def webhook():
    # --- IP verification (optional) ---
    if COURTLISTENER_IPS and COURTLISTENER_IPS[0]:
        sender_ip = request.remote_addr
        if sender_ip not in COURTLISTENER_IPS:
            print(f"[REJECTED] IP {sender_ip} not in allow-list")
            return jsonify({"error": "unauthorized"}), 403

    # --- Idempotency check ---
    idempotency_key = request.headers.get("Idempotency-Key", "")
    if idempotency_key and idempotency_key in _seen_keys:
        print(f"[SKIP] Duplicate event {idempotency_key}")
        return jsonify({"status": "duplicate, ignored"}), 200
    if idempotency_key:
        _seen_keys.add(idempotency_key)

    data = request.get_json()
    if not data:
        return jsonify({"error": "no JSON body"}), 400

    results = data.get("payload", {}).get("results", [])
    if not results:
        return jsonify({"status": "no results"}), 200

    # Read current HTML from GitHub
    current_html = read_current_html()
    if current_html is None:
        print("[ERROR] Could not read alerts.html from GitHub")
        return jsonify({"error": "could not read alerts.html"}), 500

    # Process each new docket entry
    alert_blocks = []
    for result in results:
        docket_info = result.get("docket", {})
        docket_id   = str(docket_info.get("id", ""))
        case_name   = DOCKET_NAMES.get(docket_id, docket_info.get("case_name", f"Docket {docket_id}"))

        for entry in result.get("docket_entries", []):
            block = format_alert_html(entry, docket_id, case_name)
            alert_blocks.append(block)

    if not alert_blocks:
        return jsonify({"status": "no docket entries"}), 200

    # Prepend new alerts (newest first)
    for block in reversed(alert_blocks):
        current_html = insert_alert_before_closing(current_html, block)

    # Push back to GitHub
    sha = get_file_sha()
    success = push_html(current_html, sha)
    if success:
        return jsonify({"status": "ok", "alerts_added": len(alert_blocks)}), 200
    else:
        return jsonify({"error": "push failed"}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "alive"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("WEBHOOK_PORT", 5000))
    app.run(host="0.0.0.0", port=port)
