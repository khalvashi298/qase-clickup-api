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

# ClickUp-ის User ID და პრიორიტეტების რუკები
clickup_user_map = {
    "Maia Khalvashi": 188468937,
    # დაამატეთ სხვა ტესტერის სახელი და ID, თუ გჭირდებათ
}

clickup_priority_map = {
    "Critical": 1,
    "High":     2,
    "Medium":   3,
    "Low":      4
}

# თუ ტოკენები არ არის განსაზღვრული, დიდი პრობლემა გვაქვს
if not QASE_API_TOKEN or not CLICKUP_TOKEN:
    logger.error("QASE_API_TOKEN ან CLICKUP_TOKEN გარემო ცვლადებად არ არის განსაზღვრული.")
    raise RuntimeError("გთხოვთ დააყენოთ QASE_API_TOKEN და CLICKUP_TOKEN.")

qase_headers    = {"Token": QASE_API_TOKEN, "Content-Type": "application/json"}
clickup_headers = {"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"}

# ========================
#  ფუნქციები Qase API-თან
# ========================
def safe_get(dict_obj, key, default=None):
    """უსაფრთხოდ წამოიღე მნიშვნელობა ლექსიკონიდან"""
    if dict_obj is None:
        return default
    return dict_obj.get(key, default)


def get_latest_run_id():
    url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=1"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    runs = resp.json().get("result", {}).get("entities", [])
    return runs[0].get("id") if runs else None


def get_failed_results(run_id):
    url = (
        f"https://api.qase.io/v1/result/{PROJECT_CODE}?run={run_id}&status=failed&limit=100&include=defects"
    )
    resp = requests.get(url, headers=qase_headers)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json().get("result", {}).get("entities", [])


def get_case_details(case_id):
    url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    return resp.json().get("result", {})

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
        run_id = get_latest_run_id()
        if not run_id:
            return jsonify(status="error", message="პროექტში ტესტი‑რანები არ არის."), 404

        failed = get_failed_results(run_id)
        # ფილტრაცია: მხოლოდ კონტროლი, რომ defects არ იყოს ცარიელი
        failed = [r for r in failed if r.get("defects")]
        if not failed:
            return jsonify(status="ok", message="დაფეილებული ტესტ‑ქეისები არ არის."), 200

        created = 0
        skipped = []

        for res in failed:
            case_id = res.get("case_id")
            case    = get_case_details(case_id)
            title   = (case.get("title") or "Untitled").strip()
            desc    = (case.get("description") or "").strip()

            # 1) assignee და priority
            qase_author   = safe_get(res.get("author"), "name", "")
            assignee_id   = clickup_user_map.get(qase_author)
            qase_priority = res.get("severity", "Low")
            priority_id   = clickup_priority_map.get(qase_priority, clickup_priority_map["Low"])

            # 2) ნაბიჯები მხოლოდ მოქმედებებით
            lines = []
            for i, step in enumerate(case.get("steps", []), start=1):
                act = (step.get("action") or "").strip()
                lines.append(f"{i}. {act}")

            # 3) მიმდინარე და მოსალოდნელი შედეგები
            current  = (res.get("comment") or "[კომენტარი]").strip()
            expected = (res.get("actual_result") or "[მოსალოდნელი]").strip()

            # 4) attachments
            attachments  = res.get("attachments", [])
            attach_lines = [
                f"- [{att.get('filename', att.get('url'))}]({att.get('url')})"
                for att in attachments
            ]

            # საბოლოო content
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
                "name":     f"[FAILED] {title}",
                "content":  content,
                "status":   CLICKUP_STATUS,
                "priority": priority_id
            }
            if assignee_id:
                payload["assignees"] = [assignee_id]

            resp = requests.post(
                f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task",
                headers=clickup_headers,
                json=payload
            )
            if resp.status_code in (200, 201):
                created += 1
            else:
                skipped.append({"case_id": case_id, "error": resp.text})

        return jsonify(
            status="ok",
            message=f"{created} დავალება(ებ) შექმნილია ClickUp-ში.",
            created=created,
            skipped=skipped
        ), 200

    except Exception as e:
        tb = traceback.format_exc()
        logger.exception(f"უცნობი შეცდომა send_failed_cases()-ში: {e}\n{tb}")
        return jsonify(status="error", message=f"შიდა შეცდომა: {str(e)}"), 500

# ========================
#  Entry point
# ========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
