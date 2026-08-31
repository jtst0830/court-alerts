"""
One-time script: fetches the latest docket entry for each of the
four target cases via the CourtListener REST API, builds the
initial alerts.html, and pushes it to GitHub.
"""
import os
import html
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

CL_TOKEN       = os.environ["COURTLISTENER_TOKEN"]
GH_TOKEN       = os.environ["GITHUB_TOKEN"]
GH_OWNER       = os.environ.get("GITHUB_OWNER", "jtst0830")
GH_REPO        = os.environ.get("GITHUB_REPO", "court-alerts")
GH_BRANCH      = os.environ.get("GITHUB_BRANCH", "main")
FILE_PATH      = os.environ.get("ALERTS_FILE_PATH", "alerts.html")

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


def fetch_latest_entry(docket_id):
    """Get the most recent docket entry for a given docket."""
    url = f"https://www.courtlistener.com/api/rest/v4/docket-entries/?docket={docket_id}&order_by=-date_filed&order_by=-entry_number"
    r = requests.get(url, headers=CL_HEADERS)
    r.raise_for_status()
    results = r.json().get("results", [])
    return results[0] if results else None


def build_html(entries):
    """Build the full alerts.html document with seed entries."""
    parts = ["""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Court Docket Alerts — US v. Cole / Kerkhoff v. Blaze Media</title>
  <style>
    body  { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px; margin: 0 auto; padding: 2rem; background: #f8f9fa; }
    h1    { color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: .5rem; }
    h2    { color: #16213e; }
    .alert-entry {
      background: #fff; border: 1px solid #dee2e6; border-left: 5px solid #e94560;
      border-radius: 8px; padding: 1rem 1.5rem; margin-bottom: 1.5rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .alert-entry h3 { margin-top: 0; color: #0f3460; }
    .timestamp { color: #6c757d; font-size: 0.85rem; }
    .seed-banner {
      background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px;
      padding: 1rem; margin-bottom: 2rem; color: #155724;
    }
    a { color: #0f3460; }
  </style>
</head>
<body>
  <h1>Court Docket Alerts</h1>
  <p class="timestamp">Monitoring: US v. Cole · US v. Brian Cole Jr. · Kerkhoff v. Blaze Media LLC</p>
  <div class="seed-banner">
    <strong>Initial seed:</strong> This file was generated with the latest entry from each
    case as of the script run date. New alerts are appended automatically via CourtListener webhooks.
  </div>
  <!-- NEW ALERTS BELOW THIS LINE -->
"""]

    for docket_id, case_name in entries:
        entry = entries[(docket_id, case_name)]
        if entry is None:
            parts.append(f"""
    <div class="alert-entry">
      <h3>{html.escape(case_name)}</h3>
      <p><em>No entries found.</em></p>
      <hr>
    </div>""")
            continue

        date_filed  = entry.get("date_filed", "Unknown")
        description = entry.get("description", "No description")
        entry_num   = entry.get("entry_number", "?")

        parts.append(f"""
    <div class="alert-entry" data-docket="{html.escape(str(docket_id))}">
      <h3>{html.escape(case_name)}</h3>
      <p><strong>Entry #{html.escape(str(entry_num))}</strong> — {html.escape(str(date_filed))}</p>
      <p>{html.escape(description)}</p>
      <hr>
    </div>""")

    parts.append("""
</body>
</html>""")
    return "\n".join(parts)


def push_to_github(content):
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{FILE_PATH}"
    payload = {
        "message": "Seed alerts.html with latest entries from all tracked dockets",
        "branch": GH_BRANCH,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
    }
    # Check if file exists (need SHA to update)
    r = requests.get(f"{url}?ref={GH_BRANCH}", headers=GH_HEADERS)
    if r.status_code == 200:
        payload["sha"] = r.json()["sha"]
    r = requests.put(url, headers=GH_HEADERS, json=payload)
    if r.status_code in (200, 201):
        print(f"[OK] Pushed {FILE_PATH} to {GH_OWNER}/{GH_REPO}")
    else:
        print(f"[ERROR] {r.status_code}: {r.text}")


def main():
    print("Fetching latest entries from CourtListener...")
    entries = {}
    for docket_id, case_name in TARGET_DOCKETS.items():
        print(f"  → Docket {docket_id}: {case_name}")
        entry = fetch_latest_entry(docket_id)
        entries[(docket_id, case_name)] = entry
        if entry:
            print(f"    Latest: Entry #{entry.get('entry_number')} — {entry.get('date_filed')}")
        else:
            print("    No entries found.")

    print("\nBuilding HTML...")
    html_doc = build_html(dict(entries))

    print("Pushing to GitHub...")
    push_to_github(html_doc)
    print("Done!")


if __name__ == "__main__":
    main()
