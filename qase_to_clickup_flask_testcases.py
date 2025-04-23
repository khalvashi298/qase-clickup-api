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

# თუ ტოკენები არაა გამოსახული, დიდი პრობლემა გვაქვს
if not QASE_API_TOKEN or not CLICKUP_TOKEN:
    logger.error("QASE_API_TOKEN ან CLICKUP_TOKEN გარემო ცვლადებად არ არის განსაზღვრული.")
    raise RuntimeError("გთხოვთ დააყენოთ QASE_API_TOKEN და CLICKUP_TOKEN.")

qase_headers   = {"Token": QASE_API_TOKEN, "Content-Type": "application/json"}
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
    """ბირქმევა პროექტის ბოლო Test Run-ის ID"""
    url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=1"
    logger.info(f"მოთხოვნა ბოლო რანებზე: {url}")
    
    try:
        resp = requests.get(url, headers=qase_headers)
        resp.raise_for_status()
        data = resp.json()
        
        runs = safe_get(safe_get(data, "result"), "entities", [])
        
        # დამატებითი ლოგირება
        logger.info(f"მიღებული რანები: {len(runs)}")
        if runs:
            logger.info(f"ბოლო რანის ID: {runs[0].get('id')}")
            return runs[0].get('id')
        return None
    except Exception as e:
        logger.exception(f"შეცდომა get_latest_run_id-ში: {str(e)}")
        return None

def get_failed_results(run_id):
    """ბირქმევა ყველა провалებული შედეგი მოცემული Run ID-სთვის"""
    if run_id is None:
        logger.error("run_id არის None get_failed_results-ში")
        return []
        
    all_failed = []
    offset = 0
    limit = 100
    
    try:
        while True:
            url = (
                f"https://api.qase.io/v1/result/{PROJECT_CODE}"
                f"?run={run_id}&status=failed&limit={limit}&offset={offset}"
            )
            logger.info(f"მოთხოვნა failed შედეგებზე: {url}")
            
            resp = requests.get(url, headers=qase_headers)
            
            if resp.status_code == 404:
                logger.warning(f"No results for run {run_id}, returning empty list.")
                return []
                
            resp.raise_for_status()
            
            data = resp.json()
            logger.info(f"მიღებული პასუხი failed შედეგებზე: {json.dumps(data, indent=2, ensure_ascii=False)}")
            
            results = safe_get(data, "result", {})
            entities = safe_get(results, "entities", [])
            
            # დამატებული ლოგირება შედეგების რაოდენობაზე
            logger.info(f"მიღებულია {len(entities)} failed შედეგი, offset={offset}")
            
            all_failed.extend(entities)
            
            # შევამოწმოთ თუ ეს ბოლო გვერდი იყო
            total = safe_get(results, "total", 0)
            if len(all_failed) >= total or len(entities) < limit:
                break
                
            offset += limit
    except Exception as e:
        logger.exception(f"შეცდომა get_failed_results-ში: {str(e)}")
        return []
    
    # დამატებული ლოგირება ჯამური შედეგებისთვის
    logger.info(f"სულ მიღებულია {len(all_failed)} failed შედეგი")
    
    # ყველა შედეგისთვის შევამოწმოთ აუცილებელი ველები
    valid_results = []
    for result in all_failed:
        if not isinstance(result, dict):
            logger.warning(f"შედეგი არ არის ლექსიკონი: {result}")
            continue
            
        if "case_id" not in result:
            logger.warning(f"შედეგში case_id არ არის: {result}")
            continue
            
        valid_results.append(result)
    
    # დამატებული ლოგირება თითოეული შედეგის ტიპისთვის
    for i, result in enumerate(valid_results):
        case_id = result.get("case_id")
        status = result.get("status")
        comment = result.get("comment", "")
        logger.info(f"Failed შედეგი #{i+1}: case_id={case_id}, status={status}")
        if comment:
            logger.info(f"კომენტარი: {comment[:100]}...")
    
    return valid_results

def get_case_details(case_id):
    """ბირქმევა კონკრეტული Test Case-ის სრული ინფორმაცია"""
    if case_id is None:
        logger.error("case_id არის None get_case_details-ში")
        return {}
        
    url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
    logger.info(f"მოთხოვნა კეისის დეტალებზე: {url}")
    
    try:
        resp = requests.get(url, headers=qase_headers)
        
        if resp.status_code == 404:
            logger.warning(f"კეისი {case_id} არ არსებობს")
            return {}
            
        resp.raise_for_status()
        
        data = resp.json()
        case = safe_get(data, "result", {})
        
        if not case:
            logger.warning(f"კეისი {case_id}-ის დეტალები არ არის მიღებული")
            return {}
            
        logger.info(f"მიღებულია კეისი {case_id}: {case.get('title', 'უსათაურო')}")
        return case
    except Exception as e:
        logger.exception(f"შეცდომა get_case_details-ში: {str(e)}")
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

