import requests, os, json, time, argparse
from datetime import datetime

BASE = "https://www.fxiaoke.com"

# Default headers shared by upload and send
DEFAULT_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "zh-CN,zh-TW;0.9,en;0.8",
    "origin": "https://www.fxiaoke.com",
    "priority": "u=1, i",
    "referer": "https://www.fxiaoke.com/XV/UI/Home",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Microsoft Edge";v="128"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
    "x-requested-with": "XMLHttpRequest",
    "is-tenantless": "false",
}

class FxiaokeClient:
    def __init__(self, session_path="fxiaoke_session.json"):
        self.session_path = session_path
        self.state = self._load_state()
        self.headers = dict(DEFAULT_HEADERS)
        self.cookies = self.state.get("cookies", {})
        # Override headers with captured values if present
        if self.state.get("headers"):
            self.headers.update(self.state["headers"])

    def _load_state(self):
        if os.path.exists(self.session_path):
            with open(self.session_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_state(self):
        # Persist latest session chain
        with open(self.session_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def configure_from_cookies(self, cookies: dict):
        """Refresh cookies from a fresh browser capture."""
        self.cookies = dict(cookies)
        self.state["cookies"] = self.cookies
        self.save_state()

    def configure_send_url(self, send_url: str):
        """Set the SendMessage endpoint from captured cURL."""
        self.state["send_url"] = send_url
        self.save_state()

    def configure_upload_url(self, upload_url: str):
        """Set the UploadByStream endpoint from captured cURL."""
        self.state["upload_url"] = upload_url
        self.save_state()

    def update_session_chain(self, session_id, previous_message_id, status_version):
        """Persist the authoritative session chain from API responses."""
        self.state["session_id"] = session_id
        self.state["previous_message_id"] = previous_message_id
        self.state["status_version"] = status_version
        self.save_state()

    def _send_json(self, url, payload, extra_headers=None):
        headers = dict(self.headers)
        if extra_headers:
            headers.update(extra_headers)
        resp = requests.post(url, headers=headers, cookies=self.cookies, json=payload, timeout=30)
        return resp

    def _send_text(self, url, payload, extra_headers=None):
        headers = dict(self.headers)
        if extra_headers:
            headers.update(extra_headers)
        headers["content-type"] = "text/plain"
        resp = requests.post(url, headers=headers, cookies=self.cookies, data=json.dumps(payload), timeout=30)
        return resp

    def refresh_cookies_from_edge(self, domain=".fxiaoke.com"):
        """Refresh cookies from the running Edge browser."""
        try:
            import browser_cookie3
        except ImportError:
            raise RuntimeError("browser-cookie3 is not installed")
        cookies = {}
        for c in browser_cookie3.edge(domain_name=domain):
            cookies[c.name] = c.value
        if not cookies:
            raise RuntimeError(f"No cookies found for domain={domain}")
        self.configure_from_cookies(cookies)
        return cookies

    def _recover_session_chain(self, context: str):
        """Recover session chain from checkUpdatedAsyncV2 when 904 occurs."""
        try:
            result = self.check_updated(
                ep_tag=self.state.get("ep_tag"),
                status_version=self.state.get("status_version"),
            )
            session_list = result.get("session_list", [])
            if session_list:
                session_info = session_list[0]
                new_sv = session_info.get("statusVersion") or session_info.get("updateTime")
                new_last_msg_id = session_info.get("lastMessageId")
                if new_sv:
                    self.state["status_version"] = str(new_sv)
                if new_last_msg_id is not None:
                    self.state["previous_message_id"] = int(new_last_msg_id)
                self.save_state()
                return True
        except Exception as exc:
            raise RuntimeError(
                f"{context} returned 904, and session chain recovery failed: {exc}"
            ) from exc
        return False

    def _maybe_refresh_904(self, context: str, url: str, payload, content_type=None):
        """Try request, and if it returns 904, recover session chain from server and retry once."""
        if content_type == "text/plain":
            resp = self._send_text(url, payload)
        else:
            resp = self._send_json(url, payload)

        try:
            result = self._handle_response(resp, context)
            return result
        except RuntimeError as exc:
            msg = str(exc)
            if "904" not in msg:
                raise
            # Recover session chain from server and retry once
            self._recover_session_chain(context)
            if content_type == "text/plain":
                resp = self._send_text(url, payload)
            else:
                resp = self._send_json(url, payload)
            return self._handle_response(resp, context)

    def _ensure_fresh_send_url(self) -> str:
        send_url = self.state.get("send_url")
        if not send_url:
            raise RuntimeError("Missing send_url. Capture it from DevTools and pass to configure_send_url().")

        sid = self.state.get("session_id")
        if "?postId=" not in send_url or sid not in send_url:
            return send_url

        base_url, current_post_id = send_url.split("?postId=", 1)
        prefix = current_post_id[: current_post_id.index(sid) + len(sid)]
        suffix = current_post_id[current_post_id.index(sid) + len(sid):]
        user_id = suffix[:4] if len(suffix) >= 4 else "1177"
        fresh_post_id = f"{prefix}{user_id}{int(time.time() * 1000)}"
        fresh_url = f"{base_url}?postId={fresh_post_id}"
        self.state["send_url"] = fresh_url
        self.save_state()
        return fresh_url

    def send_text(self, text, session_id=None, previous_message_id=None, status_version=None, ep_tag=None, file_info=None, mention_at_all=False, mention_at_full_user_id_list=None):
        """
        Send a plain text message.
        Requires a configured send_url and valid session chain.
        """
        send_url = self._ensure_fresh_send_url()

        sid = session_id or self.state.get("session_id")
        prev = previous_message_id if previous_message_id is not None else self.state.get("previous_message_id")
        sv = status_version or self.state.get("status_version")
        ep = ep_tag or self.state.get("ep_tag")

        if sid is None or prev is None or sv is None or ep is None:
            raise RuntimeError(
                f"Missing session chain fields: session_id={sid}, previous_message_id={prev}, "
                f"status_version={sv}, ep_tag={ep}"
            )

        payload = {
            "content": text,
            "fileInfo": file_info,
            "mentionAtFullUserIdList": mention_at_full_user_id_list if mention_at_full_user_id_list is not None else [],
            "mentionAtAll": mention_at_all,
            "secret": False,
            "sessionId": sid,
            "previousMessageId": prev,
            "epTag": ep,
            "statusVersion": sv,
            "localUniversalDefinitionTimestamp": int(time.time() * 1000),
            "localBotDefinitionsTimestamp": int(time.time() * 1000) - 86400000,
        }

        resp = self._maybe_refresh_904("send text", send_url, payload)
        result = resp
        if isinstance(result, dict):
            current = result.get("value", {}).get("currentMessage") or {}
            result["messageId"] = current.get("messageId")
            result["statusVersion"] = result.get("value", {}).get("statusVersion") or current.get("statusVersion")
        return result

    def upload_file(self, file_path):
        """
        Upload a file to Fxiaoke and return TempFileName.
        Requires a configured upload_url.
        """
        upload_url = self.state.get("upload_url")
        if not upload_url:
            raise RuntimeError("Missing upload_url. Capture it from DevTools and pass to configure_upload_url().")

        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)

        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_name)[1].lstrip(".")

        upload_headers = {
            "accept": "*/*",
            "content-length": str(file_size),
            "content-type": "multipart/form-data",
            "extension": ext,
            "startindex": "0",
            "storagepath": "",
            "totallength": str(file_size),
        }

        with open(file_path, "rb") as f:
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if ext == "xlsx" else "application/octet-stream"
            files = {"file": (file_name, f, mime)}
            resp = requests.post(upload_url, headers=upload_headers, cookies=self.cookies, files=files, timeout=60)

        if resp.status_code != 200:
            raise Exception(f"Upload failed: {resp.status_code} {resp.text[:500]}")

        result = resp.json()
        temp_name = result.get("TempFileName")
        if not temp_name:
            raise Exception(f"No TempFileName in upload response: {result}")

        return temp_name, file_size, file_name

    def send_file(self, file_path, session_id=None, previous_message_id=None, status_version=None, ep_tag=None):
        """
        Upload a file and send it to the configured chat.
        Auto-updates session chain from response.
        """
        send_url = self.state.get("send_url")
        if not send_url:
            raise RuntimeError("Missing send_url. Capture it from DevTools and pass to configure_send_url().")

        temp_name, file_size, file_name = self.upload_file(file_path)

        sid = session_id or self.state.get("session_id")
        prev = previous_message_id if previous_message_id is not None else self.state.get("previous_message_id")
        sv = status_version or self.state.get("status_version")
        ep = ep_tag or self.state.get("ep_tag")

        if sid is None or prev is None or sv is None or ep is None:
            raise RuntimeError("Missing session chain. Send a text message first or ensure all fields are configured.")

        payload = {
            "content": "",
            "fileInfo": {
                "value": 3,
                "value1": temp_name,
                "value2": file_size,
                "value3": file_name,
            },
            "secret": False,
            "sessionId": sid,
            "previousMessageId": prev,
            "epTag": ep,
            "statusVersion": sv,
            "localUniversalDefinitionTimestamp": int(time.time() * 1000),
            "localBotDefinitionsTimestamp": int(time.time() * 1000) - 86400000,
        }

        resp = self._maybe_refresh_904("send file", send_url, payload)
        result = resp
        return result

    def get_messages(self, session_id, limit=20, before_message_id=None, ep_tag=None, status_version=None):
        """
        List messages in a chat session, ordered newest-first.
        Requires a configured send_url or explicit endpoint.
        """
        send_url = self.state.get("send_url")
        if not send_url:
            raise RuntimeError("Missing send_url. Configure it first.")

        base_url = send_url.split('?')[0]
        get_url = base_url.replace('SendMessage', 'GetMessages')

        sid = session_id or self.state.get("session_id")
        ep = ep_tag or self.state.get("ep_tag")
        sv = status_version or self.state.get("status_version")

        if sid is None or ep is None or sv is None:
            raise RuntimeError(
                f"Missing session fields: session_id={sid}, ep_tag={ep}, status_version={sv}"
            )

        payload = {
            "num": limit,
            "sessionId": sid,
            "env": 0,
            "fromMessageId": before_message_id or 0,
            "epTag": ep,
            "statusVersion": sv,
        }

        resp = self._maybe_refresh_904("get_messages", get_url, payload)
        result = resp

        messages = result.get("value", {}).get("messageList", [])
        if not messages:
            messages = result.get("value", {}).get("messages", [])

        return {
            "raw": result,
            "messages": messages,
            "has_more": result.get("value", {}).get("hasMore", False),
        }

    def get_reverse_messages(self, session_id, limit=20, before_message_id=None, ep_tag=None, status_version=None):
        """
        List messages in a chat session, ordered oldest-first (reverse chronological).
        Use for pagination from the beginning of a chat.
        """
        send_url = self.state.get("send_url")
        if not send_url:
            raise RuntimeError("Missing send_url. Configure it first.")

        base_url = send_url.split('?')[0]
        get_url = base_url.replace('SendMessage', 'GetReverseMessages')

        sid = session_id or self.state.get("session_id")
        ep = ep_tag or self.state.get("ep_tag")
        sv = status_version or self.state.get("status_version")

        if sid is None or ep is None or sv is None:
            raise RuntimeError(
                f"Missing session fields: session_id={sid}, ep_tag={ep}, status_version={sv}"
            )

        payload = {
            "num": limit,
            "sessionId": sid,
            "env": 0,
            "fromMessageId": before_message_id or 0,
            "epTag": ep,
            "statusVersion": sv,
        }

        resp = self._send_json(get_url, payload)
        result = self._handle_response(resp, "get_reverse_messages")

        messages = result.get("value", {}).get("messageList", [])
        if not messages:
            messages = result.get("value", {}).get("messages", [])

        return {
            "raw": result,
            "messages": messages,
            "has_more": result.get("value", {}).get("hasMore", False),
        }

    def check_updated(self, ep_tag, status_version, local_universal_definition_timestamp=None, local_bot_definitions_timestamp=None):
        """
        Poll for new updates.
        """
        if not self.state.get("push_url"):
            return {"error": "missing push_url"}
        
        if local_universal_definition_timestamp is None:
            local_universal_definition_timestamp = int(time.time() * 1000)
        if local_bot_definitions_timestamp is None:
            local_bot_definitions_timestamp = int(time.time() * 1000) - 86400000
        
        payload = {
            "epTag": ep_tag,
            "statusVersion": status_version,
            "localUniversalDefinitionTimestamp": local_universal_definition_timestamp,
            "localBotDefinitionsTimestamp": local_bot_definitions_timestamp,
        }
        
        headers = dict(self.headers)
        headers["content-type"] = "text/plain"
        resp = requests.post(self.state["push_url"], headers=headers, cookies=self.cookies, data=json.dumps(payload), timeout=30)
        data = self._handle_response(resp, "check_updated")
        
        # Extract session list from response
        session_list = []
        if isinstance(data, dict):
            value = data.get("value") or {}
            if isinstance(value, dict):
                session_list = value.get("sessionList", [])
        
        return {
            "ok": data.get("success") if isinstance(data, dict) else False,
            "data": data,
            "session_list": session_list,
        }
    
    def get_sessions_from_poll(self, ep_tag, status_version):
        """
        Get session list from checkUpdatedAsyncV2 response.
        This replaces GetSessionList which returns 904.
        """
        result = self.check_updated(ep_tag, status_version)
        return result.get("session_list", [])

    def get_sessions(self):
        """
        List chat sessions using GetSessionList.
        Uses the current session chain from state.
        """
        send_url = self.state.get("send_url")
        if not send_url:
            raise RuntimeError("Missing send_url. Configure it first.")

        base_url = send_url.split('?')[0]
        get_url = base_url.replace('SendMessage', 'GetSessionList')

        sid = self.state.get("session_id")
        ep = self.state.get("ep_tag")
        sv = self.state.get("status_version")

        if sid is None or ep is None or sv is None:
            raise RuntimeError(
                f"Missing session fields: session_id={sid}, ep_tag={ep}, status_version={sv}"
            )

        payload = {
            "num": 50,
            "sessionId": sid,
            "env": 0,
            "fromMessageId": 0,
            "epTag": ep,
            "statusVersion": sv,
        }

        resp = self._send_json(get_url, payload)
        result = self._handle_response(resp, "get_sessions")

        sessions = result.get("value", {}).get("sessions", [])
        if not sessions:
            sessions = result.get("value", {}).get("sessionList", [])

        return {
            "raw": result,
            "sessions": sessions,
        }

    def _handle_response(self, resp, context):
        if resp.status_code != 200:
            raise Exception(f"{context} failed: {resp.status_code} {resp.text[:500]}")

        try:
            result = resp.json()
        except ValueError:
            raise Exception(f"{context} returned non-JSON: {resp.text[:500]}")

        # Detect 904 stale session
        text = json.dumps(result, ensure_ascii=False)
        if "904" in text or "QixinWebException" in text:
            raise RuntimeError(
                f"{context} returned error 904 (stale session). "
                "Re-capture SendMessage cURL from DevTools and update session config."
            )

        # Update session chain from response
        value = result.get("value") or {}
        session_list = value.get("sessionList", [])
        if session_list:
            real_sid = session_list[0].get("sessionId")
            if real_sid:
                self.state["session_id"] = real_sid

            last_msg_id = session_list[0].get("lastMessageId")
            if last_msg_id is not None:
                self.state["previous_message_id"] = int(last_msg_id)

        sv = value.get("statusVersion")
        if sv:
            self.state["status_version"] = str(sv)

        self.save_state()
        return result


