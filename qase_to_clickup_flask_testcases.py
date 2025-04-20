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
QASE_API_TOKEN = "dd203d20ea7992c881633c69c093d0509997d86687fd317141fcfaba9bc5d71c"
PROJECT_CODE = "DRESSUP"
QASE_API_URL = f"https://api.qase.io/v1/case/{PROJECT_CODE}?limit=100"
QASE_HEADERS = {
    "Authorization": QASE_API_TOKEN,
    "Content-Type": "application/json"
}

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
        expected = step.get("expected_result", "").strip()
        output.append(f"{i+1}. {action}\nმოსალოდნელი შედეგი: {expected}")
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
    response = requests.get(QASE_API_URL, headers=QASE_HEADERS)
    if response.status_code != 200:
        return jsonify({"status": "error", "message": "Qase API error."}), 500

    data = response.json()
    testcases = data.get("result", {}).get("entities", [])

    created_defects = []
    sent_bugs = load_sent_bugs()

    for test in testcases:
        title = test.get("title", "")
        actual_result = test.get("actual_result", "")
        description = test.get("description", "")
        steps = test.get("steps", [])

        if "dressup" not in title.lower() and "dressup" not in actual_result.lower():
            continue

        severity = extract_severity(actual_result, title)
        priority = 1 if severity == "Critical" else 2 if severity == "High" else 3 if severity == "Low" else None
        assignee_name, assignee_id = extract_assignee(f"{title} {actual_result}")
        device_info = extract_device_info(description)
        step_list = format_steps_numbered(steps)

        combined_steps = " ".join([
            s.get('action', '').strip().lower() for s in steps
        ])
        unique_key = combined_steps.strip()

        if unique_key in sent_bugs and is_duplicate_open(unique_key):
            continue

        clean_title = re.sub(r" ?(Critical|High|Low)", "", title, flags=re.IGNORECASE)
        for name in known_testers.keys():
            clean_title = clean_title.replace(name.title(), "").strip()

        bug_description = f"📱 მოწყობილობა: {device_info}\n\n📋 ნაბიჯები:\n{step_list}\n\n🔍 მიმდინარე შედეგი:\n{actual_result}\n\n🔑 KEY: {unique_key}"

        payload = {
            "name": f"[BUG] {clean_title}",
            "description": bug_description,
            "assignees": [assignee_id] if assignee_id else [],
            "priority": priority,
            "tags": ["auto-imported", "qase"]
        }

        res = requests.post(CLICKUP_API_URL, headers=CLICKUP_HEADERS, json=payload)
        created_defects.append(payload)
        save_sent_bug(unique_key)

    return jsonify({
        "status": "ok",
        "message": f"{len(created_defects)} ტესტ ქეისი დაემატა ClickUp-ში.",
        "created": created_defects
    })

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
