import os
import logging
from flask import Flask, jsonify, Response
import requests

app = Flask(__name__)

# ლოგირების კონფიგურაცია
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# პარამეტრები
- QASE_API_TOKEN   = os.getenv("dd203d20ea7992c881633c69c093d0509997d86687fd317141fcfaba9bc5d71c")
+ QASE_API_TOKEN   = os.getenv("QASE_API_TOKEN", "dd203d20ea7992c881633c69c093d0509997d86687fd317141fcfaba9bc5d71c")PROJECT_CODE     = "DRESSUP"
- CLICKUP_TOKEN    = os.getenv("pk_188468937_C74O5LJ8IMKNHTPMTC5QAHGGKW3U9I6Z")
+ CLICKUP_TOKEN    = os.getenv("CLICKUP_TOKEN", "pk_188468937_C74O5LJ8IMKNHTPMTC5QAHGGKW3U9I6Z")
    CLICKUP_LIST_ID  = "901807146872"
    CLICKUP_STATUS   = "to do"

# დაბიოგინეთ, თუ ცვლადები არ არის
if not QASE_API_TOKEN or not CLICKUP_TOKEN:
    logger.error("მონაცემთა ცვლადები არ არის განსაზღვრული: QASE_API_TOKEN და CLICKUP_TOKEN")
    # აპლიკაცია არ უნდა აგრძელებდეს სტარტს უშეცდომოდ
    raise RuntimeError("გთხოვთ დააყენოთ QASE_API_TOKEN და CLICKUP_TOKEN გარემოს ცვლადებად")

qase_headers = {"Token": QASE_API_TOKEN, "Content-Type": "application/json"}
clickup_headers = {"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"}

def get_latest_run_id():
    url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=1"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    runs = resp.json().get("result", {}).get("entities", [])
    return runs[0]["id"] if runs else None

def get_failed_results(run_id):
    url = f"https://api.qase.io/v1/result/{PROJECT_CODE}/{run_id}?status=failed&limit=100"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    return resp.json().get("result", {}).get("entities", [])

def get_case_details(case_id):
    url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    return resp.json().get("result", {})

@app.route("/send_failed", methods=["GET"])
def send_failed_cases():
    try:
        run_id = get_latest_run_id()
        if not run_id:
            return jsonify(status="error", message="პროექტში ტესტი‑რანები არ არის."), 404

        failed = get_failed_results(run_id)
        if not failed:
            return jsonify(status="ok", message="წარუმატებელი ტესტ‑ქეისები არაა."), 200

        created = 0
        for res in failed:
            case = get_case_details(res["case_id"])
            title = case.get("title", "Untitled")
            desc  = case.get("description", "")
            steps = case.get("steps", [])

            # ავაშენოთ ტექსტი
            lines = ["📝 ნაბიჯები:"]
            for i, step in enumerate(steps, start=1):
                act = step.get("action","").strip()
                exp = step.get("expected_result","").strip()
                lines.append(f"{i}. {act}\n   📌 მოსალოდნელი: {exp}")

            content = (
                f"{desc}\n\n" + "\n".join(lines) +
                f"\n\n🚨 მიმდინარე შედეგი:\n{res.get('comment','[კომენტარი]')}\n"
                "✅ მოსალოდნელი შედეგი:\n[შეიყვანე მოსალოდნელი შედეგი]"
            )
            payload = {"name": f"[FAILED] {title}", "content": content, "status": CLICKUP_STATUS}

            resp = requests.post(
                f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task",
                headers=clickup_headers, json=payload
            )
            # თუ ClickUp–მა მოიღო
            if resp.status_code in (200,201):
                created += 1
            else:
                # Debugging output, თუ აუცილებელია
                logger.error(f"ClickUp error ({resp.status_code}): {resp.text}")

        return jsonify(status="ok", message=f"{created} დავალება(ებ) გაიგზავნა ClickUp-ში."), 200

    except requests.HTTPError as he:
        # თუ API დაფილდ აავტორმერია
        logger.exception("HTTP მოთხოვნის შეცდომა")
        return jsonify(status="error", message=f"HTTP შეცდომა: {he}"), 500
    except Exception as e:
        # ნებისმიერი სხვა არაააპურად ხელმოსაჭერი შეცდომა
        logger.exception("უცნობი შეცდომა send_failed_cases()-ში")
        return jsonify(status="error", message=f"შიდა შეცდომა: {e}"), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
