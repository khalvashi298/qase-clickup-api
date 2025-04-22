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

@app.route("/")
def home():
    return """
    <html>
    <head><title>Qase ➔ ClickUp</title></head>
    <body style=\"font-family:sans-serif; padding:30px;\">
        <h2>Qase ➔ ClickUp გადამტანი</h2>
        <p>გადაიტანე დაფეილებული ტესტ ქეისები ClickUp-ში</p>
        <a href=\"/send_testcases\">
            <button style=\"padding:10px 20px; font-size:16px;\">გადაიტანე ტესტ ქეისები</button>
        </a>
    </body>
    </html>
    """

@app.route('/send_testcases', methods=['GET'])
def send_testcases():
    # ბოლო 10 ტესტ რანის მიღება Qase-დან
    runs_url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=10"
    logger.info(f"მოთხოვნა Qase-ზე: {runs_url}")
    runs_response = requests.get(runs_url, headers=qase_headers)
    
    if runs_response.status_code != 200:
        logger.error(f"ვერ მიიღო ტესტ რანები: {runs_response.text}")
        return jsonify({"status": "error", "message": "ვერ მოიძებნა ტესტ რანები"}), 500

    runs = runs_response.json().get("result", {}).get("entities", [])
    logger.info(f"ნაპოვნია {len(runs)} ტესტ რანი")
    
    if not runs:
        return jsonify({"status": "ok", "message": "არ მოიძებნა ტესტ რანები"}), 200

    created = 0
    for run in runs:
        run_hash = run.get("hash")
        if not run_hash:
            continue

        # ტესტ რანის შედეგების მიღება
        result_url = f"https://api.qase.io/v1/result/{PROJECT_CODE}/{run_hash}?limit=100"
        logger.info(f"მოთხოვნა ტესტის შედეგებზე: {result_url}")
        result_response = requests.get(result_url, headers=qase_headers)
        
        if result_response.status_code != 200:
            logger.warning(f"ვერ მიიღო შედეგები run_hash {run_hash}-სთვის: {result_response.text}")
            continue

        results = result_response.json().get("result", {}).get("entities", [])
        logger.info(f"ნაპოვნია {len(results)} შედეგი ტესტ რანში {run_hash}")

        for result in results:
            # მხოლოდ დაფეილებული ტესტები
            if result.get("status") != "failed":
                continue
                
            logger.info(f"ნაპოვნია დაფეილებული ტესტი: {result}")
            case_id = result.get("case_id")
            actual_result = result.get("actual_result", "")
            
            # ტესტ ქეისის დეტალების მიღება
            case_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
            logger.info(f"მოთხოვნა ტესტ ქეისზე: {case_url}")
            case_response = requests.get(case_url, headers=qase_headers)
            
            if case_response.status_code != 200:
                logger.warning(f"ვერ მიიღო ტესტ ქეისი {case_id}: {case_response.text}")
                continue

            case_data = case_response.json().get("result", {})
            logger.info(f"მიღებულია ტესტ ქეისის მონაცემები: {case_data}")
            
            title = case_data.get("title", "უსათაურო")
            description = case_data.get("description", "")
            steps = case_data.get("steps", [])
            severity = result.get("severity", case_data.get("severity", "Medium"))

            # მოამზადე ნაბიჯები ClickUp-ისთვის
            steps_output = ["ნაბიჯები:"]
            for i, step in enumerate(steps):
                action = step.get("action", "")
                expected = step.get("expected_result", "")
                steps_output.append(f"{i+1}. {action} ➔ {expected}")
            steps_text = "\n".join(steps_output)

            # მოამზადე პრიორიტეტი ClickUp-ისთვის
            priority_map = {
                "Critical": 1,
                "High": 2,
                "Medium": 3,
                "Low": 4
            }
            priority_value = priority_map.get(severity, 3)

            # მოამზადე დავალების შინაარსი
            content = f"""მოწყობილობა:
{description}

{steps_text}

მიმდინარე შედეგი:
{actual_result}

მოსალოდნელი შედეგი:
{' '.join([step.get("expected_result", "") for step in steps])}

დამატებითი ინფორმაცია:
- ტესტ ქეისი: #{case_id}
- ტესტ რანი: {run.get("title", "")}"""

            # გააგზავნე დავალება ClickUp-ში
            payload = {
                "name": f"[დეფექტი] {title}",
                "content": content,
                "status": CLICKUP_DEFAULT_STATUS,
                "assignees": [188468937],
                "priority": priority_value
            }

            logger.info(f"იგზავნება დავალება ClickUp-ში: {payload}")
            res = requests.post(
                f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID_DRESSUP}/task",
                headers=clickup_headers,
                json=payload
            )
            
            logger.info(f"ClickUp პასუხი: {res.status_code} - {res.text}")

            if res.status_code in [200, 201]:
                created += 1

    if created == 0:
        return jsonify({"status": "ok", "message": "არ მოიძებნა შესაბამისი ტესტ ქეისები ბაგ რეპორტისთვის."})

    სიტყვა = "დეფექტი" if created == 1 else "დეფექტი"
    return Response(
        json.dumps({"status": "ok", "message": f"{created} {სიტყვა} გადავიდა ClickUp-ში."}, ensure_ascii=False),
        content_type="application/json"
    )

