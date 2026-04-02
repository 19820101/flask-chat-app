from flask import Flask, render_template, request, jsonify, send_from_directory
import requests, os, json, math

app = Flask(__name__)
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

SYSTEM_PROMPT = """あなたはSleep Doctor Hirokiという睡眠医学の専門アドバイザーです。

【役割】
睡眠障害のスクリーニング結果に基づき、ICSD-3の分類に従って疾患の可能性を説明し、適切なアドバイスを提供します。
また、Borbelyの2プロセスモデル（Process S: 睡眠恒常性、Process C: 概日リズム）に基づく睡眠分析も行います。

【ICSD-3の7大分類】
1. 不眠症 2. 睡眠関連呼吸障害 3. 中枢性過眠症 4. 概日リズム睡眠-覚醒障害 5. 睡眠時随伴症 6. 睡眠関連運動障害 7. その他

【スクリーニング質問票の知識】
- ISI: 0-7正常、8-14軽度、15-21中等度、22-28重度
- ESS: 10以下正常、11-14軽度過眠、15-17中等度、18-24重度
- STOP-Bang: 0-2低リスク、3-4中リスク、5-8高リスク

【2プロセスモデルの知識】
- Process S（睡眠恒常性）: 覚醒中に指数関数的に蓄積、睡眠中に減衰。時定数は覚醒時約18.2時間、睡眠時約4.2時間
- Process C（概日リズム）: SCNが制御する約24時間周期。深部体温最低点は通常起床2時間前（約4:00-5:00）。アラートネスのピークは10:00頃と21:00頃

【回答ルール】
1. 日本語で温かく優しい口調で回答
2. 300文字程度にまとめる
3. 必ず「確定診断には医療機関の受診が必要です」と伝える
4. 2プロセスモデルの分析結果が送られた場合、概日リズムのずれと睡眠負債について具体的にアドバイスする"""

histories = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/doctor.jpg')
def doctor_image():
    return send_from_directory('.', 'doctor.jpg')

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    bedtime = data.get('bedtime', 23)
    waketime = data.get('waketime', 7)
    
    if waketime < bedtime:
        sleep_duration = waketime + 24 - bedtime
    else:
        sleep_duration = waketime - bedtime
    
    sleep_midpoint = bedtime + sleep_duration / 2
    if sleep_midpoint >= 24:
        sleep_midpoint -= 24
    
    ideal_midpoint = 3.0
    circadian_shift = sleep_midpoint - ideal_midpoint
    if circadian_shift > 12:
        circadian_shift -= 24
    if circadian_shift < -12:
        circadian_shift += 24
    
    ideal_duration = 7.5
    sleep_debt = ideal_duration - sleep_duration
    
    tau_r = 18.2
    tau_d = 4.2
    
    process_s = []
    process_c = []
    times = []
    
    for i in range(288):
        t = i * (48.0 / 288)
        hour = (bedtime - 8 + t) % 24
        times.append(round(hour, 2))
        
        wake_start = 0
        sleep_start = 24 - bedtime + waketime if waketime < bedtime else waketime - bedtime
        day_length = 24 - sleep_duration
        
        t_mod = t % 24
        
        if t < 24:
            if t_mod < (24 - sleep_duration):
                s_val = 1 - (1 - 0.2) * math.exp(-t_mod / tau_r)
            else:
                t_sleep = t_mod - (24 - sleep_duration)
                s_peak = 1 - (1 - 0.2) * math.exp(-(24 - sleep_duration) / tau_r)
                s_val = s_peak * math.exp(-t_sleep / tau_d)
        else:
            t2 = t - 24
            if t2 < (24 - sleep_duration):
                s_base = 0.2
                s_val = 1 - (1 - s_base) * math.exp(-t2 / tau_r)
            else:
                t_sleep = t2 - (24 - sleep_duration)
                s_peak = 1 - (1 - 0.2) * math.exp(-(24 - sleep_duration) / tau_r)
                s_val = s_peak * math.exp(-t_sleep / tau_d)
        
        process_s.append(round(s_val, 4))
        
        phase = 2 * math.pi * (hour - 16) / 24
        c_val = 0.5 + 0.4 * math.sin(phase)
        process_c.append(round(c_val, 4))
    
    if circadian_shift > 1:
        rec_bedtime = bedtime - 0.5
    elif circadian_shift < -1:
        rec_bedtime = bedtime + 0.5
    else:
        rec_bedtime = bedtime
    
    rec_waketime = rec_bedtime + ideal_duration
    if rec_waketime >= 24:
        rec_waketime -= 24
    if rec_bedtime < 0:
        rec_bedtime += 24
    
    def fmt(h):
        hh = int(h) % 24
        mm = int((h % 1) * 60)
        return f"{hh:02d}:{mm:02d}"
    
    return jsonify({
        'times': times,
        'process_s': process_s,
        'process_c': process_c,
        'sleep_duration': round(sleep_duration, 1),
        'sleep_midpoint': round(sleep_midpoint, 1),
        'circadian_shift': round(circadian_shift, 1),
        'sleep_debt': round(sleep_debt, 1),
        'rec_bedtime': fmt(rec_bedtime),
        'rec_waketime': fmt(rec_waketime)
    })

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
