from flask import Flask, render_template, request, jsonify, send_from_directory
import requests, os

app = Flask(__name__)
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
SYSTEM_PROMPT = 'あなたはSleep Doctor Hirokiという睡眠の専門アドバイザーです。睡眠に関する悩みに科学的根拠に基づいた親身なアドバイスをしてください。医療行為は行わず深刻な場合は医療機関の受診を勧めてください。日本語で温かく優しい口調で回答し200文字程度にまとめてください。睡眠に関係ない質問には睡眠に関するご相談をお待ちしていますと伝えてください。'
histories = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/doctor.jpg')
def doctor_image():
    return send_from_directory('.', 'doctor.jpg')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    msg = data.get('message', '')
    sid = data.get('session_id', 'default')
    if sid not in histories:
        histories[sid] = []
    histories[sid].append({'role': 'user', 'content': msg})
    if len(histories[sid]) > 20:
        histories[sid] = histories[sid][-20:]
    try:
        r = requests.post('https://api.anthropic.com/v1/messages',
            headers={'x-api-key': ANTHROPIC_API_KEY, 'content-type': 'application/json', 'anthropic-version': '2023-06-01'},
            json={'model': 'claude-sonnet-4-20250514', 'max_tokens': 1024, 'system': SYSTEM_PROMPT, 'messages': histories[sid]})
        result = r.json()
        reply = result['content'][0]['text']
        histories[sid].append({'role': 'assistant', 'content': reply})
        return jsonify({'response': reply})
    except Exception as e:
        return jsonify({'response': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
