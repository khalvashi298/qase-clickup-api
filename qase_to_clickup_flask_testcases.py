import os
from flask import Flask, jsonify, Response
import requests
import re
import json

app = Flask(__name__)

# QASE და CLICKUP პარამეტრები
QASE_API_TOKEN = "dd203d20ea7992c881633c69c093d0509997d86687fd317141fcfaba9bc5d71c"
PROJECT_CODE = "DRESSUP"
CLICKUP_TOKEN = "pk_188468937_C74O5LJ8IMKNHTPMTC5QAHGGKW3U9I6Z"
CLICKUP_LIST_ID_DRESSUP = "901807146872"
CLICKUP_DEFAULT_STATUS = "to do"

qase_headers = {
    "Token": QASE_API_TOKEN,
    "Content-Type": "application/json"
}
clickup_headers = {
    "Authorization": CLICKUP_TOKEN,
    "Content-Type": "application/json"
}

# 🔹 მთავარი გვერდი ღილაკით
@app.route("/")
def home():
    return """
    <html>
    <head><title>Qase ➜ ClickUp დეფექტების გადატანა</title></head>
    <body style=\"font-family:sans-serif; padding:30px;\">
        <h2>Qase ➜ ClickUp დეფექტების გადამტანი</h2>
        <p>გადაიტანე ყველა დაფეილდებული ტესტ ქეისი ClickUp-ში</p>
        <a href=\"/send_defects\">
            <button style=\"padding:10px 20px; font-size:16px;\">გადაიტანე დეფექტები</button>
        </a>
    </body>
    </html>
    """

# 🔹 მხოლოდ Defect-ების გადატანა
@app.route('/send_defects', methods=['GET'])
def send_defects():
    url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=100"
    response = requests.get(url, headers=qase_headers)

    if response.status_code != 200:
        return jsonify({"status": "error", "message": "Qase API run endpoint error."}), 500

    runs = response.json().get("result", {}).get("entities", [])
    if not runs:
        return jsonify({"status": "ok", "message": "გაშვებული ტესტები არ მოიძებნა."}), 200

    created = 0
    for run in runs:
        for result in run.get("cases", []):
            if result.get("status") != "failed":
                continue

            case_id = result.get("case_id")
            if not case_id:
                continue

            # ტესტ ქეისის დეტალების ამოღება
            case_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
            case_response = requests.get(case_url, headers=qase_headers)
            if case_response.status_code != 200:
                continue

            case_data = case_response.json().get("result", {})

            title = case_data.get("title", "Untitled Test Case")
            description = result.get("actual_result", "No description.")
            steps = case_data.get("steps", [])
            device_text = case_data.get("description", "")

            steps_output = ["\n\nნაბიჯები:"]
            for i, s in enumerate(steps):
                action = s.get("action", "")
                expected = s.get("expected_result", "")
                steps_output.append(f"{i+1}. {action} ➜ {expected}")
            steps_text = "\n".join(steps_output)

            severity = result.get("severity", "Medium")
            priority_map = {
                "Critical": 1,
                "High": 2,
                "Medium": 3,
                "Low": 4
            }
            priority_value = priority_map.get(severity, 3)

            assignee_name = result.get("assignee", {}).get("full_name", "Maia Khalvashi")

            content = f"""მოწყობილობა:
{device_text}

ტესტერი: {assignee_name}
Severity: {severity}
Priority: {"Urgent" if priority_value == 1 else severity}
{steps_text}

მიმდინარე შედეგი:
{description}

მოსალოდნელი შედეგი:
[აქ ჩაწერე მოსალოდნელი შედეგი]

დამატებითი ფოტო/ვიდეო მასალა:
[აქ ჩასვი საჭირო მტკიცებულებები]
"""

            payload = {
                "name": f"[დეფექტი] {title}",
                "content": content,
                "status": CLICKUP_DEFAULT_STATUS,
                "assignees": [188468937],
                "priority": priority_value
            }

            res = requests.post(
                f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID_DRESSUP}/task",
                headers=clickup_headers,
                json=payload
            )

            if res.status_code in [200, 201]:
                created += 1

    სიტყვა = "დეფექტი" if created == 1 else "დეფექტი"
    return Response(
        json.dumps({"status": "ok", "message": f"{created} {სიტყვა} გადავიდა ClickUp-ში."}, ensure_ascii=False),
        content_type="application/json"
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)