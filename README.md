# fxiaoke-api

通过 **纷享销客 Web API** 发送/接收消息与文件，不依赖浏览器 UI 自动化。

## 能力范围

- 发送文本消息：`SendMessage`
- 发送文件消息：`UploadByStream` + `SendMessage`
- 读取聊天记录：`GetMessages` / `GetReverseMessages`
- 拉取会话列表：`GetSessionList` / `checkUpdatedAsyncV2`
- 监听更新：`checkUpdatedAsyncV2`

## 环境准备

- Python >= 3.11
- 已登录的 Edge 浏览器会话：`https://www.fxiaoke.com/XV/UI/Home`
- 通过 Edge DevTools 捕获 `SendMessage` / `UploadByStream` 的 cURL

## 会话配置

运行状态保存在 `fxiaoke_session.json`，核心字段：

- `cookies`
- `send_url`
- `upload_url`
- `session_id`
- `previous_message_id`
- `status_version`
- `ep_tag`

模板：`references/fxiaoke_session_template.json`

## 快速开始

```bash
python scripts/fxiaoke_client.py --session fxiaoke_session.json status
python scripts/fxiaoke_client.py --session fxiaoke_session.json get_messages --limit 20
python scripts/fxiaoke_client.py --session fxiaoke_session.json send_text --text "hello"
python scripts/fxiaoke_client.py --session fxiaoke_session.json send_file --file "C:\path\to\file.xlsx"
```

## 目录结构

```
scripts/fxiaoke_client.py        # 主客户端
scripts/capture_helper.py        # cURL 捕获向导
references/fxiaoke-api-reference.md
references/fxiaoke_session_template.json
```

## 已知限制

- `GetSessionList` 在当前 cookie/trace 组合下可能返回 904，优先使用 `checkUpdatedAsyncV2` 的 `value.sessionList` 代替。
- 未做官方 OpenAPI 接入，基于 Web 端点反向集成，变更时需重新捕获 cURL。

## 常见问题

- **904**：`sessionId` 过期。重新捕获 cURL 并更新 `fxiaoke_session.json`，或运行 `refresh` 从 Edge 拉取最新 cookies。
- **消息链**：每次发送后需更新 `previousMessageId`、`statusVersion`、`sessionId`，客户端已自动持久化。
