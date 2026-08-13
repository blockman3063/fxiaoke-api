import json
import os
import subprocess
import sys
import time
from datetime import datetime

# Ensure the skill scripts dir is importable
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))

from fxiaoke_client import FxiaokeClient

SESSION_PATH = os.environ.get(
    "FXIAOKE_SESSION_PATH",
    os.path.join(SKILL_DIR, "fxiaoke_session.json"),
)
POLL_INTERVAL = 3  # seconds
HISTORY_PATH = os.path.join(SKILL_DIR, "listener_history.json")


def _load_history() -> dict:
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_history(history: dict) -> None:
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _shorten(text: str, n: int = 60) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[: n - 3] + "..."


def hermes_reply(text: str) -> str:
    """Call hermes chat -q for a quick reply."""
    try:
        proc = subprocess.run(
            ["hermes", "chat", "-q", text],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=SKILL_DIR,
        )
        out = proc.stdout.strip()
        if out:
            return out
        return "(empty reply)"
    except subprocess.TimeoutExpired:
        return "[timeout]"
    except Exception as exc:
        return f"[error: {exc}]"


def main() -> None:
    client = FxiaokeClient(session_path=SESSION_PATH)
    session = client.state
    history = _load_history()

    # Primary listen target: the BOT session we already use for tests.
    # You can extend this to a list later.
    listen_sessions = [
        session.get("session_id", "dcb28d7671954d71b46325611b02ded6"),
    ]
    for sid in listen_sessions:
        history.setdefault(sid, {"last_message_id": 0, "last_message_time": 0})

    print(f"[{_ts()}] listener started; polling {POLL_INTERVAL}s")
    print(f"[{_ts()}] listening on: {listen_sessions}")

    while True:
        try:
            for sid in listen_sessions:
                state = history.setdefault(sid, {"last_message_id": 0, "last_message_time": 0})
                last_msg_id = state.get("last_message_id", 0) or 0
                last_msg_time = state.get("last_message_time", 0) or 0

                # Pull latest messages; prefer reverse so newest is first.
                try:
                    result = client.get_reverse_messages(session_id=sid, limit=10)
                except Exception as exc:
                    print(f"[{_ts()}] get_reverse_messages error {sid}: {exc}")
                    continue

                messages = result.get("messages", [])
                if not messages:
                    continue

                new_msgs = []
                for m in messages:
                    mid = m.get("messageId") or 0
                    mtime = m.get("messageTime") or m.get("createTime") or 0
                    if mid > last_msg_id or (mid == last_msg_id and mtime > last_msg_time):
                        new_msgs.append(m)

                if not new_msgs:
                    continue

                # Process newest first
                for m in reversed(new_msgs):
                    mid = m.get("messageId") or 0
                    mtime = m.get("messageTime") or m.get("createTime") or 0
                    sender = m.get("senderName") or m.get("senderId") or ""
                    content = m.get("content") or ""
                    msg_type = m.get("messageType") or m.get("type") or ""

                    print(f"[{_ts()}] NEW {sid}: id={mid} type={msg_type} from={sender} text={_shorten(content)}")

                    # Skip non-text messages for now; can be extended.
                    if msg_type not in ("T", "Text", "text", "", None):
                        print(f"[{_ts()}] skip non-text msg id={mid}")
                        state["last_message_id"] = mid
                        state["last_message_time"] = mtime
                        continue

                    t0 = time.time()
                    reply = hermes_reply(content)
                    dt = int((time.time() - t0) * 1000)
                    print(f"[{_ts()}] hermes reply {dt}ms: {_shorten(reply)}")

                    try:
                        send = client.send_text(text=reply, session_id=sid)
                        print(f"[{_ts()}] sent reply id={send.get('messageId')} sv={send.get('statusVersion')}")
                    except Exception as exc:
                        print(f"[{_ts()}] send_text error: {exc}")

                    state["last_message_id"] = mid
                    state["last_message_time"] = mtime
                    _save_history(history)

            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print(f"\n[{_ts()}] listener stopped")
            break
        except Exception as exc:
            print(f"[{_ts()}] loop error: {exc}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
