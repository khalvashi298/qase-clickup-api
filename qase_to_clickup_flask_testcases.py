import os
from flask import Flask, jsonify, Response
import requests
import re
import json
import logging

# ლოგების გასამართად
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# QASE და CLICKUP პარამეტრები
QASE_API_TOKEN = "dd203d20ea7992c881633c69c093d0509997d86687fd317141fcfaba9bc5d71c"
PROJECT_CODE = "DRESSUP"
CLICKUP_TOKEN = "pk_188468937_C74O5LJ8IMKNHTPMTC5QAHGGKW3U9I6Z"
CLICKUP_LIST_ID_DRESSUP = "901807146872"
CLICKUP_DEFAULT_STATUS = "to do"

# Header-ები
qase_headers = {
    "Token": QASE_API_TOKEN,
    "Content-Type": "application/json"
}

clickup_headers = {
    "Authorization": CLICKUP_TOKEN,
    "Content-Type": "application/json"
}

# ✅ ეს არის მთავარი გვერდი "/" (ღილაკით)
@app.route("/")
def home():
    return """
    <html>
    <head><title>Qase ➜ ClickUp</title></head>
    <body style="font-family:sans-serif; padding:30px;">
        <h2>Qase ➜ ClickUp გადამტანი</h2>
        <p>გადაიტანე წარუმატებელი (Failed) ტესტ ქეისები ClickUp-ში</p>
        <a href="/send_testcases">
            <button style="padding:10px 20px; font-size:16px;">გადაიტანე Failed ტესტ ქეისები</button>
        </a>
    </body>
    </html>
    """