def main():
    parser = argparse.ArgumentParser(description="Fxiaoke Web API client")
    parser.add_argument("--session", default="fxiaoke_session.json", help="Session state file")
    parser.add_argument("action", choices=["send_text", "send_file", "upload", "status", "refresh", "get_messages", "get_reverse_messages", "get_sessions", "check_updated"])
    parser.add_argument("--text", help="Text to send")
    parser.add_argument("--file", help="File path to send")
    parser.add_argument("--limit", type=int, default=20, help="Number of messages to fetch")
    parser.add_argument("--before-message-id", dest="before_message_id", type=int, help="Pagination cursor")
    parser.add_argument("--configure-send-url", dest="configure_send_url", help="Set SendMessage URL")
    parser.add_argument("--configure-upload-url", dest="configure_upload_url", help="Set UploadByStream URL")
    parser.add_argument("--cookies-json", dest="cookies_json", help="JSON string of cookies from DevTools")
    parser.add_argument("--ep-tag", dest="ep_tag", help="Set epTag from cURL")
    parser.add_argument("--session-id", dest="session_id", help="Override sessionId")
    parser.add_argument("--previous-message-id", dest="previous_message_id", type=int, help="Override previousMessageId")
    parser.add_argument("--status-version", dest="status_version", help="Override statusVersion")
    parser.add_argument("--edge-domain", dest="edge_domain", default=".fxiaoke.com", help="Edge cookie domain for refresh")

    args = parser.parse_args()
    client = FxiaokeClient(session_path=args.session)

    # Configure overrides
    if args.configure_send_url:
        client.configure_send_url(args.configure_send_url)
        print(f"Configured send_url: {args.configure_send_url}")
    if args.configure_upload_url:
        client.configure_upload_url(args.configure_upload_url)
        print(f"Configured upload_url: {args.configure_upload_url}")
    if args.cookies_json:
        cookies = json.loads(args.cookies_json)
        client.configure_from_cookies(cookies)
        print("Cookies updated.")
    if args.ep_tag:
        client.state["ep_tag"] = args.ep_tag
        client.save_state()
        print(f"Set ep_tag: {args.ep_tag}")
    if args.session_id:
        client.state["session_id"] = args.session_id
        client.save_state()
    if args.previous_message_id is not None:
        client.state["previous_message_id"] = args.previous_message_id
        client.save_state()
    if args.status_version:
        client.state["status_version"] = args.status_version
        client.save_state()

    if args.action == "status":
        print(json.dumps(client.state, ensure_ascii=False, indent=2))
        return

    if args.action == "refresh":
        cookies = client.refresh_cookies_from_edge(domain=args.edge_domain)
        print(f"Refreshed {len(cookies)} cookies from Edge.")
        print("Updated session file:", client.session_path)
        return

    if args.action == "upload":
        if not args.file:
            parser.error("--file required for upload")
        temp_name, file_size, file_name = client.upload_file(args.file)
        print(json.dumps({"TempFileName": temp_name, "FileSize": file_size, "FileName": file_name}, ensure_ascii=False))
        return

    if args.action == "send_text":
        if not args.text:
            parser.error("--text required for send_text")
        result = client.send_text(args.text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.action == "send_file":
        if not args.file:
            parser.error("--file required for send_file")
        result = client.send_file(args.file)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.action == "get_messages":
        result = client.get_messages(
            session_id=getattr(args, 'session_id', None),
            limit=args.limit,
            before_message_id=getattr(args, 'before_message_id', None)
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.action == "get_reverse_messages":
        result = client.get_reverse_messages(
            session_id=getattr(args, 'session_id', None),
            limit=args.limit,
            before_message_id=getattr(args, 'before_message_id', None)
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.action == "get_sessions":
        result = client.get_sessions()
        print(json.dumps({"sessions": result.get("sessions", [])}, ensure_ascii=False, indent=2))
        return

    if args.action == "check_updated":
        ep_tag = getattr(args, 'ep_tag', None) or client.state.get("ep_tag")
        status_version = getattr(args, 'status_version', None) or client.state.get("status_version")
        if not ep_tag or not status_version:
            parser.error("check_updated requires --ep-tag and --status-version, or configured session state")
        result = client.check_updated(ep_tag, status_version)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

if __name__ == "__main__":
    main()
