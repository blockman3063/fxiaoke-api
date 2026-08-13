"""
Fxiaoke cURL capture helper.

Run this BEFORE using fxiaoke_client.py for the first time or after session expiry.
It guides you through capturing the necessary cURLs from Edge DevTools.
"""
import json, os, sys
from datetime import datetime

CAPTURE_STATE_PATH = "fxiaoke_capture_state.json"

def load_capture_state():
    if os.path.exists(CAPTURE_STATE_PATH):
        with open(CAPTURE_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_capture_state(state):
    with open(CAPTURE_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def prompt_yes_no(question):
    while True:
        ans = input(f"{question} [y/n]: ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please enter y or n.")

def extract_cookies_from_curl(curl_text):
    """Parse cookie header lines from cURL output."""
    cookies = {}
    for line in curl_text.splitlines():
        line = line.strip()
        if line.startswith("-H 'Cookie:") or line.startswith('"-H" "Cookie:'):
            cookie_str = line.split(":", 1)[1].strip().strip("'\"")
            for part in cookie_str.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()
    return cookies

def extract_url_from_curl(curl_text, method="POST"):
    """Extract URL from first matching request line."""
    for line in curl_text.splitlines():
        line = line.strip().strip("'\"")
        if line.startswith(method + " "):
            # 'POST https://...' or '"POST" "https://..."'
            parts = line.split(None, 1)
            if len(parts) == 2:
                return parts[1].strip().strip("'\"")
    return None

def extract_body_from_curl(curl_text):
    """Extract JSON body from --data or --data-raw."""
    for line in curl_text.splitlines():
        line = line.strip().strip("'\"")
        if line.startswith("--data-raw") or line.startswith("--data"):
            _, _, body = line.partition(" ")
            return body.strip().strip("'\"")
    return None

def main():
    print("=" * 60)
    print("Fxiaoke cURL Capture Helper")
    print("=" * 60)
    print()

    state = load_capture_state()
    has_upload = bool(state.get("upload_url"))
    has_send = bool(state.get("send_url"))
    has_cookies = bool(state.get("cookies"))

    print("Current capture status:")
    print(f"  UploadByStream URL: {'✓' if has_upload else '✗'}")
    print(f"  SendMessage URL:    {'✓' if has_send else '✗'}")
    print(f"  Cookies:            {'✓' if has_cookies else '✗'}")
    print(f"  Session chain:      {'✓' if all(state.get(k) for k in ['session_id','previous_message_id','status_version','ep_tag']) else '✗'}")
    print()

    if not prompt_yes_no("Do you want to capture/update cURLs now?"):
        print("Exiting.")
        return

    print()
    print("Step 1: Capture SendMessage cURL")
    print("-" * 40)
    print("1. Open Edge and go to https://www.fxiaoke.com/XV/UI/Home")
    print("2. Log in if needed.")
    print("3. Open DevTools (F12) → Network tab.")
    print("4. In the target chat, send a short text message or upload any file.")
    print("5. Find the request named 'SendMessage' or 'UploadByStream'.")
    print("6. Right-click → Copy → Copy as cURL (bash).")
    print()

    send_curl = input("Paste the SendMessage cURL here (or leave blank to skip): ").strip()
    if send_curl:
        send_url = extract_url_from_curl(send_curl, "POST")
        if not send_url:
            print("WARNING: Could not auto-extract SendMessage URL. Paste it manually:")
            send_url = input("Send URL: ").strip()
        state["send_url"] = send_url

        # Try to extract cookies
        cookies = extract_cookies_from_curl(send_curl)
        if cookies:
            state["cookies"] = cookies
            print(f"Extracted {len(cookies)} cookies from cURL.")

        # Try to extract body
        body = extract_body_from_curl(send_curl)
        if body:
            try:
                body_json = json.loads(body)
                if "sessionId" in body_json:
                    state["session_id"] = body_json["sessionId"]
                if "previousMessageId" in body_json:
                    state["previous_message_id"] = body_json["previousMessageId"]
                if "statusVersion" in body_json:
                    state["status_version"] = body_json["statusVersion"]
                if "epTag" in body_json:
                    state["ep_tag"] = body_json["epTag"]
                print("Extracted session chain from cURL body.")
            except json.JSONDecodeError:
                print("Could not parse request body as JSON.")

        save_capture_state(state)
        print("✓ Saved SendMessage config.")

    print()
    print("Step 2: Capture UploadByStream cURL")
    print("-" * 40)
    upload_curl = input("Paste the UploadByStream cURL here (or leave blank to skip): ").strip()
    if upload_curl:
        upload_url = extract_url_from_curl(upload_curl, "POST")
        if not upload_url:
            print("WARNING: Could not auto-extract UploadByStream URL. Paste it manually:")
            upload_url = input("Upload URL: ").strip()
        state["upload_url"] = upload_url
        save_capture_state(state)
        print("✓ Saved UploadByStream config.")

    # Ask for missing epTag
    if not state.get("ep_tag"):
        print()
        ep = input("Enter epTag value (from SendMessage cURL body or response): ").strip()
        if ep:
            state["ep_tag"] = ep
            save_capture_state(state)

    save_capture_state(state)
    print()
    print("=" * 60)
    print("Capture complete. State saved to", CAPTURE_STATE_PATH)
    print()
    print("Next step:")
    print("  1. Copy fxiaoke_capture_state.json → fxiaoke_session.json")
    print("  2. Run: python fxiaoke_client.py --session fxiaoke_session.json status")
    print("  3. Test send: python fxiaoke_client.py --session fxiaoke_session.json send_text --text 'hello'")
    print("=" * 60)

if __name__ == "__main__":
    main()
