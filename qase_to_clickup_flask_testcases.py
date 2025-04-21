import os
from flask import Flask, jsonify, Response
import requests
import json

app = Flask(__name__)

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

@app.route("/")
def home():
    return """
    <html>
    <head><title>Qase ➔ ClickUp</title></head>
    <body style=\"font-family:sans-serif; padding:30px;\">
        <h2>Qase ➔ ClickUp გადამტანი</h2>
        <p>გადაიტანე მხოლოდ ჩაჭრილი ტესტ ქეისები ClickUp-ში</p>
        <a href=\"/send_testcases\">
            <button style=\"padding:10px 20px; font-size:16px;\">გადაიტანე ტესტ ქეისები</button>
        </a>
    </body>
    </html>
    """

@app.route('/send_testcases', methods=['GET'])
def send_testcases():
    # 1. მიიღე ბოლო ტესტ რანები
    runs_url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=10"
    runs_response = requests.get(runs_url, headers=qase_headers)

    if runs_response.status_code != 200:
        return jsonify({"status": "error", "message": "Can't fetch test runs."}), 500

    runs = runs_response.json().get("result", {}).get("entities", [])
    if not runs:
        return jsonify({"status": "ok", "message": "No test runs found."}), 200

    created = 0

    for run in runs:
        run_id = run.get("id")  # Use run ID instead of hash
        if not run_id:
            continue

        # 2. თითოეული რანის შედეგები (მხოლოდ failed ტესტ ქეისები)
        result_url = f"https://api.qase.io/v1/result/{PROJECT_CODE}/{run_id}?limit=100"
        result_response = requests.get(result_url, headers=qase_headers)
        if result_response.status_code != 200:
            continue

        cases = result_response.json().get("result", {}).get("entities", [])

        for case_result in cases:
            if case_result.get("status") != "failed":
                continue

            case_id = case_result.get("case_id")
            actual_result = case_result.get("actual_result", "")
            severity = case_result.get("severity", "Medium")

            # 3. ამოიღე ქეისის დეტალები
            case_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
            case_response = requests.get(case_url, headers=qase_headers)
            if case_response.status_code != 200:
                continue

            case_data = case_response.json().get("result", {})
            title = case_data.get("title", "Untitled")
            description = case_data.get("description", "")
            steps = case_data.get("steps", [])

            steps_output = ["ნაბიჯები:"]
            for i, step in enumerate(steps):
                action = step.get("action", "")
                expected = step.get("expected_result", "")
                steps_output.append(f"{i+1}. {action} ➔ {expected}")
            steps_text = "\n".join(steps_output)

            priority_map = {
                "Critical": 1,
                "High": 2,
                "Medium": 3,
                "Low": 4
            }
            priority_value = priority_map.get(severity, 3)

            content = f"""მოწყობილობა:
{description}

{steps_text}

მიმდინარე შედეგი:
{actual_result}

მოსალოდნელი შედეგი:
[აქ ჩაწერე მოსალოდნელი შედეგი]

დამატებითი მასალა:
[აქ ჩასვი საჭირო მტკიცებულებები]"""

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
