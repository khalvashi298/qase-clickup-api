import os
import logging
import json
import traceback
from flask import Flask, jsonify, redirect, url_for, Response
import requests

app = Flask(__name__)

# ========================
#  ლოგირების კონფიგურაცია
# ========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========================
#  პარამეტრები
# ========================
QASE_API_TOKEN = os.getenv(
    "QASE_API_TOKEN",
    "dd203d20ea7992c881633c69c093d0509997d86687fd317141fcfaba9bc5d71c"
)

CLICKUP_TOKEN = os.getenv(
    "CLICKUP_TOKEN",
    "pk_188468937_C74O5LJ8IMKNHTPMTC5QAHGGKW3U9I6Z"
)

PROJECT_CODE    = "DRESSUP"
CLICKUP_LIST_ID = "901807146872"
CLICKUP_STATUS  = "to do"

# რუკა: Qase ავტორი → ClickUp User ID
clickup_user_map = {
    "Maia Khalvashi": 188468937,
    # დაამატეთ საჭიროებისამებრ სხვა იდენტიფიკატორები
}

# რუკა: Qase severity → ClickUp Priority ID
clickup_priority_map = {
    "Critical": 1,
    "High":     2,
    "Medium":   3,
    "Low":      4
}

# თუ ტოკენები არ არის განსაზღვრული, აპლიკაცია შეჩერდეს
if not QASE_API_TOKEN or not CLICKUP_TOKEN:
    logger.error("QASE_API_TOKEN ან CLICKUP_TOKEN არ არის განსაზღვრული")
    raise RuntimeError("გთხოვთ დააყენოთ QASE_API_TOKEN და CLICKUP_TOKEN გარემოს ცვლადებად")

qase_headers    = {"Token": QASE_API_TOKEN, "Content-Type": "application/json"}
clickup_headers = {"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"}

# ========================
#  Qase API ფუნქციები
# ========================
def safe_get(dict_obj, key, default=None):
    if dict_obj is None:
        return default
    return dict_obj.get(key, default)


def get_latest_run_id():
    url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=1"
    try:
        resp = requests.get(url, headers=qase_headers)
        resp.raise_for_status()
        runs = resp.json().get("result", {}).get("entities", [])
        return runs[0].get("id") if runs else None
    except Exception as e:
        logger.exception(f"get_latest_run_id error: {e}")
        return None


def get_failed_results(run_id):
    if run_id is None:
        return []
    url = (
        f"https://api.qase.io/v1/result/{PROJECT_CODE}?run={run_id}&status=failed&limit=100&include=defects"
    )
    try:
        resp = requests.get(url, headers=qase_headers)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("result", {}).get("entities", [])
    except Exception as e:
        logger.exception(f"get_failed_results error: {e}")
        return []


def get_case_details(case_id):
    if case_id is None:
        return {}
    url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
    try:
        resp = requests.get(url, headers=qase_headers)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json().get("result", {})
    except Exception as e:
        logger.exception(f"get_case_details error: {e}")
        return {}

# ========================
#  Route-ები
# ========================
@app.route("/", methods=["GET"])
def home():
    return redirect(url_for("send_failed_cases"))

@app.route("/send_testcases", methods=["GET"])
def alias_send():
    return redirect(url_for("send_failed_cases"))

@app.route("/send_failed", methods=["GET"])
def send_failed_cases():
    try:
        # 1) ვიღებთ ყველა დეფექტს Qase-დან
        url = f"https://api.qase.io/v1/defect/{PROJECT_CODE}"
        resp = requests.get(url, headers=qase_headers)
        resp.raise_for_status()
        defects = resp.json().get("result", {}).get("entities", [])

        created = 0
        skipped = []

        for defect in defects:
            case_id = defect.get("case_id")
            if not case_id:
                continue

            case = get_case_details(case_id)
            title = (case.get("title") or "Untitled").strip()
            desc  = (case.get("description") or "").strip()

            # Assignee + Priority
            qase_author   = safe_get(defect.get("author"), "name", "")
            assignee_id   = clickup_user_map.get(qase_author)
            qase_priority = defect.get("severity", "Low")
            priority_id   = clickup_priority_map.get(qase_priority, clickup_priority_map["Low"])

            # ნაბიჯები მხოლოდ მოქმედებებით
            lines = ["📝 ნაბიჯები:"]
            for i, step in enumerate(case.get("steps", []), start=1):
                act = (step.get("action") or "").strip()
                lines.append(f"{i}. {act}")

            # დეფექტის კომენტარი როგორც მიმდინარე შედეგი
            current = (defect.get("comment") or f"Defect ID: {defect.get('id')}").strip()

            # მოსალოდნელი შედეგი თუ გაქვთ სხვა ველი, ან სტატიკური ტექსტი
            expected = "[შეიყვანეთ მოსალოდნელი შედეგი]"

            # attachments
            attachments  = defect.get("attachments", [])
            attach_lines = [
                f"- [{att.get('filename', att.get('url'))}]({att.get('url')})"
                for att in attachments
            ]

            # შეადგენთ content-ს
            content = (
                f"{desc}\n\n"
                + "\n".join(lines) + "\n\n"
                + f"🚨 მიმდინარე შედეგი:\n{current}\n\n"
                + f"✅ მოსალოდნელი შედეგი:\n{expected}\n\n"
                + "📎 დამატებითი მასალა:\n"
                + ("\n".join(attach_lines) if attach_lines else "[დამატებითი მასალა არ არის]")
            )

            # ClickUp payload
            payload = {
                "name":     f"[DEFECT] {title}",
                "content":  content,
                "status":   CLICKUP_STATUS,
                "priority": priority_id
            }
            if assignee_id:
                payload["assignees"] = [assignee_id]

            r2 = requests.post(
                f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task",
                headers=clickup_headers, json=payload
            )
            if r2.status_code in (200, 201):
                created += 1
            else:
                skipped.append({"case_id": case_id, "error": r2.text})

          return jsonify(
            status="ok",
            message=f"{created} დავალება(ებ) შექმნილია ClickUp-ში.",
            created=created,
            skipped=skipped
        ), 200

    except Exception as e:
        tb = traceback.format_exc()
        logger.exception(f"send_failed_cases error: {e}\n{tb}")
        return jsonify(status="error", message=f"შიდა შეცდომა: {e}"), 500

# აქ უნდა გაიდგეს 0 გვერდზე, არ უნდა იყოს indent–ში!
if __name__ == "__main__":
    # Render აწვდის PORT გარემოს ცვლადში
    port = int(os.environ.get("PORT", 5000))
    # host=0.0.0.0–ზე რომ გარედანაც მიუკვეთონ
    app.run(host="0.0.0.0", port=port, debug=True)
