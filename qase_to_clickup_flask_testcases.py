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
CLICKUP_USER_ID = 188468937

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
    <head><title>Qase ➞ ClickUp Defect Transfer</title></head>
    <body style="font-family:sans-serif; padding:30px;">
        <h2>Qase ➞ ClickUp Defects Integration</h2>
        <p>გადაიტანე Qase-იდან ClickUp-ში დეფექტები</p>
        <a href="/send_defects">
            <button style="padding:10px 20px; font-size:16px;">გადაიტანე დეფექტები</button>
        </a>
    </body>
    </html>
    """

@app.route('/send_defects', methods=['GET'])
def send_defects():
    url = f"https://api.qase.io/v1/defect/{PROJECT_CODE}?limit=100"
    response = requests.get(url, headers=qase_headers)

    if response.status_code != 200:
        return jsonify({"status": "error", "message": "Qase API defect endpoint error."}), 500

    defects = response.json().get("result", {}).get("entities", [])
    if not defects:
        return jsonify({"status": "ok", "message": "დეფექტები არ მოიძებნა Qase-ში."}), 200

    created = 0
    for d in defects:
        title = d.get("title", "Untitled defect")
        description = d.get("actual_result", "No description.")
        severity = d.get("severity", "low").capitalize()
        case_id = d.get("case_id")

        # Step-ები და მოწყობილობა
        device_text = ""
        steps_text = ""
        if case_id:
            case_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
            case_response = requests.get(case_url, headers=qase_headers)
            if case_response.status_code == 200:
                case_data = case_response.json().get("result", {})
                device_text = case_data.get("description", "").strip()
                steps = case_data.get("steps", [])
                if steps:
                    steps_text = "\n\nნაბიჯები:\n"
                    for i, step in enumerate(steps):
                        action = step.get("action", "")
                        expected = step.get("expected_result", "")
                        steps_text += f"{i+1}. {action} ➜ {expected}\n"

        priority_map = {
            "Critical": 1,
            "High": 2,
            "Medium": 3,
            "Low": 4
        }
        priority_value = priority_map.get(severity, 3)

        content = f"""მოწყობილობა:
{device_text}{steps_text}

მიმდინარე შედეგი:
{description}

მოსალოდნელი შედეგი:
[აქ ჩაცერე მოსალოდნელი შედეგი]

დამატებითი ფოტო/ვიდეო მასალა:
[აქ ჩასვი სასრირო მსამწელი]
"""

        payload = {
            "name": f"[დეფექტი] {title}",
            "content": content,
            "status": CLICKUP_DEFAULT_STATUS,
            "assignees": [CLICKUP_USER_ID],
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
        json.dumps({"status": "ok", "message": f"{created} {სიტყვა} გადაგავიდა ClickUp-ში."}, ensure_ascii=False),
        content_type="application/json"
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
