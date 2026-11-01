
import os
import json
from urllib import request

def make_ai_plan(text):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY が設定されていません")

    instructions = """
あなたはGazebo内の差動二輪ロボットの行動計画AIです。
ユーザーの日本語指示を運転動作の配列に変換してください。

使用できる動作：
forward: 前進
backward: 後退
left: 左回転
right: 右回転
stop: 停止

前進・後退の速度は0.25m/s、
旋回の角速度は0.7rad/sです。
90度回転するには約2.24秒必要です。

四角形を描く指示では、前進と90度回転を4組作成してください。
動作は最大16個、合計30秒以内。
各動作の実行時間は0.1秒から3秒です。
理解できない指示では空の配列を返してください。
"""

    schema = {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "forward", "backward",
                                "left", "right", "stop"
                            ]
                        },
                        "seconds": {"type": "number"}
                    },
                    "required": ["action", "seconds"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["steps"],
        "additionalProperties": False
    }

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": text}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "robot_plan",
                "strict": True,
                "schema": schema
            }
        }
    }

    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with request.urlopen(req, timeout=20) as response:
        data = json.load(response)

    steps = json.loads(
        data["choices"][0]["message"]["content"]
    )["steps"]

    mapping = {
        "forward": (0.25, 0.0, "前進"),
        "backward": (-0.25, 0.0, "後退"),
        "left": (0.0, 0.7, "左回転"),
        "right": (0.0, -0.7, "右回転"),
        "stop": (0.0, 0.0, "停止")
    }

    plan = []
    total = 0.0

    for step in steps[:16]:
        action = step["action"]
        if action not in mapping:
            continue

        seconds = max(0.1, min(float(step["seconds"]), 3.0))
        if action in ("left", "right"):
            seconds = min(seconds * 1.3, 4.0)
        if total + seconds > 30:
            break

        v, w, name = mapping[action]
        plan.append((v, w, seconds, name))
        total += seconds

    return plan

