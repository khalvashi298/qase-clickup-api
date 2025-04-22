import os
from flask import Flask, jsonify, Response
import requests

app = Flask(__name__)

# Qase და ClickUp პარამეტრები
QASE_API_TOKEN   = os.getenv("QASE_API_TOKEN", "თქვენი_QASE_TOKEN")
PROJECT_CODE     = "DRESSUP"
CLICKUP_TOKEN    = os.getenv("CLICKUP_TOKEN", "თქვენი_CLICKUP_TOKEN")
CLICKUP_LIST_ID  = "901807146872"
CLICKUP_STATUS   = "to do"

qase_headers = {
    "Token": QASE_API_TOKEN,
    "Content-Type": "application/json"
}
clickup_headers = {
    "Authorization": CLICKUP_TOKEN,
    "Content-Type": "application/json"
}

def get_latest_run_id():
    """
    იძენს Qase–იდან პროექტის ბოლო ტესტი‑რანის ID–ს
    """
    url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=1"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    runs = resp.json()["result"]["entities"]
    return runs[0]["id"] if runs else None

def get_failed_results(run_id):
    """
    იძენს ყველა провალებულ (failed) შედეგს მოცემული რანისთვის
    """
    url = f"https://api.qase.io/v1/result/{PROJECT_CODE}/{run_id}?status=failed&limit=100"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    return resp.json()["result"]["entities"]

def get_case_details(case_id):
    """
    იძენს ტესტ‑ქეისის სრულ ინფორმაციას ID–ს მიხედვით
    """
    url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    return resp.json()["result"]

@app.route("/send_failed", methods=["GET"])
def send_failed_cases():
    # Qase–დან ბოლო რანის ID
    run_id = get_latest_run_id()
    if not run_id:
        return jsonify({"status":"error","message":"პროექტში ტესტი‑რანები არ არსებობს."}), 404

    # მხოლოდ провალებული (failed) შედეგების მიღება
    failed_results = get_failed_results(run_id)
    if not failed_results:
        return jsonify({"status":"ok","message":"პровალებული ტესტ‑ქეისები არ არის."}), 200

    created = 0
    for result in failed_results:
        case = get_case_details(result["case_id"])

        title       = case.get("title", "Untitled")
        description = case.get("description", "")
        steps       = case.get("steps", [])

        # ნაბიჯების ჩამონათვალი
        steps_lines = ["📝 ვიდეო ნაბიჯები:"]
        for idx, s in enumerate(steps, start=1):
            action = s.get("action", "").strip()
            exp    = s.get("expected_result", "").strip()
            steps_lines.append(f"{idx}. {action}\n   📌 მოსალოდნელი: {exp}")

        # დავალების body
        content = (
            f"{description}\n\n"
            + "\n".join(steps_lines)
            + f"\n\n🚨 მიმდინარე შედეგი:\n{result.get('comment','[კომენტარი ვერ მოიძებნა]')}\n"
            + "✅ მოსალოდნელი შედეგი:\n[შეიყვანე მოსალოდნელი შედეგი აქ]"
        )

        # ClickUp დავალების დატვირთვა
        payload = {
            "name": f"[FAILED] {title}",
            "content": content,
            "status": CLICKUP_STATUS
        }
        resp = requests.post(
            f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task",
            headers=clickup_headers, json=payload
        )
        if resp.status_code in (200, 201):
            created += 1

    # შედეგის შეტყობინება
    msg = f"{created} დავალება(ებ) გადაიტანილია ClickUp-ში."
    return Response(jsonify(status="ok", message=msg).data, mimetype="application/json")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
