# 纷享销客 Web API Reference

## Verified endpoints

### Upload file
`POST https://www.fxiaoke.com/FSC/EM/File/UploadByStream?...`

Request:
- multipart/form-data
- Key headers: `extension`, `startindex`, `storagepath`, `totallength`, `content-length`
- File field name: `file`

Response:
```json
{
  "TempFileName": "...",
  "FileExtension": "..."
}
```

### Send message
`POST https://www.fxiaoke.com/H/V5Messenger/SendMessage?...`

Request body for **text message**:
```json
{
  "content": "hello",
  "secret": false,
  "sessionId": "...",
  "previousMessageId": 123,
  "epTag": "...",
  "statusVersion": "...",
  "localUniversalDefinitionTimestamp": 1786421644219,
  "localBotDefinitionsTimestamp": 1786352692411
}
```

Request body for **file message**:
```json
{
  "content": "",
  "fileInfo": {
    "value": 3,
    "value1": "TempFileName from upload",
    "value2": fileSize,
    "value3": "display_name.xlsx"
  },
  "secret": false,
  "sessionId": "...",
  "previousMessageId": 123,
  "epTag": "...",
  "statusVersion": "...",
  "localUniversalDefinitionTimestamp": 1786421644219,
  "localBotDefinitionsTimestamp": 1786352692411
}
```

Response:
```json
{
  "value": {
    "currentMessage": {
      "messageId": 987654,
      "content": "..."
    },
    "sessionList": [
      {
        "sessionId": "REAL_SESSION_ID"
      }
    ],
    "statusVersion": "S-9-..."
  }
}
```

## Critical: stale sessionId

The `sessionId` in captured cURLs is often stale. The API may return HTTP 200 with a `messageId`, but the message does not appear in the expected chat. Always refresh `sessionId` from `value.sessionList[0].sessionId` in the response.

Error 904:
```
QixinWebException error code is 904
```
This means `sessionId` is invalid/stale. Re-capture cURL from DevTools.

## Message chain update rules

After every successful send:
- `previousMessageId` ← `value.currentMessage.messageId`
- `statusVersion` ← `value.statusVersion`
- `sessionId` ← `value.sessionList[0].sessionId`

These three values must be persisted and reused for the next send.

## Cookie structure

Required cookies from browser session:
- `fs_token`
- `FSAuthX`
- `FSAuthXC`
- `JSESSIONID`
- `guid`
- `fsRoutes`
- `lang`

Cookies expire. When they do, re-capture from DevTools.

## Get messages / receive

This client currently focuses on send. To add receive capability:

1. Capture a `GetMessages` or session list request from DevTools while browsing a chat.
2. Identify the endpoint, required query params or body (`sessionId`, `page`, `size`, etc.).
3. Add a `get_messages(session_id, limit=20)` method that returns parsed message list.
4. Handle pagination via `previousMessageId` or offset params seen in the captured request.

Known pitfalls:
- Stale `sessionId` also affects reads; same 904 error.
- Some read endpoints use query params instead of JSON body.
- The response schema for messages may include `messageList` or nested `value` objects—verify from actual response.

## Helper: capture cURL from Edge DevTools

1. Open F12 in Edge on `https://www.fxiaoke.com/XV/UI/Home`.
2. Go to Network tab.
3. Manually send a message or upload a file in the target chat.
4. Find `SendMessage` and `UploadByStream` requests.
5. Right-click → Copy → Copy as cURL.
6. Paste into a text editor and extract:
   - Full URL including query string
   - Cookie header values
   - Request body
   - `sessionId`, `previousMessageId`, `epTag`, `statusVersion` from body or response

A helper script `scripts/capture_helper.py` can guide you through this.
