from flask import Flask, render_template, request, jsonify, send_from_directory
import requests, os, json

app = Flask(__name__)
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

SYSTEM_PROMPT = """あなたはSleep Doctor Hirokiという睡眠医学の専門アドバイザーです。

【役割】
睡眠障害のスクリーニング結果に基づき、ICSD-3（国際睡眠障害分類第3版）の分類に従って疾患の可能性を説明し、適切なアドバイスを提供します。

【ICSD-3の7大分類】
1. 不眠症（慢性不眠症、短期不眠症）
2. 睡眠関連呼吸障害（閉塞性睡眠時無呼吸症候群 OSA、中枢性睡眠時無呼吸）
3. 中枢性過眠症（ナルコレプシー1型/2型、特発性過眠症）
4. 概日リズム睡眠-覚醒障害（睡眠相後退型、交代勤務型、非24時間型）
5. 睡眠時随伴症（夢遊病、レム睡眠行動障害、悪夢障害）
6. 睡眠関連運動障害（レストレスレッグス症候群 RLS、周期性四肢運動障害 PLMD）
7. その他の睡眠障害

【スクリーニング質問票の知識】
- ISI（不眠重症度指数）: 0-7正常、8-14軽度、15-21中等度、22-28重度
- ESS（エプワース眠気尺度）: 10以下正常、11-14軽度過眠、15-17中等度、18-24重度
- STOP-Bang: 0-2低リスク、3-4中リスク、5-8高リスク（OSA）
- PSQI: 5.5点未満正常、5.5以上睡眠障害の疑い

【回答ルール】
1. ユーザーから問診スコアが送られた場合、スコアを解釈し、疑われる疾患分類を説明する
2. 追加の鑑別質問を行い、より具体的な疾患の可能性を絞り込む
3. 必ず「これはスクリーニング結果であり、確定診断には医療機関の受診が必要です」と伝える
4. 生活改善のアドバイスも提供する
5. 日本語で温かく優しい口調で回答する
6. 300文字程度にまとめる
7. 重症度が高い場合は強く受診を勧める"""

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
