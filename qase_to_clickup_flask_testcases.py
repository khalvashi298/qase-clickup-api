import os
from flask import Flask, jsonify, Response
import requests
import json
import logging

# ლოგების გასამართად
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

@app.route('/')
def home():
    return """
    <html>
    <head><title>Qase ➔ ClickUp</title></head>
    <body style="font-family:sans-serif; padding:30px;">
        <h2>Qase ➔ ClickUp გადამტანი</h2>
        <p>გადაიტანე დაფეილებული ტესტ ქეისები ClickUp-ში</p>
        <a href="/send_testcases">
            <button style="padding:10px 20px; font-size:16px;">გადაიტანე ტესტ ქეისები</button>
        </a>
    </body>
    </html>
    """

@app.route('/send_testcases', methods=['GET'])
def send_testcases():
    runs_url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=10"
    runs_response = requests.get(runs_url, headers=qase_headers)

    if runs_response.status_code != 200:
        return jsonify({"status": "error", "message": "ვერ მოიძებნა ტესტ რანები"}), 500

    runs = runs_response.json().get("result", {}).get("entities", [])
    if not runs:
        return jsonify({"status": "ok", "message": "არ მოიძებნა ტესტ რანები"}), 200

    created = 0
    for run in runs:
        run_hash = run.get("hash")
        if not run_hash:
            logger.warning(f"ტესტ რანს არ აქვს hash და გამოტოვებულია: {run.get('title')}")
            continue

        result_url = f"https://api.qase.io/v1/result/{PROJECT_CODE}/{run_hash}?limit=100"
        result_response = requests.get(result_url, headers=qase_headers)
        if result_response.status_code != 200:
            continue

        results = result_response.json().get("result", {}).get("entities", [])
        for result in results:
            if result.get("status") != "failed":
                continue

            case_id = result.get("case_id")
            actual_result = result.get("actual_result", "")
            if not case_id:
                continue

            case_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
            case_response = requests.get(case_url, headers=qase_headers)
            if case_response.status_code != 200:
                continue

            case_data = case_response.json().get("result", {})
            title = case_data.get("title", "უსათაურო")
            description = case_data.get("description", "")
            steps = case_data.get("steps", [])
            severity = result.get("severity", case_data.get("severity", "Medium"))

            steps_output = ["ნაბიჯები:"]
            for i, step in enumerate(steps):
                action = step.get("action", "")
                expected = step.get("expected_result") or ""
                steps_output.append(f"{i+1}. {action} ➔ {expected}")
            steps_text = "\n".join(steps_output)

            priority_map = {
                "Critical": 1,
                "High": 2,
                "Medium": 3,
                "Low": 4
            }
            priority_value = priority_map.get(severity, 3)

            expected_combined = ' '.join([str(step.get("expected_result", "")) for step in steps])

            content = f"""მოწყობილობა:
{description}

{steps_text}

მიმდინარე შედეგი:
{actual_result}

მოსალოდნელი შედეგი:
{expected_combined}

დამატებითი ინფორმაცია:
- ტესტ ქეისი: #{case_id}
- ტესტ რანი: {run.get("title", "")}
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

    if created == 0:
        return jsonify({"status": "ok", "message": "არ მოიძებნა შესაბამისი ტესტ ქეისები ბაგ რეპორტისთვის."})

    სიტყვა = "დეფექტი" if created == 1 else "დეფექტი"
    return Response(
        json.dumps({"status": "ok", "message": f"{created} {სიტყვა} გადავიდა ClickUp-ში."}, ensure_ascii=False),
        content_type="application/json"
    )

@app.route('/force_send', methods=['GET'])
def force_send():
    case_id = 2  # ხელით არჩეული ქეისი

    case_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
    case_response = requests.get(case_url, headers=qase_headers)
    if case_response.status_code != 200:
        return jsonify({"status": "error", "message": f"ვერ მიიღო ტესტ ქეისი {case_id}"}), 500

    case_data = case_response.json().get("result", {})
    title = case_data.get("title", "უსათაურო")
    description = case_data.get("description", "")
    steps = case_data.get("steps", [])

    steps_output = ["ნაბიჯები:"]
    for i, step in enumerate(steps):
        action = step.get("action", "")
        expected = step.get("expected_result") or ""
        steps_output.append(f"{i+1}. {action} ➔ {expected}")
    steps_text = "\n".join(steps_output)

    expected_combined = ' '.join([str(step.get("expected_result", "")) for step in steps])

    content = f"""მოწყობილობა:
{description}

{steps_text}

მიმდინარე შედეგი:
ავტორიზაცია პრობლემა

მოსალოდნელი შედეგი:
{expected_combined}

დამატებითი ინფორმაცია:
- ტესტ ქეისი: #{case_id}
- მხოლოდ ტესტისთვის"""

    payload = {
        "name": f"[დეფექტი] {title}",
        "content": content,
        "status": CLICKUP_DEFAULT_STATUS,
        "assignees": [188468937],
        "priority": 3
    }

    res = requests.post(
        f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID_DRESSUP}/task",
        headers=clickup_headers,
        json=payload
    )

    if res.status_code in [200, 201]:
        return Response(
            json.dumps({"status": "ok", "message": "ტესტ ქეისი გადავიდა ClickUp-ში."}, ensure_ascii=False),
            content_type="application/json"
        )
    else:
        return jsonify({
            "status": "error",
            "message": f"ClickUp-ში გაგზავნის შეცდომა: {res.status_code}",
            "response": res.text
        })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
