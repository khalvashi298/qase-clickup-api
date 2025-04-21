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
        <p>გადაიტანე ტესტ ქეისები ClickUp-ში ბაგ რეპორტის სახით</p>
        <a href="/send_testcases">
            <button style="padding:10px 20px; font-size:16px;">გადაიტანე ტესტ ქეისები</button>
        </a>
    </body>
    </html>
    """

# ✅ ბაგ რეპორტების შექმნა ტესტ ქეისებიდან
@app.route('/send_testcases', methods=['GET'])
def send_testcases():
    try:
        # მივიღოთ ყველა ტესტ ქეისი
        url = f"https://api.qase.io/v1/case/{PROJECT_CODE}?limit=100"
        logger.info(f"მოთხოვნა ტესტ ქეისებზე: {url}")
        
        response = requests.get(url, headers=qase_headers)
        logger.info(f"API პასუხის სტატუსი: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Qase API შეცდომა: {response.text}")
            return jsonify({
                "status": "error", 
                "message": f"Qase API error - ვერ მოიძებნა ტესტ ქეისები. კოდი: {response.status_code}"
            }), 500
        
        cases = response.json().get("result", {}).get("entities", [])
        logger.info(f"მოძიებულია {len(cases)} ტესტ ქეისი")
        
        if not cases:
            return jsonify({"status": "ok", "message": "არ მოიძებნა ტესტ ქეისები."}), 200
        
        # ფილტრაცია - მხოლოდ 'dressup'-ის შემცველი ქეისები
        filtered = []
        for c in cases:
            if isinstance(c, dict):
                title = c.get("title", "").lower()
                steps = c.get("steps", [])
                combined_steps = " ".join([
                    str(step.get("action") or "") + " " + str(step.get("expected_result") or "")
                    for step in steps
                ]).lower()
                
                # ჩავთვალოთ რომ ეს არის "failed" ქეისები (რეალურად აქ უნდა იყოს უფრო კონკრეტული ლოგიკა)
                # მომავალში აქ შეგიძლიათ დაამატოთ ლოგიკა, რომელიც რეალურად გაფილტრავს failed ქეისებს
                if "dressup" in title or "dressup" in combined_steps:
                    # დროებითი ფილტრი - აქ შეიძლება დაამატოთ სხვა პირობები failed ქეისების საიდენტიფიკაციოდ
                    if c.get("description", "").lower().find("failed") >= 0 or title.find("failed") >= 0:
                        filtered.append(c)
        
        if not filtered:
            return jsonify({"status": "ok", "message": "არ მოიძებნა შესაბამისი ტესტ ქეისები ბაგ რეპორტისთვის."}), 200
        
        created = 0
        for case in filtered:
            title = case.get("title", "Untitled Test Case")
            description = case.get("description", "No description.")
            steps = case.get("steps", [])
            
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
            
            content = f"{description}\n\n{steps_text}\n\n**მიმდინარე შედეგი:** \n\nწარუმატებელი (Failed)\n\n**მოსალოდნელი შედეგი:** \n\n{expected_text}"
            
            payload = {
                "name": f"[BUG] {title}",
                "content": content,
                "status": CLICKUP_DEFAULT_STATUS,
                "priority": 2  # მაღალი პრიორიტეტი
            }
            
            res = requests.post(
                f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID_DRESSUP}/task",
                headers=clickup_headers,
                json=payload
            )
            
            if res.status_code in [200, 201]:
                created += 1
                logger.info(f"შეიქმნა ბაგ რეპორტი: {title}")
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