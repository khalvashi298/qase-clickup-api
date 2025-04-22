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

# თუ ტოკენები არაა გამოსახული, დიდი პრობლემა გვაქვს
if not QASE_API_TOKEN or not CLICKUP_TOKEN:
    logger.error("QASE_API_TOKEN ან CLICKUP_TOKEN გარემო ცვლადებად არ არის განსაზღვრული.")
    raise RuntimeError("გთხოვთ დააყენოთ QASE_API_TOKEN და CLICKUP_TOKEN.")

qase_headers   = {"Token": QASE_API_TOKEN, "Content-Type": "application/json"}
clickup_headers = {"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"}

# ========================
#  ფუნქციები Qase API-თან
# ========================
def get_latest_run_id():
    """ბირქმევა პროექტის ბოლო Test Run-ის ID"""
    url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=1"
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    runs = resp.json().get("result", {}).get("entities", [])
    
    # დამატებითი ლოგირება
    logger.info(f"მიღებული რანები: {len(runs)}")
    if runs:
        logger.info(f"ბოლო რანის ID: {runs[0]['id']}")
    
    return runs[0]["id"] if runs else None

def get_failed_results(run_id):
    """ბირქმევა ყველა провалებული შედეგი მოცემული Run ID-სთვის"""
    all_failed = []
    offset = 0
    limit = 100
    
    while True:
        url = (
            f"https://api.qase.io/v1/result/{PROJECT_CODE}"
            f"?run={run_id}&status=failed&limit={limit}&offset={offset}"
        )
        logger.info(f"მოთხოვნა failed შედეგებზე: {url}")
        
        resp = requests.get(url, headers=qase_headers)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            if resp.status_code == 404:
                # თუ 404-ია, უბრალოდ ცარიელ სიას ვუყურებთ
                logger.warning(f"No results for run {run_id}, returning empty list.")
                return []
            logger.error(f"HTTP შეცდომა შედეგების მიღებისას: {resp.status_code}, {resp.text}")
            raise
        
        results = resp.json().get("result", {})
        entities = results.get("entities", [])
        
        # დამატებული ლოგირება შედეგების რაოდენობაზე
        logger.info(f"მიღებულია {len(entities)} failed შედეგი, offset={offset}")
        
        all_failed.extend(entities)
        
        # შევამოწმოთ თუ ეს ბოლო გვერდი იყო
        total = results.get("total", 0)
        if len(all_failed) >= total or len(entities) < limit:
            break
            
        offset += limit
    
    # დამატებული ლოგირება ჯამური შედეგებისთვის
    logger.info(f"სულ მიღებულია {len(all_failed)} failed შედეგი")
    
    # დამატებული ლოგირება თითოეული შედეგის ტიპისთვის
    for i, result in enumerate(all_failed):
        case_id = result.get("case_id")
        logger.info(f"Failed შედეგი #{i+1}: case_id={case_id}")
    
    return all_failed

def get_case_details(case_id):
    """ბირქმევა კონკრეტული Test Case-ის სრული ინფორმაცია"""
    url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
    logger.info(f"მოთხოვნა კეისის დეტალებზე: {url}")
    
    resp = requests.get(url, headers=qase_headers)
    resp.raise_for_status()
    
    case = resp.json().get("result", {})
    logger.info(f"მიღებულია კეისი {case_id}: {case.get('title', 'უსათაურო')}")
    
    return case

# ========================
#  Route-ები
# ========================
@app.route("/", methods=["GET"])
def home():
    # მისამართი მოთამაშეს პირდაპირ გადამისამართებს /send_failed-ზე
    return redirect(url_for("send_failed_cases"))

@app.route("/send_testcases", methods=["GET"])
def alias_send():
    # რჩება backward compatibility
    return redirect(url_for("send_failed_cases"))

@app.route("/send_failed", methods=["GET"])
def send_failed_cases():
    try:
        # 1) მივიღოთ ბოლო Run ID
        run_id = get_latest_run_id()
        if not run_id:
            return jsonify(status="error", message="პროექტში ტესტი‑რანები არ არის."), 404

        # 2) მივიღოთ მხოლოდ провалებული შედეგები
        failed = get_failed_results(run_id)
        if not failed:
            return jsonify(status="ok", message="წარუმატებელი ტესტ‑ქეისები არ არის."), 200

        logger.info(f"დასამუშავებელია {len(failed)} წარუმატებელი შედეგი")
        
        created = 0
        failed_to_create = 0
        
        # 3) თითო провალებული შედეგი გადავამუშავოთ
        for res in failed:
            try:
                case_id = res["case_id"]
                logger.info(f"ვამუშავებთ case_id {case_id}")
                
                case    = get_case_details(case_id)
                title   = (case.get("title") or "Untitled").strip()
                desc    = (case.get("description") or "").strip()
                comment = (res.get("comment") or "[კომენტარი]").strip()
                
                logger.info(f"დამუშავება: {title}")

                steps = case.get("steps", [])
                # 4) დავამზადოთ ნაბიჯების სიები
                lines = ["📝 ნაბიჯები:"]
                for i, step in enumerate(steps, start=1):
                    act = (step.get("action") or "").strip()
                    exp = (step.get("expected_result") or "").strip()
                    lines.append(f"{i}. {act}\n   📌 მოსალოდნელი: {exp}")

                # 5) დავამატოთ აღწერა, ნაბიჯები, მიმდინარე და მოსალოდნელი შედეგები
                content = (
                    f"{desc}\n\n"
                    + "\n".join(lines)
                    + f"\n\n🚨 მიმდინარე შედეგი:\n{comment}\n"
                    + "✅ მოსალოდნელი შედეგი:\n[შეიყვანეთ მოსალოდნელი შედეგი აქ]"
                )

                # 6) დავაგზავნოთ ClickUp-ში
                payload = {
                    "name": f"[FAILED] {title}",
                    "content": content,
                    "status": CLICKUP_STATUS
                }
                
                logger.info(f"ClickUp API გაგზავნა დავალებისთვის: {title}")
                resp = requests.post(
                    f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task",
                    headers=clickup_headers,
                    json=payload
                )
                
                if resp.status_code in (200, 201):
                    task_id = resp.json().get('id', 'unknown')
                    logger.info(f"შეიქმნა ClickUp დავალება ID={task_id}: {title}")
                    created += 1
                else:
                    logger.error(f"ClickUp შეცდომა ({resp.status_code}): {resp.text}")
                    failed_to_create += 1
                    
            except Exception as e:
                logger.exception(f"შეცდომა მოხდა case_id {res.get('case_id')} დამუშავებისას")
                failed_to_create += 1

        return jsonify(
            status="ok", 
            message=f"{created} დავალება(ებ) შექმნილია ClickUp-ში. {failed_to_create} ვერ შეიქმნა.",
            created=created,
            failed=failed_to_create
        ), 200

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
    app.run(host="0.0.0.0", port=port, debug=True)