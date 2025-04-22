import os
import logging
from flask import Flask, jsonify, redirect, url_for, Response
import requests

app = Flask(__name__)

# ========================
#  ლოგირების კონფიგურაცია
# ========================
logging.basicConfig(level=logging.INFO)
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

if not QASE_API_TOKEN or not CLICKUP_TOKEN:
    logger.error("QASE_API_TOKEN ან CLICKUP_TOKEN არ არის განსაზღვრული.")
    raise RuntimeError("გთხოვთ დააყენოთ გარემოს ცვლადებად QASE_API_TOKEN და CLICKUP_TOKEN")

qase_headers    = {"Token": QASE_API_TOKEN, "Content-Type": "application/json"}
clickup_headers = {"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"}

# ========================
#  Qase API ფუნქციები
# ========================
def get_latest_run_id():
    """ბირქმევა პროექტის ბოლო Test Run-ის ID"""
    url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=1"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    runs = resp.json().get("result", {}).get("entities", [])
    return runs[0]["id"] if runs else None

def get_failed_results(run_id):
    """
    ბირქმევა ყველა провалებული შედეგი მოცემული Run ID-სთვის.
    შემდეგ შეგვიძლია გავფილტროთ მხოლოდ r["defects"]-ის მქონე ობიექტები.
    """
    url = (
        f"https://api.qase.io/v1/result/{PROJECT_CODE}"
        f"?run={run_id}&status=failed&limit=100"
    )
    resp = requests.get(url, headers=qase_headers)
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        if resp.status_code == 404:
            logger.warning(f"No results for run {run_id}, returning empty list.")
            return []
        raise
    return resp.json().get("result", {}).get("entities", [])

def get_case_details(case_id):
    """ტესტ‑ქეისის სრული დეტალების გამოძახება ID–ით"""
    url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    return resp.json().get("result", {})

# ========================
#  Route-ები
# ========================
@app.route("/", methods=["GET"])
def home():
    # ძირითადი გადასამისამართებელია send_failed-ზე
    return redirect(url_for("send_failed_cases"))

@app.route("/send_testcases", methods=["GET"])
def alias_send():
    # backward compatibility
    return redirect(url_for("send_failed_cases"))

@app.route("/send_failed", methods=["GET"])
def send_failed_cases():
    """
    1) ვიღებთ ბოლო რანის ID-ს
    2) ვიღებთ ყველა failed result-ს
    3) ფილტრავთ მხოლოდ result-ებს, რომლებსაც აქვთ defects (defect-ები დაფიქსირებული)
    4) თითო case_id-ზე ვიღებთ დეტალებს და აგზავნით ClickUp-ში
    """
    try:
        run_id = get_latest_run_id()
        if not run_id:
            return jsonify(status="error", message="პროექტში ტესტი‑რანები არ არის."), 404

        failed = get_failed_results(run_id)
        # 3) ფილტრაცია: მხოლოდ მათთვის, სადაც result["defects"] არ არის ცარიელი
        failed_with_defect = [r for r in failed if r.get("defects")]
        if not failed_with_defect:
            return jsonify(status="ok", message="დეფექტის გარეშე ფეილი არ არის."), 200

        created = 0
        for res in failed_with_defect:
            case    = get_case_details(res["case_id"])
            title   = (case.get("title") or "Untitled").strip()
            desc    = (case.get("description") or "").strip()
            # თუ result-ში უშუალო კომენტარი არაა, ვაჩვენებთ defect ID-ს
            comment = (res.get("comment") or f"Defects: {res.get('defects')}").strip()

            steps = case.get("steps", [])
            lines = ["📝 ნაბიჯები:"]
            for i, step in enumerate(steps, start=1):
                act = (step.get("action") or "").strip()
                exp = (step.get("expected_result") or "").strip()
                lines.append(f"{i}. {act}\n   📌 მოსალოდნელი: {exp}")

            content = (
                f"{desc}\n\n"
                + "\n".join(lines)
                + f"\n\n🚨 მიმდინარე შედეგი:\n{comment}\n"
                + "✅ მოსალოდნელი შედეგი:\n[შეიყვანეთ მოსალოდნელი შედეგი აქ]"
            )

            payload = {
                "name": f"[FAILED] {title}",
                "content": content,
                "status": CLICKUP_STATUS
            }
            resp = requests.post(
                f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task",
                headers=clickup_headers,
                json=payload
            )
            if resp.status_code in (200, 201):
                created += 1
            else:
                logger.error(f"ClickUp error ({resp.status_code}): {resp.text}")

        return jsonify(status="ok", message=f"{created} დავალება(ებ) შექმნილია ClickUp-ში."), 200

    except requests.HTTPError as he:
        logger.exception("HTTP მოთხოვნის შეცდომა")
        return jsonify(status="error", message=f"HTTP შეცდომა: {he}"), 500
    except Exception as e:
        logger.exception("უცნობი შეცდომა send_failed_cases()-ში")
        return jsonify(status="error", message=f"შიდა შეცდომა: {e}"), 500

# ========================
#  Entry point
# ========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
