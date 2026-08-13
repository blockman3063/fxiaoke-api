import json
import os
import sys
import time
from typing import Any

import requests
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

SESSION_PATH = os.environ.get("FXIAOKE_SESSION_PATH", "fxiaoke_session.json")


def _load_session() -> dict:
    with open(SESSION_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _cookies(session: dict) -> dict:
    return session.get("cookies", {})


def _headers(content_type: str = "application/json; charset=UTF-8") -> dict:
    return {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "zh-CN,zh-TW;0.9,en;0.8",
        "content-type": content_type,
        "origin": "https://www.fxiaoke.com",
        "referer": "https://www.fxiaoke.com/XV/UI/Home",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
        "x-requested-with": "XMLHttpRequest",
        "is-tenantless": "false",
    }


def _post(url: str, payload: Any, session: dict, content_type: str = "application/json; charset=UTF-8") -> dict:
    cookies = _cookies(session)
    headers = _headers(content_type)
    if content_type == "text/plain":
        resp = requests.post(url, headers=headers, cookies=cookies, data=json.dumps(payload), timeout=30)
    else:
        resp = requests.post(url, headers=headers, cookies=cookies, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "904" in json.dumps(data, ensure_ascii=False) or "QixinWebException" in json.dumps(data, ensure_ascii=False):
        raise RuntimeError("Session expired (904). Refresh fxiaoke_session.json with fresh cookies/tokens.")
    return data


def _post_form(url: str, file_path: str, session: dict) -> dict:
    cookies = _cookies(session)
    headers = _headers("multipart/form-data")
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    ext = os.path.splitext(file_name)[1].lstrip(".")
    headers.update({
        "content-length": str(file_size),
        "extension": ext,
        "startindex": "0",
        "storagepath": "",
        "totallength": str(file_size),
    })
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f)}
        resp = requests.post(url, headers=headers, cookies=cookies, files=files, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _get(session: dict, tool_name: str, arguments: dict) -> str:
    if tool_name == "send_text":
        text = arguments.get("text") or arguments.get("content")
        if not text:
            raise ValueError("Missing text/content")
        send_url = session.get("send_url")
        if not send_url:
            raise RuntimeError("Missing send_url in session")
        sid = session.get("session_id")
        prev = session.get("previous_message_id")
        sv = session.get("status_version")
        ep = session.get("ep_tag")
        if not all([sid, prev, sv, ep]):
            raise RuntimeError("Missing session chain fields")
        payload = {
            "content": text,
            "fileInfo": None,
            "mentionAtFullUserIdList": [],
            "mentionAtAll": False,
            "secret": False,
            "sessionId": sid,
            "previousMessageId": prev,
            "epTag": ep,
            "statusVersion": sv,
            "localUniversalDefinitionTimestamp": int(time.time() * 1000),
            "localBotDefinitionsTimestamp": int(time.time() * 1000) - 86400000,
        }
        data = _post(send_url, payload, session)
        msg = data.get("value", {}).get("currentMessage", {})
        session["previous_message_id"] = msg.get("messageId") or prev
        session["status_version"] = data.get("value", {}).get("statusVersion") or sv
        return json.dumps({"messageId": msg.get("messageId"), "content": msg.get("content"), "statusVersion": session["status_version"]}, ensure_ascii=False)

    if tool_name == "send_file":
        file_path = arguments.get("file_path") or arguments.get("file")
        if not file_path:
            raise ValueError("Missing file_path/file")
        upload_url = session.get("upload_url")
        send_url = session.get("send_url")
        if not upload_url or not send_url:
            raise RuntimeError("Missing upload_url/send_url in session")
        upload = _post_form(upload_url, file_path, session)
        temp_file_name = upload.get("TempFileName") or upload.get("tempFileName")
        if not temp_file_name:
            raise RuntimeError("Upload failed: %s" % upload)
        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_name)[1].lstrip(".")
        file_size = os.path.getsize(file_path)
        sid = session.get("session_id")
        prev = session.get("previous_message_id")
        sv = session.get("status_version")
        ep = session.get("ep_tag")
        payload = {
            "content": "",
            "fileInfo": {
                "extension": ext,
                "fileDisplayName": file_name,
                "fileSize": file_size,
                "fullFileId": "",
                "tempFileName": temp_file_name,
            },
            "mentionAtFullUserIdList": [],
            "mentionAtAll": False,
            "secret": False,
            "sessionId": sid,
            "previousMessageId": prev,
            "epTag": ep,
            "statusVersion": sv,
            "localUniversalDefinitionTimestamp": int(time.time() * 1000),
            "localBotDefinitionsTimestamp": int(time.time() * 1000) - 86400000,
        }
        data = _post(send_url, payload, session)
        msg = data.get("value", {}).get("currentMessage", {})
        session["previous_message_id"] = msg.get("messageId") or prev
        session["status_version"] = data.get("value", {}).get("statusVersion") or sv
        return json.dumps({"messageId": msg.get("messageId"), "messageType": msg.get("messageType"), "tempFileName": temp_file_name, "statusVersion": session["status_version"]}, ensure_ascii=False)

    if tool_name == "get_messages":
        sid = arguments.get("session_id") or session.get("session_id")
        limit = int(arguments.get("limit", 20))
        before = arguments.get("before_message_id") or arguments.get("beforeMessageId")
        base = session.get("send_url", "").split("?")[0]
        url = base.replace("SendMessage", "GetMessages")
        payload = {"sessionId": sid, "limit": limit}
        if before:
            payload["beforeMessageId"] = int(before)
        data = _post(url, payload, session)
        messages = data.get("value", {}).get("messageList", []) or data.get("value", {}).get("messages", [])
        return json.dumps({"messages": messages, "hasMore": data.get("value", {}).get("hasMore", False)}, ensure_ascii=False)

    if tool_name == "get_reverse_messages":
        sid = arguments.get("session_id") or session.get("session_id")
        limit = int(arguments.get("limit", 20))
        before = arguments.get("before_message_id") or arguments.get("beforeMessageId")
        base = session.get("send_url", "").split("?")[0]
        url = base.replace("SendMessage", "GetReverseMessages")
        payload = {"sessionId": sid, "limit": limit}
        if before:
            payload["beforeMessageId"] = int(before)
        data = _post(url, payload, session)
        messages = data.get("value", {}).get("messageList", []) or data.get("value", {}).get("messages", [])
        return json.dumps({"messages": messages, "hasMore": data.get("value", {}).get("hasMore", False)}, ensure_ascii=False)

    if tool_name == "get_sessions":
        base = session.get("send_url", "").split("?")[0]
        url = base.replace("SendMessage", "GetSessionList")
        sid = session.get("session_id")
        ep = session.get("ep_tag")
        sv = session.get("status_version")
        payload = {"num": 50, "sessionId": sid, "env": 0, "fromMessageId": 0, "epTag": ep, "statusVersion": sv}
        data = _post(url, payload, session)
        sessions = data.get("value", {}).get("sessions", []) or data.get("value", {}).get("sessionList", [])
        return json.dumps({"sessions": sessions}, ensure_ascii=False)

    if tool_name == "check_updated":
        ep = arguments.get("ep_tag") or session.get("ep_tag")
        sv = arguments.get("status_version") or session.get("status_version")
        if not ep or not sv:
            raise ValueError("Missing ep_tag/status_version")
        push_url = session.get("push_url")
        if not push_url:
            raise RuntimeError("Missing push_url in session")
        payload = {
            "epTag": ep,
            "statusVersion": sv,
            "localUniversalDefinitionTimestamp": int(time.time() * 1000),
            "localBotDefinitionsTimestamp": int(time.time() * 1000) - 86400000,
        }
        data = _post(push_url, payload, session, content_type="text/plain")
        session_list = (data.get("value") or {}).get("sessionList", []) if isinstance(data, dict) else []
        return json.dumps({"ok": data.get("success") if isinstance(data, dict) else False, "sessionList": session_list, "statusVersion": (data.get("value") or {}).get("statusVersion") if isinstance(data, dict) else None}, ensure_ascii=False)

    raise ValueError("Unsupported tool: %s" % tool_name)


