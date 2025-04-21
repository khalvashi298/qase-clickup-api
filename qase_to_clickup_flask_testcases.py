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

# Header-ები
qase_headers = {
    "Token": QASE_API_TOKEN,
    "Content-Type": "application/json"
}
clickup_headers = {
    "Authorization": CLICKUP_TOKEN,
    "Content-Type": "application/json"
}

# ✅ ეს არის მთავარი გვერდი "/" (ღილაკით)
@app.route("/")
def home():
    return """
    <html>
    <head><title>Qase ➜ ClickUp</title></head>
    <body style=\"font-family:sans-serif; padding:30px;\">
        <h2>Qase ➜ ClickUp გადამტანი</h2>
        <p>გადაიტანე მხოლოდ ჩაჭრილი ტესტ ქეისები ClickUp-ში</p>
        <a href=\"/send_testcases\">
            <button style=\"padding:10px 20px; font-size:16px;\">გადაიტანე ტესტ ქეისები</button>
        </a>
    </body>
    </html>
    """

# ✅ ტესტ ქეისების გადატანა (მხოლოდ ჩაჭრილები)
@app.route('/send_testcases', methods=['GET'])
def send_testcases():
    url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=50"
    response = requests.get(url, headers=qase_headers)

    if response.status_code != 200:
        return jsonify({"status": "error", "message": "Qase API error while retrieving test runs."}), 500

    runs = response.json().get("result", {}).get("entities", [])
    if not runs:
        return jsonify({"status": "ok", "message": "დაფეილდებული ტესტ ქეისები არ მოიძებნა."}), 200

    created = 0
    for run in runs:
        for case_result in run.get("cases", []):
            if case_result.get("status") != "failed":
                continue

            case_id = case_result.get("case_id")
            if not case_id:
                continue

            # ამოიღე ტესტ ქეისის დეტალები
            case_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
            case_response = requests.get(case_url, headers=qase_headers)
            if case_response.status_code != 200:
                continue

            case_data = case_response.json().get("result", {})
            title = case_data.get("title", "Untitled Test Case")
            description = case_data.get("description", "No description.")
            steps = case_data.get("steps", [])
            assignee_name = case_result.get("assignee", {}).get("full_name", "Maia Khalvashi")
            severity = case_result.get("severity", "Medium")

            steps_output = ["ნაბიჯები:"]
            seen_links = set()
            for i, s in enumerate(steps):
                action = s.get("action") or ""
                urls = re.findall(r'https?://\S+', action)
                for url in urls:
                    if url in seen_links:
                        action = action.replace(url, "")
                    else:
                        seen_links.add(url)
                steps_output.append(f"{i+1}. {action.strip()}")

            steps_text = "\n".join(steps_output)
            expected_text = "\n".join([
                f"{str(s.get('expected_result') or '')}" for s in steps
            ]) if steps else ""

            priority_map = {
                "Critical": 1,
                "High": 2,
                "Medium": 3,
                "Low": 4
            }
            priority_value = priority_map.get(severity, 3)

            content = f"""{description}\n\n{steps_text}\n\nმიმდინარე შედეგი: \n\n{expected_text}\n\nმოსალოდნელი შედეგი: \n\n[აქ ჩაწერე მოსალოდნელი შედეგი]"""

            payload = {
                "name": f"[TEST CASE] {title}",
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

    სიტყვა = "ბაგ-რეპორტი" if created == 1 else "ბაგ-რეპორტი"
    return Response(
        json.dumps({"status": "ok", "message": f"{created} {სიტყვა} გადავიდა ClickUp-ში."}, ensure_ascii=False),
        content_type="application/json"
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # ეს იწვევს Render-ის მიერ მიცემულ პორტზე გაშვებას
    app.run(host="0.0.0.0", port=port)