@app.route("/single_case/<int:case_id>", methods=["GET"])
def process_single_case(case_id):
    """ერთი კონკრეტული კეისის დამუშავება"""
    try:
        logger.info(f"ვამუშავებთ ერთ კონკრეტულ კეისს: {case_id}")
        
        # მივიღოთ კეისის დეტალები
        case = get_case_details(case_id)
        if not case:
            return jsonify(status="error", message=f"კეისი {case_id} ვერ მოიძებნა"), 404
            
        title = (case.get("title") or "Untitled").strip()
        desc = (case.get("description") or "").strip()
        
        # ტესტ პასუხი (რადგან შედეგები არ გვაქვს)
        comment = "[დაფეილებული კეისის კომენტარი]"
        
        steps = case.get("steps", [])
        # დავამზადოთ ნაბიჯების სიები
        lines = ["📝 ნაბიჯები:"]
        for i, step in enumerate(steps, start=1):
            act = (step.get("action") or "").strip()
            exp = (step.get("expected_result") or "").strip()
            lines.append(f"{i}. {act}\n   📌 მოსალოდნელი: {exp}")

        # დავამატოთ აღწერა, ნაბიჯები, მიმდინარე და მოსალოდნელი შედეგები
        content = (
            f"{desc}\n\n"
            + "\n".join(lines)
            + f"\n\n🚨 მიმდინარე შედეგი:\n{comment}\n"
            + "✅ მოსალოდნელი შედეგი:\n[შეიყვანეთ მოსალოდნელი შედეგი აქ]"
        )

        # დავაგზავნოთ ClickUp-ში
        payload = {
            "name": f"[FAILED] {title} (case_id: {case_id})",
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
            response_data = resp.json()
            task_id = response_data.get('id', 'unknown')
            logger.info(f"შეიქმნა ClickUp დავალება ID={task_id}: {title}")
            return jsonify(
                status="ok", 
                message=f"შეიქმნა ClickUp დავალება: {title}",
                task_id=task_id
            ), 200
        else:
            return jsonify(
                status="error", 
                message=f"ClickUp შეცდომა: {resp.status_code} - {resp.text}"
            ), 500
    
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"შეცდომა process_single_case-ში: {str(e)}\n{tb}")
        return jsonify(status="error", message=f"შიდა შეცდომა: {str(e)}"), 500

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
        
        # სიები შექმნილი და გამოტოვებული კეისებისთვის
        created_cases = []
        skipped_cases = []
        
        # 3) თითო провалებული შედეგი გადავამუშავოთ
        for res in failed:
            try:
                case_id = res.get("case_id")
                if case_id is None:
                    logger.warning("შედეგში case_id არ არის")
                    failed_to_create += 1
                    skipped_cases.append({
                        "error": "case_id არ არის შედეგში",
                        "result": res
                    })
                    continue
                    
                logger.info(f"ვამუშავებთ case_id {case_id}")
                
                # მივიღოთ კეისის დეტალები
                case = get_case_details(case_id)
                if not case:
                    logger.warning(f"კეისი {case_id} ვერ მოიძებნა")
                    failed_to_create += 1
                    skipped_cases.append({
                        "case_id": case_id,
                        "error": "კეისის დეტალები ვერ მოიძებნა"
                    })
                    continue
                    
                title = (case.get("title") or "Untitled").strip()
                desc = (case.get("description") or "").strip()
                comment = (res.get("comment") or "[კომენტარი]").strip()
                
                logger.info(f"დამუშავება: {title}")

                steps = case.get("steps", [])
                # 4) დავამზადოთ ნაბიჯების სიები
                lines = ["📝 ნაბიჯები:"]
                for i, step in enumerate(steps, start=1):
                    if not isinstance(step, dict):
                        continue
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
                    "name": f"[FAILED] {title} (case_id: {case_id})",
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
                    response_data = resp.json()
                    task_id = response_data.get('id', 'unknown')
                    logger.info(f"შეიქმნა ClickUp დავალება ID={task_id}: {title}")
                    created += 1
                    created_cases.append({
                        "case_id": case_id,
                        "title": title,
                        "clickup_task_id": task_id
                    })
                else:
                    logger.error(f"ClickUp შეცდომა ({resp.status_code}): {resp.text}")
                    failed_to_create += 1
                    skipped_cases.append({
                        "case_id": case_id,
                        "title": title,
                        "error": f"HTTP {resp.status_code}: {resp.text}"
                    })
                    
            except Exception as e:
                tb = traceback.format_exc()
                logger.exception(f"შეცდომა მოხდა case_id {res.get('case_id')} დამუშავებისას: {e}\n{tb}")
                failed_to_create += 1
                skipped_cases.append({
                    "case_id": res.get('case_id'),
                    "error": str(e)
                })

        return jsonify(
            status="ok", 
            message=f"{created} დავალება(ებ) შექმნილია ClickUp-ში. {failed_to_create} ვერ შეიქმნა.",
            created=created,
            failed=failed_to_create,
            created_cases=created_cases,
            skipped_cases=skipped_cases
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