# ✅ წარუმატებელი (Failed) ტესტ ქეისების გადატანა
@app.route('/send_testcases', methods=['GET'])
def send_testcases():
    try:
        # 1. მივიღოთ ბოლო დასრულებული ტესტ რანი
        runs_url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=1&status=complete"
        logger.info(f"მოთხოვნა რანებზე: {runs_url}")
        
        runs_response = requests.get(runs_url, headers=qase_headers)
        logger.info(f"რანების პასუხის სტატუსი: {runs_response.status_code}")
        
        if runs_response.status_code != 200:
            logger.error(f"Qase API შეცდომა (რანები): {runs_response.text}")
            return jsonify({
                "status": "error", 
                "message": f"Qase API error - ვერ მოიძებნა ტესტ რანები. კოდი: {runs_response.status_code}"
            }), 500
        
        runs_data = runs_response.json()
        runs = runs_data.get("result", {}).get("entities", [])
        
        if not runs:
            return jsonify({"status": "ok", "message": "არ მოიძებნა დასრულებული ტესტ რანები."}), 200
        
        latest_run_id = runs[0].get("id")
        logger.info(f"ბოლო რანის ID: {latest_run_id}")
        
        # 2. მივიღოთ ტესტ რანის დეტალები
        run_details_url = f"https://api.qase.io/v1/run/{PROJECT_CODE}/{latest_run_id}"
        logger.info(f"მოთხოვნა რანის დეტალებზე: {run_details_url}")
        
        run_details_response = requests.get(run_details_url, headers=qase_headers)
        logger.info(f"რანის დეტალების პასუხის სტატუსი: {run_details_response.status_code}")
        
        if run_details_response.status_code != 200:
            logger.error(f"Qase API შეცდომა (რანის დეტალები): {run_details_response.text}")
            return jsonify({
                "status": "error", 
                "message": f"Qase API error - ვერ მოიძებნა რანის დეტალები. კოდი: {run_details_response.status_code}"
            }), 500
        
        # 3. შევამოწმოთ არის თუ არა წარუმატებელი ტესტები
        run_stats = run_details_response.json().get("result", {}).get("stats", {})
        failed_cases_count = run_stats.get("failed", 0)
        
        if failed_cases_count == 0:
            return jsonify({"status": "ok", "message": "არ მოიძებნა წარუმატებელი (Failed) ტესტ ქეისები."}), 200
        
        # 4. მივიღოთ ტესტ შედეგები
        results_url = f"https://api.qase.io/v1/result/{PROJECT_CODE}/{latest_run_id}"
        logger.info(f"მოთხოვნა ტესტ შედეგებზე: {results_url}")
        
        results_response = requests.get(results_url, headers=qase_headers)
        logger.info(f"შედეგების პასუხის სტატუსი: {results_response.status_code}")
        
        if results_response.status_code != 200:
            logger.error(f"Qase API შეცდომა (შედეგები): {results_response.text}")
            return jsonify({
                "status": "error", 
                "message": f"Qase API error - ვერ მოიძებნა ტესტ შედეგები. კოდი: {results_response.status_code}"
            }), 500
        
        all_results = results_response.json().get("result", {}).get("entities", [])
        logger.info(f"მიღებული შედეგების რაოდენობა: {len(all_results)}")
        
        # 5. გავფილტროთ მხოლოდ წარუმატებელი ტესტები
        failed_results = [result for result in all_results if result.get("status") == "failed"]
        logger.info(f"წარუმატებელი შედეგების რაოდენობა: {len(failed_results)}")
        
        if not failed_results:
            return jsonify({"status": "ok", "message": "არ მოიძებნა წარუმატებელი (Failed) ტესტ ქეისები."}), 200
        
        # 6. თითოეული წარუმატებელი ტესტისთვის შევქმნათ ბაგ რეპორტი ClickUp-ში
        created = 0
        
        for result in failed_results:
            case_id = result.get("case", {}).get("id")
            
            if not case_id:
                continue
            
            # მივიღოთ ტესტ ქეისის დეტალები
            case_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
            logger.info(f"მოთხოვნა ქეისის დეტალებზე: {case_url}")
            
            case_response = requests.get(case_url, headers=qase_headers)
            
            if case_response.status_code != 200:
                logger.warning(f"ვერ მოიძებნა ქეისის დეტალები (ID: {case_id}): {case_response.status_code}")
                continue
            
            case = case_response.json().get("result", {})
            if not case:
                continue
            
            # მოვამზადოთ ბაგ რეპორტის შინაარსი
            title = case.get("title", "Untitled Test Case")
            description = case.get("description", "No description.")
            steps = case.get("steps", [])
            
            # წარუმატებლობის მიზეზი
            actual_result = result.get("comment", "დეტალები არ არის მითითებული")
            
            seen_links = set()
            steps_output = ["ნაბიჯები:"]
            
            for i, s in enumerate(steps):
                action = s.get("action") or ""
                urls = re.findall(r'https?://\S+', action)
                for url in urls:
                    if url in seen_links:
                        action = action.replace(url, "")
                    else:
                        seen_links.add(url)
                steps_output.append(f"{i+1}. {action.strip()}")
            
            steps_text = "\n".join(steps_output)
            expected_text = "\n".join([
                f"{str(s.get('expected_result') or '')}" for s in steps
            ]) if steps else ""
            
            # შედეგის დეტალები
            time_start = result.get("time_start", "")
            time_end = result.get("time_end", "")
            duration = result.get("duration", 0)
            
            content = (
                f"{description}\n\n"
                f"{steps_text}\n\n"
                f"**მიმდინარე შედეგი:** \n{actual_result}\n\n"
                f"**მოსალოდნელი შედეგი:** \n{expected_text}\n\n"
                f"**ტესტის შესრულების დეტალები:**\n"
                f"დაწყების დრო: {time_start}\n"
                f"დასრულების დრო: {time_end}\n"
                f"ხანგრძლივობა: {duration} წამი"
            )
            
            # შევქმნათ ტასკი ClickUp-ში
            payload = {
                "name": f"[BUG] {title}",
                "content": content,
                "status": CLICKUP_DEFAULT_STATUS,
                "priority": 2  # მაღალი პრიორიტეტი ბაგებისთვის
            }
            
            res = requests.post(
                f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID_DRESSUP}/task",
                headers=clickup_headers,
                json=payload
            )
            
            if res.status_code in [200, 201]:
                created += 1
                logger.info(f"ბაგ რეპორტი შეიქმნა: {title}")
            else:
                logger.error(f"ClickUp API შეცდომა: {res.status_code}, {res.text}")
        
        სიტყვა = "ბაგ-რეპორტი" if created == 1 else "ბაგ-რეპორტი"
        return Response(
            json.dumps({"status": "ok", "message": f"{created} {სიტყვა} გადავიდა ClickUp-ში."}, ensure_ascii=False),
            content_type="application/json"
        )
        
    except Exception as e:
        logger.exception("შეცდომა მოხდა:")
        return jsonify({"status": "error", "message": f"მოხდა შეცდომა: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # ეს იწვევს Render-ის მიერ მიცემულ პორტზე გაშვებას
    app.run(host="0.0.0.0", port=port)