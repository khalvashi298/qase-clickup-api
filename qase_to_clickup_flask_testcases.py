import requests
import re
import json
from flask import Flask, jsonify, Response

app = Flask(__name__)

# --- QASE CONFIG ---
QASE_API_TOKEN = "899e1d184ff7c82a3c1d13a624c496d3c97f4b41f03916c5a01745c20159f5b8"
PROJECT_CODE = "DRESSUP"

# --- CLICKUP CONFIG ---
CLICKUP_TOKEN = "pk_188468937_C74O5LJ8IMKNHTPMTC5QAHGGKW3U9I6Z"
CLICKUP_LIST_ID_DRESSUP = "901807146872"
CLICKUP_DEFAULT_STATUS = "to do"

# --- HEADERS ---
qase_headers = {
    "Token": QASE_API_TOKEN,
    "Content-Type": "application/json"
}

clickup_headers = {
    "Authorization": CLICKUP_TOKEN,
    "Content-Type": "application/json"
}

@app.route('/send_testcases', methods=['GET'])
def send_testcases():
    url = f"https://api.qase.io/v1/case/{PROJECT_CODE}?limit=20"
    response = requests.get(url, headers=qase_headers)

    if response.status_code != 200:
        return jsonify({"status": "error", "message": "Qase API error."}), 500

    cases = response.json().get("result", {}).get("entities", [])

    filtered = []
    for c in cases:
        if isinstance(c, dict):
            title = c.get("title", "").lower()
            steps = c.get("steps", [])
            combined_steps = " ".join([
                str(step.get("action") or "") + " " + str(step.get("expected_result") or "")
                for step in steps
            ]).lower()
            if "dressup" in title or "dressup" in combined_steps:
                filtered.append(c)

    if not filtered:
        return jsonify({"status": "ok", "message": "არ მოიძებნა ტესტ ქეისი სიტყვით 'dressup'."}), 200

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

        content = f"{description}\n\n{steps_text}\n\nმიმდინარე შედეგი: \n\n{expected_text}\n\nმოსალოდნელი შედეგი: \n\n[აქ ჩაწერე მოსალოდნელი შედეგი]"

        payload = {
            "name": f"[TEST CASE] {title}",
            "content": content,
            "status": CLICKUP_DEFAULT_STATUS
        }

        res = requests.post(
            f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID_DRESSUP}/task",
            headers=clickup_headers,
            json=payload
        )

        if res.status_code == 200:
            created += 1

    return Response(
        json.dumps({"status": "ok", "message": f"{created} ტესტ ქეისი დაემატა ClickUp-ში."}, ensure_ascii=False),
        content_type="application/json"
    )

if __name__ == '__main__':
    app.run(debug=True)