def main() -> None:
    session = _load_session()
    server = Server("fxiaoke-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="send_text",
                description="Send a text message to a Fxiaoke session.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Message text to send"},
                        "session_id": {"type": "string", "description": "Override session id"},
                        "previous_message_id": {"type": "integer", "description": "Override previous message id"},
                        "status_version": {"type": "string", "description": "Override status version"},
                        "ep_tag": {"type": "string", "description": "Override ep tag"},
                    },
                    "required": ["text"],
                },
            ),
            Tool(
                name="send_file",
                description="Send a file to a Fxiaoke session.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Local file path to send"},
                        "session_id": {"type": "string", "description": "Override session id"},
                        "previous_message_id": {"type": "integer", "description": "Override previous message id"},
                        "status_version": {"type": "string", "description": "Override status version"},
                        "ep_tag": {"type": "string", "description": "Override ep tag"},
                    },
                    "required": ["file_path"],
                },
            ),
            Tool(
                name="get_messages",
                description="Fetch messages from a Fxiaoke session.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Override session id"},
                        "limit": {"type": "integer", "description": "Max messages to return", "default": 20},
                        "before_message_id": {"type": "integer", "description": "Pagination cursor"},
                    },
                },
            ),
            Tool(
                name="get_reverse_messages",
                description="Fetch messages in reverse order from a Fxiaoke session.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Override session id"},
                        "limit": {"type": "integer", "description": "Max messages to return", "default": 20},
                        "before_message_id": {"type": "integer", "description": "Pagination cursor"},
                    },
                },
            ),
            Tool(
                name="get_sessions",
                description="List available Fxiaoke sessions.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="check_updated",
                description="Poll for updates / session list using checkUpdatedAsyncV2.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ep_tag": {"type": "string"},
                        "status_version": {"type": "string"},
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            result = _get(session, name, arguments)
            return [TextContent(type="text", text=result)]
        except Exception as exc:
            return [TextContent(type="text", text=json.dumps({"error": str(exc)}, ensure_ascii=False))]

    stdio_server(server)
