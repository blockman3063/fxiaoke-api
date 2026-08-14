import json, os, re, subprocess, sys, time
from datetime import datetime

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

from fxiaoke_client import FxiaokeClient

SESSION_PATH = os.environ.get(
    "FXIAOKE_SESSION_PATH",
    os.path.join(SKILL_DIR, "..", "fxiaoke_session.json"),
)
POLL_INTERVAL = 3
HISTORY_PATH = os.path.join(SKILL_DIR, "..", "listener_history.json")
BOT_SESSION_ID = "dcb28d7671954d71b46325611b02ded6"

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


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


def _shorten(text: str, n: int = 80) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[: n - 3] + "..."


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _clean_hermes_output(text: str) -> str:
    # Strip ANSI escape codes first so prefix checks are reliable
    text = _strip_ansi(text)

    # Drop leading metadata/loading lines
    drop_prefixes = ("Query:", "Initializing agent...", "────────────────────────────────────────")
    lines = [line for line in text.splitlines() if not any(line.strip().startswith(prefix) for prefix in drop_prefixes)]

    # Drop Hermes UI frame lines
    frame_re = re.compile(r"^╭.*Hermes.*╮?$")
    bottom_re = re.compile(r"^╰[-─\s]*╯?$")
    lines = [line for line in lines if not frame_re.match(line) and not bottom_re.match(line)]
    cleaned = "\n".join(lines)

    # Drop Hermes UI frame blocks
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # Drop trailing resume/status block
    lines = cleaned.splitlines()
    cutoff = None
    for i, line in enumerate(lines):
        if line.strip().startswith("Resume this session with:") or line.strip().startswith("Session:"):
            cutoff = i
            break
    if cutoff is not None:
        lines = lines[:cutoff]

    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def hermes_reply(text: str) -> str:
    try:
        proc = subprocess.run(
            [
                "hermes", "chat", "-q", text,
            ],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=SKILL_DIR,
        )
        out = proc.stdout.strip()
        if not out:
            return "(empty reply)"
        if proc.returncode != 0:
            return f"[hermes exit {proc.returncode}: {_shorten(out or proc.stderr)}]"
        return _clean_hermes_output(out)
    except subprocess.TimeoutExpired:
        return "[timeout]"
    except Exception as exc:
        return f"[error: {exc}]"


def _is_text_message(m: dict) -> bool:
    msg_type = m.get("messageType") or m.get("type") or ""
    return msg_type in ("T", "Text", "text")


def _extract_text(m: dict) -> str:
    content = m.get("content") or ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _extract_message_id(m: dict) -> int:
    return int(m.get("messageId") or 0)


def _extract_message_time(m: dict) -> int:
    return int(m.get("messageTime") or m.get("createTime") or 0)


def main() -> None:
    client = FxiaokeClient(session_path=SESSION_PATH)
    history = _load_history()

    listen_sessions = [BOT_SESSION_ID]
    for sid in listen_sessions:
        history.setdefault(sid, {"last_message_id": 0, "last_message_time": 0})

    print(f"[{_ts()}] listener started; polling {POLL_INTERVAL}s")
    print(f"[{_ts()}] listening on: {listen_sessions}")

    while True:
        try:
            for sid in listen_sessions:
                st = history.setdefault(sid, {"last_message_id": 0, "last_message_time": 0})
                last_msg_id = int(st.get("last_message_id") or 0)
                last_msg_time = int(st.get("last_message_time") or 0)

                try:
                    result = client.get_messages(session_id=sid, limit=20)
                except Exception as exc:
                    print(f"[{_ts()}] get_messages error {sid}: {exc}")
                    continue

                messages = result.get("messages", [])
                if not messages:
                    continue

                new_msgs = []
                for m in messages:
                    mid = _extract_message_id(m)
                    mtime = _extract_message_time(m)
                    if mid > last_msg_id or (mid == last_msg_id and mtime > last_msg_time):
                        new_msgs.append(m)

                if not new_msgs:
                    continue

                for m in reversed(new_msgs):
                    mid = _extract_message_id(m)
                    mtime = _extract_message_time(m)
                    sender_id = m.get("senderId") or m.get("sender", {}).get("employeeID") or 0
                    content = _extract_text(m)

                    print(f"[{_ts()}] NEW {sid}: id={mid} from={sender_id} text={_shorten(content)}")

                    if sid != BOT_SESSION_ID or not _is_text_message(m) or sender_id != 1177:
                        print(f"[{_ts()}] skip non-user-text msg id={mid}")
                        st["last_message_id"] = mid
                        st["last_message_time"] = mtime
                        _save_history(history)
                        continue

                    stripped = content.strip()

                    if stripped == "/ping":
                        reply = "pong"
                        print(f"[{_ts()}] ping reply: {reply}")
                        try:
                            send = client.send_text(text=reply, session_id=sid, previous_message_id=mid)
                            print(f"[{_ts()}] sent reply id={send.get('messageId')} sv={send.get('statusVersion')}")
                        except Exception as exc:
                            print(f"[{_ts()}] send_text error: {exc}")
                        st["last_message_id"] = mid
                        st["last_message_time"] = mtime
                        _save_history(history)
                        continue

                    if stripped.startswith("!"):
                        prompt = stripped[1:].strip()
                        reply = hermes_reply(prompt)
                        reply = f"${reply}"
                        print(f"[{_ts()}] hermes reply: {_shorten(reply)}")
                        try:
                            send = client.send_text(text=reply, session_id=sid, previous_message_id=mid)
                            print(f"[{_ts()}] sent reply id={send.get('messageId')} sv={send.get('statusVersion')}")
                        except Exception as exc:
                            print(f"[{_ts()}] send_text error: {exc}")
                        st["last_message_id"] = mid
                        st["last_message_time"] = mtime
                        _save_history(history)
                        continue

                    print(f"[{_ts()}] skip non-command msg id={mid}")
                    st["last_message_id"] = mid
                    st["last_message_time"] = mtime
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
