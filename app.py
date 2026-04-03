from flask import Flask, render_template, request, jsonify, send_from_directory
import requests, os, json, math

app = Flask(__name__)
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

SYSTEM_PROMPT = """あなたはSleep Doctor Hirokiという睡眠医学の専門アドバイザーです。

【役割】
睡眠障害のスクリーニング結果に基づき、ICSD-3の分類に従って疾患の可能性を説明し、適切なアドバイスを提供します。
また、Borbelyの2プロセスモデルとHongらのCSS（Circadian Sleep Sufficiency）理論に基づく睡眠分析も行います。

【ICSD-3の7大分類】
1. 不眠症 2. 睡眠関連呼吸障害 3. 中枢性過眠症 4. 概日リズム睡眠-覚醒障害 5. 睡眠時随伴症 6. 睡眠関連運動障害 7. その他

【スクリーニング質問票の知識】
- ISI: 0-7正常、8-14軽度、15-21中等度、22-28重度
- ESS: 10以下正常、11-14軽度過眠、15-17中等度、18-24重度
- STOP-Bang: 0-2低リスク、3-4中リスク、5-8高リスク

【2プロセスモデル + CSS理論の知識】
- Process S（睡眠恒常性）: 覚醒中に指数関数的に蓄積、睡眠中に減衰。時定数は覚醒時約18.2時間、睡眠時約4.2時間
- Process C（概日リズム）: SCNが制御する約24時間周期
- DLMO（Dim Light Melatonin Onset）: 概日位相の指標。Midsleep - 7hで推定（Song et al. 2024, Forgerモデル）
- CSS（Circadian Sleep Sufficiency）: 概日リズム的に十分な睡眠かを判定（Hong et al. 2021, iScience）
  - 入眠時刻によって必要な睡眠時間が変わる（23時→約7.5h、遅れるほど短くなる）
  - CSSが高い人ほど日中の眠気（ESS）が低い（ρ=-0.50）
  - 睡眠時間（TST）ではなく「いつ寝るか」が重要
- 概日位相のずれ（DLMO変動）はMDD/BDIの気分症状を直接引き起こす（Song et al. 2024）

【回答ルール】
1. 日本語で温かく優しい口調で回答
2. 300文字程度にまとめる
3. 必ず「確定診断には医療機関の受診が必要です」と伝える
4. CSS分析結果が送られた場合、Circadian SufficientかInsufficientかに基づき具体的にアドバイスする
5. 概日位相ずれが大きい場合、光療法のタイミングとメラトニン分泌への影響を説明する
6. 気分障害リスクが示された場合、概日リズム矯正の重要性を強調する"""

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
    bed_str = data.get('bedtime', '23:00')
    wake_str = data.get('waketime', '07:00')
    bh, bm = bed_str.split(':')
    wh, wm = wake_str.split(':')
    bedtime = int(bh) + int(bm)/60
    waketime = int(wh) + int(wm)/60

    if waketime < bedtime:
        sleep_duration = waketime + 24 - bedtime
    else:
        sleep_duration = waketime - bedtime

    sleep_midpoint = bedtime + sleep_duration / 2
    if sleep_midpoint >= 24:
        sleep_midpoint -= 24

    # Song et al. 2024: DLMO estimation via Forger model
    # CBTmin ~ Midsleep, DLMO = CBTmin - 7h
    dlmo = sleep_midpoint - 7
    if dlmo < 0:
        dlmo += 24

    # Hong et al. 2021: Circadian Necessary Sleep
    # Fig3D: 23:00 -> 7.5h needed, delays reduce by ~0.3h/hour
    delay_from_23 = (bedtime - 23) % 24
    circadian_necessary = max(3.5, min(8.0, 7.5 - 0.3 * delay_from_23))

    # CSS (Circadian Sleep Sufficiency) determination
    is_css = sleep_duration >= circadian_necessary
    css_label = "Circadian Sufficient" if is_css else "Circadian Insufficient"

    # Circadian phase analysis (DLMO-based)
    ideal_dlmo = 21.0
    phase_diff = dlmo - ideal_dlmo
    if phase_diff > 12:
        phase_diff -= 24
    if phase_diff < -12:
        phase_diff += 24
    phase_delay_min = round(phase_diff * 60)

    # Sleep debt vs circadian necessary sleep
    sleep_debt = circadian_necessary - sleep_duration
    sleep_debt_min = round(max(0, sleep_debt) * 60)

    # Mood risk (Song et al. 2024: DLMO disruption -> mood)
    mood_risk = "low"
    if abs(phase_diff) > 2:
        mood_risk = "high"
    elif abs(phase_diff) > 1:
        mood_risk = "moderate"

    # Process S (homeostatic sleep pressure)
    tau_r = 18.2
    tau_d = 4.2
    process_s = []
    process_c = []
    times = []

    for i in range(288):
        t = i * (48.0 / 288)
        hour = (bedtime - 8 + t) % 24
        times.append(round(hour, 2))
        t_mod = t % 24
        wake_dur = 24 - sleep_duration

        if t < 24:
            if t_mod < wake_dur:
                s_val = 1 - (1 - 0.2) * math.exp(-t_mod / tau_r)
            else:
                t_sleep = t_mod - wake_dur
                s_peak = 1 - (1 - 0.2) * math.exp(-wake_dur / tau_r)
                s_val = s_peak * math.exp(-t_sleep / tau_d)
        else:
            t2 = t - 24
            if t2 < wake_dur:
                s_val = 1 - (1 - 0.2) * math.exp(-t2 / tau_r)
            else:
                t_sleep = t2 - wake_dur
                s_peak = 1 - (1 - 0.2) * math.exp(-wake_dur / tau_r)
                s_val = s_peak * math.exp(-t_sleep / tau_d)
        process_s.append(round(s_val, 4))

        # Process C: phase aligned to estimated DLMO
        phase = 2 * math.pi * (hour - (dlmo + 7)) / 24
        c_val = 0.5 + 0.4 * math.sin(phase)
        process_c.append(round(c_val, 4))

    # Recommendations based on circadian phase
    if phase_delay_min > 60:
        rec_bedtime = bedtime - 0.5
    elif phase_delay_min < -60:
        rec_bedtime = bedtime + 0.5
    else:
        rec_bedtime = bedtime
    rec_duration = max(3.5, min(8.5, circadian_necessary + 0.5))
    rec_waketime = rec_bedtime + rec_duration
    if rec_waketime >= 24:
        rec_waketime -= 24
    if rec_bedtime < 0:
        rec_bedtime += 24

    def fmt(h):
        hh = int(h) % 24
        mm = int((h % 1) * 60)
        return f"{hh:02d}:{mm:02d}"

    return jsonify({
        'hours': times, 'bedtime_h': bedtime, 'waketime_h': waketime,
        'process_s': process_s,
        'process_c': process_c,
        'sleep_duration_h': round(sleep_duration, 1),
        'sleep_midpoint': round(sleep_midpoint, 1),
        'dlmo': round(dlmo, 1),
        'dlmo_fmt': fmt(dlmo),
        'circadian_necessary_h': round(circadian_necessary, 1),
        'css_label': css_label,
        'is_css': is_css,
        'phase_delay_min': phase_delay_min,
        'sleep_debt_min': sleep_debt_min,
        'mood_risk': mood_risk,
        'recommended_bedtime': fmt(rec_bedtime),
        'recommended_waketime': fmt(rec_waketime),
        'rec_duration_h': round(rec_duration, 1)
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
