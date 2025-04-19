import os
import re
import json
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

CLICKUP_API_URL = "https://api.clickup.com/api/v2/list/901807146872/task"
CLICKUP_API_TOKEN = "pk_188468937_C74O5LJ8IMKNHTPMTC5QAHGGKW3U9I6Z"

# Assignee mapping (Qase name → ClickUp user ID)
known_testers = {
    "maia khalvashi": 73402724
    # სხვა ტესტერებიც შეგიძლიათ დაამატოთ
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
            return clickup_id
    return None

def extract_device_info(description: str) -> str:
    if not description:
        return "მოწყობილობა არ არის მითითებული"
    lines = description.strip().splitlines()
    for line in lines:
        if 'device' in line.lower() or 'მოწყობილობა' in line.lower():
            return line.strip()
    return lines[0].strip() if lines else "მოწყობილობა არ არის მითითებული"

def load_sent_bugs():
    try:
        with open("sent_bugs.txt", "r", encoding="utf-8") as file:
            return set(line.strip() for line in file)
    except FileNotFoundError:
        return set()

def save_sent_bug(key):
    with open("sent_bugs.txt", "a", encoding="utf-8") as file:
        file.write(f"{key}\n")

@app.route("/send_testcases", methods=["POST"])
def send_testcases():
    data = request.get_json()
    testcases = data.get("cases", [])
    created_defects = []
    sent_bugs = load_sent_bugs()

    for test in testcases:
        title = test.get("title", "")
        actual_result = test.get("actual_result", "")
        description = test.get("description", "")

        # ✅ ნაბიჯი 1: dressup keyword filter
        if "dressup" not in title.lower() and "dressup" not in actual_result.lower():
            continue

        # ✅ ნაბიჯი 2: ამოვიღოთ severity
        severity = extract_severity(actual_result, title)
        priority = 1 if severity == "Critical" else 2 if severity == "High" else 3 if severity == "Low" else None

        # ✅ ნაბიჯი 3: ამოვიღოთ Assignee (ტესტერის სახელი)
        assignee_id = extract_assignee(f"{title} {actual_result}")

        # ✅ ნაბიჯი 4: ამოვიღოთ Device info Description-იდან
        device_info = extract_device_info(description)

        # ✅ ნაბიჯი 5: დუბლიკატის შემოწმება
        unique_key = f"{title.strip().lower()}::{assignee_id}"
        if unique_key in sent_bugs:
            continue

        bug_description = f"📱 მოწყობილობა: {device_info}\n\n🔍 მიმდინარე შედეგი:\n{actual_result}\n\n📌 მოსალოდნელი შედეგი:\n[აქ ჩაწერე მოსალოდნელი შედეგი]"

        payload = {
            "name": f"[BUG] {title}",
            "description": bug_description,
            "assignees": [assignee_id] if assignee_id else [],
            "priority": priority,
            "tags": ["auto-imported", "qase"]
        }

        # Uncomment this to actually send to ClickUp
        # headers = {"Authorization": CLICKUP_API_TOKEN, "Content-Type": "application/json"}
        # res = requests.post(CLICKUP_API_URL, headers=headers, json=payload)

        created_defects.append(payload)
        save_sent_bug(unique_key)

    return jsonify({
        "status": "ok",
        "message": f"{len(created_defects)} ტესტ ქეისი დაემატა ClickUp-ში.",
        "created": created_defects
    })

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
