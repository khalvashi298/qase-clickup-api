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

# ===================================
#   ფუნქციები Qase API დეფექტებისთვის
# ===================================
def get_defects():
    """
    ვიღებთ ყველა Defect-ს პროექტში Qase–დან.
    თუ გინდა მხოლოდ Open ან Specific Status, დაამატე ?status=[0] ან სხვა.
    """
    url = f"https://api.qase.io/v1/defect/{PROJECT_CODE}"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
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
    # მაჩვენებს HTML ღილაკს ან პირდაპირ გადამისამართებს
    return redirect(url_for("send_defected_cases"))

@app.route("/send_testcases", methods=["GET"])
def alias_send():
    return redirect(url_for("send_defected_cases"))

@app.route("/send_defected", methods=["GET"])
def send_defected_cases():
    """
    გამოვიძახოთ Qase დეფექტები, შემდეგ თითო დეფექტისთვის:
     - გამოვიღოთ case_id
     - ავიღოთ ტესტ‑ქეისის დეტალები
     - დავამუშავოთ და გავაგზავნოთ ClickUp–ში
    """
    try:
        defects = get_defects()
        if not defects:
            return jsonify(status="ok", message="დეფექტები არ არის."), 200

        created = 0
        for defect in defects:
            case_id = defect.get("case_id")
            if not case_id:
                continue

            case    = get_case_details(case_id)
            title   = (case.get("title") or "Untitled").strip()
            desc    = (case.get("description") or "").strip()
            comment = (defect.get("comment") or "[კომენტარი]").strip()

            steps = case.get("steps", [])
            lines = ["📝 ნაბიჯები:"]
            for i, step in enumerate(steps, start=1):
                act = (step.get("action") or "").strip()
                exp = (step.get("expected_result") or "").strip()
                lines.append(f"{i}. {act}\n   📌 მოსალოდნელი: {exp}")

            content = (
                f"{desc}\n\n"
                + "\n".join(lines)
                + f"\n\n🚨 დეფექტის კომენტარი:\n{comment}\n"
                + "✅ სასურველი მოსალოდნელი შედეგი:\n[შეიყვანეთ]"
            )

            payload = {
                "name": f"[DEFECT] {title}",
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
        logger.exception("უცნობი შეცდომა send_defected_cases()-ში")
        return jsonify(status="error", message=f"შიდა შეცდომა: {e}"), 500

# ========================
#  Entry point
# ========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