@app.route('/debug', methods=['GET'])
def debug_qase():
    results = {}
    
    # 1. შევამოწმოთ API ტოკენი და ტესტ რანები
    runs_url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=10"
    runs_response = requests.get(runs_url, headers=qase_headers)
    
    if runs_response.status_code != 200:
        return jsonify({
            "error": "ვერ მოიძებს ტესტ რანებს",
            "status_code": runs_response.status_code,
            "response": runs_response.text
        })
    
    # შევამოწმოთ რანები
    runs = runs_response.json().get("result", {}).get("entities", [])
    runs_info = []
    
    for run in runs:
        run_hash = run.get("hash")
        run_info = {
            "hash": run_hash,
            "title": run.get("title"),
            "status": run.get("status"),
            "stats": run.get("stats", {})
        }
        
        # შევამოწმოთ თითოეული რანის შედეგები
        if run_hash:
            result_url = f"https://api.qase.io/v1/result/{PROJECT_CODE}/{run_hash}?limit=100"
            result_response = requests.get(result_url, headers=qase_headers)
            
            if result_response.status_code == 200:
                results_data = result_response.json().get("result", {}).get("entities", [])
                # მხოლოდ დაფეილებულები ავიღოთ
                failed_results = [r for r in results_data if r.get("status") == "failed"]
                
                run_info["results_count"] = len(results_data)
                run_info["failed_count"] = len(failed_results)
                
                # თუ გვაქვს დაფეილებული შედეგები, ერთი მაინც დავამატოთ დეტალურად
                if failed_results:
                    sample_failed = failed_results[0]
                    case_id = sample_failed.get("case_id")
                    run_info["sample_failed"] = {
                        "case_id": case_id,
                        "status": sample_failed.get("status"),
                        "actual_result": sample_failed.get("actual_result")
                    }
                    
                    # შევამოწმოთ ტესტ ქეისის დეტალები
                    if case_id:
                        case_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
                        case_response = requests.get(case_url, headers=qase_headers)
                        
                        if case_response.status_code == 200:
                            case_data = case_response.json().get("result", {})
                            run_info["sample_case_details"] = {
                                "title": case_data.get("title"),
                                "has_steps": len(case_data.get("steps", [])) > 0,
                                "description": case_data.get("description", "")[:100] + "..." if case_data.get("description") else ""
                            }
                        else:
                            run_info["case_error"] = f"Status: {case_response.status_code}, Response: {case_response.text[:200]}"
                    
            else:
                run_info["results_error"] = f"Status: {result_response.status_code}, Response: {result_response.text[:200]}"
        
        runs_info.append(run_info)
    
    results["runs"] = runs_info
    
    # 2. შევამოწმოთ ClickUp კავშირი
    clickup_test_url = f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID_DRESSUP}"
    clickup_response = requests.get(clickup_test_url, headers=clickup_headers)
    
    results["clickup_test"] = {
        "status_code": clickup_response.status_code,
        "response": clickup_response.text[:200] if clickup_response.text else None
    }
    
    return jsonify(results)

@app.route('/force_send', methods=['GET'])
def force_send():
    # FORCE MANUAL TEST CASE - ხელით გაკეთებული ტესტ ქეისი
    # თქვენ უკვე გაქვთ ტესტ ქეისი ID 2, ამიტომ მას გამოვიყენებთ
    case_id = 2  # შეცვალეთ ეს იმ case ID-თ რომელიც გაქვთ!
    
    # ტესტ ქეისის დეტალების მიღება
    case_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
    case_response = requests.get(case_url, headers=qase_headers)
    
    if case_response.status_code != 200:
        return jsonify({"status": "error", "message": f"ვერ მიიღო ტესტ ქეისი {case_id}"})
    
    case_data = case_response.json().get("result", {})
    title = case_data.get("title", "უსათაურო")
    description = case_data.get("description", "")
    steps = case_data.get("steps", [])
    
    # მოამზადე ნაბიჯები ClickUp-ისთვის
    steps_output = ["ნაბიჯები:"]
    for i, step in enumerate(steps):
        action = step.get("action", "")
        expected = step.get("expected_result", "")
        steps_output.append(f"{i+1}. {action} ➔ {expected}")
    steps_text = "\n".join(steps_output)
    
    # მოამზადე დავალების შინაარსი
    content = f"""მოწყობილობა:
{description}

{steps_text}

მიმდინარე შედეგი:
ავტორიზაცია პრობლემა

მოსალოდნელი შედეგი:
{' '.join([step.get("expected_result", "") for step in steps])}

დამატებითი ინფორმაცია:
- ტესტ ქეისი: #{case_id}
- მხოლოდ ტესტისთვის"""
    
    # გააგზავნე დავალება ClickUp-ში
    payload = {
        "name": f"[დეფექტი] {title}",
        "content": content,
        "status": CLICKUP_DEFAULT_STATUS,
        "assignees": [188468937],  # შეცვალეთ თქვენი ID-ით
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