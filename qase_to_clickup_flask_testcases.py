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
        # 1. მივიღოთ ყველა ტესტ ქეისი
        cases_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}?limit=100"
        logger.info(f"მოთხოვნა ტესტ ქეისებზე: {cases_url}")
        
        cases_response = requests.get(cases_url, headers=qase_headers)
        logger.info(f"ქეისების პასუხის სტატუსი: {cases_response.status_code}")
        
        if cases_response.status_code != 200:
            logger.error(f"Qase API შეცდომა (ქეისები): {cases_response.text}")
            return jsonify({
                "status": "error", 
                "message": f"Qase API error - ვერ მოიძებნა ტესტ ქეისები. კოდი: {cases_response.status_code}"
            }), 500
        
        all_cases = cases_response.json().get("result", {}).get("entities", [])
        logger.info(f"სულ მოძიებულია {len(all_cases)} ტესტ ქეისი")
        
        # 2. მივიღოთ დასრულებული ტესტ რანები
        runs_url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=10&status[]=completed"
        logger.info(f"მოთხოვნა ტესტ რანებზე: {runs_url}")
        
        runs_response = requests.get(runs_url, headers=qase_headers)
        logger.info(f"რანების პასუხის სტატუსი: {runs_response.status_code}")
        
        if runs_response.status_code != 200:
            logger.error(f"Qase API შეცდომა (რანები): {runs_response.text}")
            return jsonify({
                "status": "error", 
                "message": f"Qase API error - ვერ მოიძებნა ტესტ რანები. კოდი: {runs_response.status_code}"
            }), 500
        
        runs = runs_response.json().get("result", {}).get("entities", [])
        
        if not runs:
            return jsonify({"status": "ok", "message": "არ მოიძებნა დასრულებული ტესტ რანები."}), 200
        
        # მივიღოთ ბოლო რანის ID
        latest_run = runs[0]
        latest_run_id = latest_run.get("id")
        latest_run_title = latest_run.get("title", "უცნობი რანი")
        logger.info(f"ბოლო რანის ID: {latest_run_id}, სახელი: {latest_run_title}")
        
        # 3. შევამოწმოთ წარუმატებელი ტესტები - გამოვიყენოთ ალტერნატიული მიდგომა
        # შევნახოთ წარუმატებელი ქეისების ID-ები
        failed_case_ids = []
        failed_details = {}
        
        # შევქმნათ ერთიანი ბაგ რეპორტი რანისთვის, ვინაიდან API შეზღუდვების გამო
        # შეიძლება ვერ მივიღოთ ინდივიდუალური წარუმატებელი ტესტების დეტალები
        all_failures_content = f"# წარუმატებელი ტესტ ქეისები რანიდან: {latest_run_title} (ID: {latest_run_id})\n\n"
        all_failures_content += f"## რანის სტატისტიკა:\n"
        all_failures_content += f"- მთლიანი ტესტ ქეისები: {latest_run.get('cases', {}).get('total', 'N/A')}\n"
        all_failures_content += f"- წარუმატებელი: {latest_run.get('stats', {}).get('failed', 'N/A')}\n"
        all_failures_content += f"- წარმატებული: {latest_run.get('stats', {}).get('passed', 'N/A')}\n"
        all_failures_content += f"- გამოტოვებული: {latest_run.get('stats', {}).get('skipped', 'N/A')}\n\n"
        
        # დავამატოთ ბაგ რეპორტები ყველა ქეისისთვის, რომელიც მოსალოდნელია რომ წარუმატებელია
        # (ეს არ არის იდეალური მიდგომა, მაგრამ API შეზღუდვის გამო შესაძლოა აუცილებელი იყოს)
        
        created = 0
        
        if latest_run.get('stats', {}).get('failed', 0) > 0:
            # შევქმნათ ერთი ბაგ რეპორტი, რომელიც მიუთითებს რანის შედეგებზე
            all_failures_content += "## შენიშვნა\n"
            all_failures_content += "მითითებულ რანში მოძიებულია წარუმატებელი ტესტ ქეისები, მაგრამ API შეზღუდვის გამო ვერ ხერხდება მათი დეტალური ინფორმაციის მიღება.\n"
            all_failures_content += f"გთხოვთ, შეამოწმეთ Qase მართვის პანელში რანი ID: {latest_run_id} დეტალური ინფორმაციისთვის.\n\n"
            
            # დავამატოთ ყველა ქეისის სახელები
            all_failures_content += "## შესაძლო წარუმატებელი ტესტ ქეისები:\n"
            for case in all_cases:
                case_title = case.get("title", "უცნობი ქეისი")
                case_id = case.get("id", "N/A")
                all_failures_content += f"- {case_title} (ID: {case_id})\n"
            
            # შევქმნათ ტასკი ClickUp-ში
            payload = {
                "name": f"[BUG REPORT] წარუმატებელი ტესტები რანიდან: {latest_run_title}",
                "content": all_failures_content,
                "status": CLICKUP_DEFAULT_STATUS,
                "priority": 2  # მაღალი პრიორიტეტი
            }
            
            res = requests.post(
                f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID_DRESSUP}/task",
                headers=clickup_headers,
                json=payload
            )
            
            if res.status_code in [200, 201]:
                created = 1
                logger.info(f"შეიქმნა ბაგ რეპორტი რანისთვის: {latest_run_title}")
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