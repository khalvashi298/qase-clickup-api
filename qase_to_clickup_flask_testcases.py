import os
from flask import Flask, jsonify, Response
import requests
import re
import json

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
    # პირველად მივიღოთ ტესტ რანის შესახებ ინფორმაცია, რომ ვიპოვოთ წარუმატებელი ტესტ ქეისები
    runs_url = f"https://api.qase.io/v1/run/{PROJECT_CODE}?limit=1&status=complete"
    runs_response = requests.get(runs_url, headers=qase_headers)
    
    if runs_response.status_code != 200:
        return jsonify({"status": "error", "message": "Qase API error - ვერ მოიძებნა ტესტ რანები."}), 500
    
    runs = runs_response.json().get("result", {}).get("entities", [])
    if not runs:
        return jsonify({"status": "ok", "message": "არ მოიძებნა დასრულებული ტესტ რანები."}), 200
    
    # ბოლო დასრულებული ტესტ რანი
    latest_run_id = runs[0].get("id")
    
    # მოვიძიოთ წარუმატებელი (Failed) ტესტ ქეისები ამ რანში
    results_url = f"https://api.qase.io/v1/result/{PROJECT_CODE}/{latest_run_id}?status[]=failed"
    results_response = requests.get(results_url, headers=qase_headers)
    
    if results_response.status_code != 200:
        return jsonify({"status": "error", "message": "Qase API error - ვერ მოიძებნა ტესტ შედეგები."}), 500
    
    failed_results = results_response.json().get("result", {}).get("entities", [])
    
    if not failed_results:
        return jsonify({"status": "ok", "message": "არ მოიძებნა წარუმატებელი (Failed) ტესტ ქეისები."}), 200
    
    # შევაგროვოთ წარუმატებელი ქეისების ID-ები
    failed_case_ids = [result.get("case", {}).get("id") for result in failed_results if result.get("case")]
    
    if not failed_case_ids:
        return jsonify({"status": "ok", "message": "ვერ მოიძებნა ტესტ ქეისების ID-ები."}), 200
    
    created = 0
    
    # თითოეული წარუმატებელი ქეისისთვის მივიღოთ დეტალური ინფორმაცია
    for case_id in failed_case_ids:
        case_url = f"https://api.qase.io/v1/case/{PROJECT_CODE}/{case_id}"
        case_response = requests.get(case_url, headers=qase_headers)
        
        if case_response.status_code != 200:
            continue
        
        case = case_response.json().get("result", {})
        if not case:
            continue
        
        title = case.get("title", "Untitled Test Case")
        description = case.get("description", "No description.")
        steps = case.get("steps", [])
        
        # მოვიძიოთ შესაბამისი წარუმატებელი შედეგი, რომ მივიღოთ წარუმატებლობის მიზეზი
        relevant_result = next((r for r in failed_results if r.get("case", {}).get("id") == case_id), None)
        actual_result = relevant_result.get("comment", "დეტალები არ არის მითითებული") if relevant_result else "დეტალები არ არის მითითებული"
        
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
        
        content = f"{description}\n\n{steps_text}\n\nმიმდინარე შედეგი: \n{actual_result}\n\nმოსალოდნელი შედეგი: \n{expected_text}"
        
        payload = {
            "name": f"[BUG] {title}",
            "content": content,
            "status": CLICKUP_DEFAULT_STATUS
        }
        
        res = requests.post(
            f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID_DRESSUP}/task",
            headers=clickup_headers,
            json=payload
        )
        
        if res.status_code in [200, 201]:
            created += 1
    
    სიტყვა = "ბაგ-რეპორტი" if created == 1 else "ბაგ-რეპორტი"
    return Response(
        json.dumps({"status": "ok", "message": f"{created} {სიტყვა} გადავიდა ClickUp-ში."}, ensure_ascii=False),
        content_type="application/json"
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # ეს იწვევს Render-ის მიერ მიცემულ პორტზე გაშვებას
    app.run(host="0.0.0.0", port=port)