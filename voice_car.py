import json
import re
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rclpy
from geometry_msgs.msg import Twist

rclpy.init()
node = rclpy.create_node("voice_car")
pub = node.create_publisher(
    Twist, "/model/vehicle_blue/cmd_vel", 10
)

lock = threading.Lock()
plan = []
deadline = 0
speed = (0.0, 0.0)

def publish(v, w):
    msg = Twist()
    msg.linear.x = float(v)
    msg.angular.z = float(w)
    pub.publish(msg)

def rule_make_plan(text):
    text = text.replace("全身", "前進")
    text = text.replace("交代", "後退")
    text = text.replace("バック", "後退")
    text = text.replace("止まれ", "停止")

    parts = re.split(
        r"、|。|，|そして|次に|それから|してから|して",
        text
    )

    result = []

    for part in parts:
        if not part.strip():
            continue

        if any(x in part for x in ["止ま", "停止", "ストップ"]):
            result.append((0.0, 0.0, 0.2, "停止"))

        elif "右" in part:
            result.append((0.0, -0.7, 1.5, "右回転"))

        elif "左" in part:
            result.append((0.0, 0.7, 1.5, "左回転"))

        elif any(x in part for x in ["後ろ", "後退", "戻"]):
            result.append((-0.25, 0.0, 3.0, "後退"))

        elif any(x in part for x in ["前", "進", "直進"]):
            result.append((0.25, 0.0, 3.0, "前進"))

    return result[:8]



from ai_planner import make_ai_plan

def make_plan(text):
    if any(word in text for word in
           ["止ま", "停止", "ストップ"]):
        return [(0.0, 0.0, 0.2, "停止")]

    if "円" in text or "丸" in text or "えんを" in text:
        return [(0.25, 0.50, 12.5, "円形走行")]

    try:
        return make_ai_plan(text)
    except Exception as e:
        print("AIエラー:", e, flush=True)
        return rule_make_plan(text)

def drive_loop():
    global deadline, speed
    while True:
        with lock:
            now = time.monotonic()
            if now >= deadline:
                if plan:
                    v, w, duration, name = plan.pop(0)
                    speed = (v, w)
                    deadline = now + duration
                    print("実行:", name, flush=True)
                else:
                    speed = (0.0, 0.0)
            v, w = speed
        publish(v, w)
        time.sleep(0.1)

HTML = """<!doctype html>
<html lang="ja">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI音声ロボットカー</title>
<style>
body{font-family:sans-serif;max-width:620px;margin:35px auto;
padding:20px;text-align:center;background:#f3f6fa;color:#203047}
h1{font-size:27px}
button{padding:16px 20px;margin:6px;border:0;border-radius:12px;
font-size:17px;cursor:pointer;background:#2563eb;color:white}
.stop{background:#dc2626}
#result{padding:18px;background:white;border-radius:12px;
min-height:55px;margin:18px 0}
</style>
<h1>🚗 AI音声ロボットカー 🎙️</h1>
<p>マイクを押して日本語で運転指示をしてください。</p>
<button onclick="listen()">🎤 音声で指示</button>
<button class="stop" onclick="send('停止')">■ 停止</button>
<div id="result">音声を待っています</div>
<p>動作確認用ボタン</p>
<button onclick="send('前進')">↑ 前進</button>
<button onclick="send('左')">← 左</button>
<button onclick="send('右')">右 →</button>
<button onclick="send('後退')">↓ 後退</button>
<script>
const result = document.getElementById('result');
async function send(text){
  result.textContent = '指示：' + text;
  try {
    const response = await fetch('/command', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text})
    });
    const data = await response.json();
    result.textContent = '認識：「'+text+'」\\n動作：'+data.actions.join(' → ');
  } catch(e) {
    result.textContent = '通信エラー：'+e.message;
  }
}
function listen(){
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if(!SR){result.textContent='Chromeで開いてください';return}
  const rec = new SR();
  rec.lang='ja-JP';
  rec.interimResults=false;
  rec.onresult=e=>send(e.results[0][0].transcript);
  rec.onerror=e=>result.textContent='音声エラー：'+e.error;
  result.textContent='聞き取り中...';
  rec.start();
}
</script>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        global deadline, speed
        if self.path != "/command":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if length > 4096:
            self.send_error(413)
            return
        obj = json.loads(self.rfile.read(length))
        text = str(obj.get("text", ""))[:200]
        actions = make_plan(text)

        with lock:
            plan.clear()
            if any(x in text for x in ["止ま", "停止", "ストップ"]):
                actions = [(0.0, 0.0, 0.2, "停止")]
            plan.extend(actions)
            deadline = 0
            speed = (0.0, 0.0)
            publish(0, 0)

        names = [a[3] for a in actions] or ["命令を認識できません"]
        data = json.dumps({"actions": names}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

threading.Thread(target=drive_loop, daemon=True).start()
print("音声ロボット起動: http://localhost:8765", flush=True)
try:
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
except KeyboardInterrupt:
    publish(0, 0)
finally:
    node.destroy_node()
    rclpy.shutdown()

