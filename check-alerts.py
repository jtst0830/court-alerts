"""
Polling script for GitHub Actions: checks each tracked docket for
new entries since the last known entry, formats new ones as HTML,
and appends them to alerts.html.

Uses .last-seen.json (stored in the repo) to track which entries
have already been processed.
"""
import os
import json
import html
import base64
import requests

CL_TOKEN = os.environ["COURTLISTENER_TOKEN"]
GH_TOKEN = os.environ["GITHUB_TOKEN"]
REPO     = os.environ.get("GITHUB_REPOSITORY", "jtst0830/court-alerts")

TARGET_DOCKETS = {
    "71994556": "United States v. Cole (Docket 71994556)",
    "72099987": "United States v. Cole (Docket 72099987)",
    "72236187": "United States v. Brian Cole Jr. (Docket 72236187)",
    "73220023": "Kerkhoff v. Blaze Media LLC (Docket 73220023)",
}

CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}
GH_HEADERS = {
    "Authorization": f"token {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

STATE_FILE  = ".last-seen.json"
ALERTS_FILE = "alerts.html"


def load_state():
    """Load the last-seen state from the repo."""
    url = f"https://api.github.com/repos/{REPO}/contents/{STATE_FILE}"
    r = requests.get(url, headers=GH_HEADERS)
    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"]).decode("utf-8")
        return json.loads(content), r.json().get("sha")
    return {}, None


def save_state(state, sha=None):
    """Save state back to the repo."""
    url = f"https://api.github.com/repos/{REPO}/contents/{STATE_FILE}"
    payload = {
        "message": "Update last-seen state",
        "content": base64.b64encode(
            json.dumps(state, indent=2).encode()
        ).decode(),
    }
    if sha:
        payload["sha"] = sha
    requests.put(url, headers=GH_HEADERS, json=payload)


def fetch_new_entries(docket_id, last_seen_seq):
    """Fetch entries newer than the last seen recap_sequence_number."""
    url = (
        f"https://www.courtlistener.com/api/rest/v4/docket-entries/"
        f"?docket={docket_id}&order_by=-recap_sequence_number"
    )
    r = requests.get(url, headers=CL_HEADERS)
    r.raise_for_status()
    results = r.json().get("results", [])

    new_entries = []
    for entry in results:
        seq = entry.get("recap_sequence_number", "")
        if seq and last_seen_seq and seq <= last_seen_seq:
            break
        new_entries.append(entry)
    return new_entries


def format_alert(entry, docket_id, case_name):
    seq    = entry.get("recap_sequence_number", "?")
    date_f = entry.get("date_filed", "Unknown")
    desc   = entry.get("description", "No description")
    return f"""
    <div class="alert-entry" data-docket="{html.escape(str(docket_id))}">
      <h3>{html.escape(case_name)}</h3>
      <p><strong>Entry #{html.escape(str(seq))}</strong> — {html.escape(str(date_f))}</p>
      <p>{html.escape(desc)}</p>
      <hr>
    </div>"""


def read_alerts_html():
    url = f"https://api.github.com/repos/{REPO}/contents/{ALERTS_FILE}"
    r = requests.get(url, headers=GH_HEADERS)
    if r.status_code == 200:
        return base64.b64decode(r.json()["content"]).decode("utf-8"), r.json().get("sha")
    return None, None


def push_alerts_html(content, sha=None):
    url = f"https://api.github.com/repos/{REPO}/contents/{ALERTS_FILE}"
    payload = {
        "message": "Auto-update: new docket alert(s) appended",
        "content": base64.b64encode(content.encode()).decode(),
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=GH_HEADERS, json=payload)
    return r.status_code in (200, 201)


def insert_alert(current_html, alert_block):
    marker = "<!-- NEW ALERTS BELOW THIS LINE -->"
    if marker in current_html:
        return current_html.replace(marker, marker + "\n" + alert_block)
    return current_html.replace("</body>", alert_block + "\n</body>")


def main():
    state, state_sha = load_state()
    all_new = []

    for docket_id, case_name in TARGET_DOCKETS.items():
        last_seq = state.get(docket_id, "")
        print(f"Checking docket {docket_id}: {case_name}")
        print(f"  Last seen: {last_seq}")

        new_entries = fetch_new_entries(docket_id, last_seq)
        if not new_entries:
            print("  No new entries.")
            continue

        print(f"  {len(new_entries)} new entry/entries!")
        for entry in new_entries:
            block = format_alert(entry, docket_id, case_name)
            all_new.append(block)

        # Update last-seen to the newest entry's sequence
        newest_seq = new_entries[0].get("recap_sequence_number", "")
        if newest_seq:
            state[docket_id] = newest_seq

    if not all_new:
        print("\nNo new alerts across all dockets. Done.")
        return

    # Read current alerts.html
    current_html, html_sha = read_alerts_html()
    if current_html is None:
        print("[ERROR] Could not read alerts.html")
        return

    # Prepend new alerts (newest first)
    for block in reversed(all_new):
        current_html = insert_alert(current_html, block)

    # Push updated HTML
    if push_alerts_html(current_html, html_sha):
        print(f"[OK] Pushed {len(all_new)} new alert(s) to alerts.html")
    else:
        print("[ERROR] Failed to push alerts.html")
        return

    # Save updated state
    save_state(state, state_sha)
    print("[OK] State saved.")


if __name__ == "__main__":
    main()
