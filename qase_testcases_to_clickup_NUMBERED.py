import os
import re
import json
from flask import Flask, request, jsonify, render_template_string
import requests

app = Flask(__name__)

# --- CLICKUP CONFIG ---
CLICKUP_TOKEN = "pk_188468937_C74O5LJ8IMKNHTPMTC5QAHGGKW3U9I6Z"
CLICKUP_LIST_ID_DRESSUP = "901807146872"
CLICKUP_DEFAULT_STATUS = "to do"
CLICKUP_API_URL = f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID_DRESSUP}/task"
CLICKUP_HEADERS = {
    "Authorization": CLICKUP_TOKEN,
    "Content-Type": "application/json"
}

# --- QASE CONFIG ---
QASE_API_TOKEN = "899e1d184ff7c82a3c1d13a624c496d3c97f4b41f03916c5a01745c20159f5b8"
PROJECT_CODE = "DRESSUP"
QASE_API_URL = f"https://api.qase.io/v1/case/{PROJECT_CODE}?limit=100"

# Assignee mapping (Qase name → ClickUp user ID)
known_testers = {
    "maia khalvashi": 73402724
    # დაამატე სხვა ტესტერებიც საჭიროებისამებრ
}

def extract_severity(actual_result: str, title: str) -> str:
    text = f"{actual_result.lower()} {title.lower()}"
    if "critical" in text:
        return "Critical"
    elif "high" in text:
        return "High"
    elif "low" in text:
        return "Low"
    return "Normal"

def extract_assignee(text: str):
    for name, clickup_id in known_testers.items():
        if name in text.lower():
            return name, clickup_id
    return None, None

def extract_device_info(description: str) -> str:
    if not description:
        return "მოწყობილობა არ არის მითითებული"
    lines = description.strip().splitlines()
    for line in lines:
        if 'device' in line.lower() or 'მოწყობილობა' in line.lower():
            return line.strip()
    return lines[0].strip() if lines else "მოწყობილობა არ არის მითითებული"

def format_steps_numbered(steps):
    if not steps:
        return "[ნაბიჯები არ მოიძებნა]"
    output = []
    for i, step in enumerate(steps):
        action = step.get("action", "").strip()
        output.append(f"{i+1}. {action}")
    return "\n".join(output)

def load_sent_bugs():
    try:
        with open("sent_bugs.txt", "r", encoding="utf-8") as file:
            return set(line.strip() for line in file)
    except FileNotFoundError:
        return set()

def save_sent_bug(key):
    with open("sent_bugs.txt", "a", encoding="utf-8") as file:
        file.write(f"{key}\n")

def is_duplicate_open(key: str) -> bool:
    team_id = "90181092380"
    params = {
        "archived": False,
        "include_closed": True,
        "page": 0
    }
    tasks_url = f"https://api.clickup.com/api/v2/team/{team_id}/task"
    res = requests.get(tasks_url, headers=CLICKUP_HEADERS, params=params)
    if res.status_code != 200:
        return False
    for task in res.json().get("tasks", []):
        if key in task.get("description", ""):
            status = task.get("status", {}).get("status", "").lower()
            if status not in ["closed", "done", "fixed"]:
                return True
    return False

@app.route("/")
def home():
    return render_template_string('''
        <html>
        <head><title>Qase → ClickUp</title></head>
        <body style="font-family:Arial;padding:2rem;">
            <h2>Qase → ClickUp ინტეგრაცია</h2>
            <p>დააჭირე ქვემოთ ღილაკს ტესტ ქეისების გადასატანად:</p>
            <form action="/send_testcases" method="post">
                <input type="submit" value="გადაიტანე ტესტ ქეისები">
            </form>
        </body>
        </html>
    ''')

@app.route("/send_testcases", methods=["POST"])
def send_testcases():
    return jsonify({"message": "შემდეგ ეტაპზე ჩასამატებელი კოდია: Qase API-დან წამოღება და დამუშავება."})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
