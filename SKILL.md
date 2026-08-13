---
name: fxiaoke-api
description: Send and receive messages and files in 纷享销客 via direct web API.
tags:
  - fxiaoke
  - chat
  - crm
  - messaging
---

# 纷享销客 Web API

Use when the task is to send/receive messages or files in 纷享销客 through its web backend API, without desktop automation.

## When to use

- Send text or file messages to a 纷享销客 chat.
- Read messages from a 纷享销客 chat session.
- Automate chat interactions without browser UI control.
- Desktop automation is unavailable or unreliable.

## Prerequisites

- A browser session on `https://www.fxiaoke.com/XV/UI/Home` with the target chat open.
- Edge DevTools Network tab to capture cURLs.
- A saved session file `fxiaoke_session.json` containing valid cookies, URLs, and session chain.

## Quick start

1. Verify state:
   ```bash
   python scripts/fxiaoke_client.py --session fxiaoke_session.json status
   ```

2. Read latest messages:
   ```bash
   python scripts/fxiaoke_client.py --session fxiaoke_session.json get_messages --limit 20
   ```

3. Send a test text:
   ```bash
   python scripts/fxiaoke_client.py --session fxiaoke_session.json send_text --text "hello"
   ```

4. Send a test file:
   ```bash
   python scripts/fxiaoke_client.py --session fxiaoke_session.json send_file --file "C:\path\to\file.xlsx"
   ```

## Configuration

All runtime state lives in `fxiaoke_session.json`:

```json
{
  "cookies": { "fs_token": "...", "FSAuthX": "...", ... },
  "send_url": "https://www.fxiaoke.com/H/V5Messenger/SendMessage?...",
  "upload_url": "https://www.fxiaoke.com/FSC/EM/File/UploadByStream?...",
  "session_id": "...",
  "previous_message_id": 123,
  "status_version": "...",
  "ep_tag": "..."
}
```

Update fields via CLI flags:
```bash
python scripts/fxiaoke_client.py \
  --session fxiaoke_session.json \
  --configure-send-url "https://..." \
  --configure-upload-url "https://..." \
  --cookies-json '{"fs_token":"...","FSAuthX":"..."}' \
  --ep-tag "..." \
  --session-id "..." \
  --previous-message-id 123 \
  --status-version "..."
```

Refresh cookies directly from Edge:
```bash
python scripts/fxiaoke_client.py --session fxiaoke_session.json refresh
```

## Verified capabilities

- `get_messages` — read chat history via `GetMessages`
- `send_text` — send plain text via `SendMessage`
- `send_file` — upload file via `UploadByStream`, then send via `SendMessage`
- `refresh` — pull fresh cookies from Edge via `browser-cookie3`

## Known limitations

- `GetSessionList` currently returns 904 with the current cookie/trace combo, so session enumeration is not yet stable.
- `GetMessages` works with the provided session fields from cURL.
- This client uses reverse-engineered web endpoints, not the official OpenAPI.

## Pitfalls

- **904 stale session**: The most common failure. `sessionId` from cURL is often stale. Always let the client refresh it from response.
- **Cookie expiry**: Cookies expire. When 904 persists after refresh, re-capture cookies from DevTools.
- **Message chain**: `previousMessageId` and `statusVersion` must be updated after each send. The client persists them automatically.
- **Text vs file**: Text messages set `content` directly. File messages set `content=""` and use `fileInfo`.

## Scripts

- `scripts/fxiaoke_client.py` — main client: get_messages, send_text, send_file, upload, status, refresh.
- `scripts/capture_helper.py` — guided cURL capture wizard.
- `references/fxiaoke_session_template.json` — template for manual config.
- `references/fxiaoke-api-reference.md` — endpoint specs and notes.
