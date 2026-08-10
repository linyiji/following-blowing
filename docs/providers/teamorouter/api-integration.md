TeamoRouter 支持 **OpenAI**、**Google Gemini**、**Anthropic** 多种兼容格式接口。你可以把官方 SDK 的 base URL 指向 TeamoRouter，无需改动业务代码，即可调用 Claude / Gemini / GPT 等多家模型。

- **Base URL**：`https://api.teamorouter.com`
- **鉴权**：API Key（`provider-issued`）
- **协议**：同时支持 Anthropic 原生格式（`/v1/messages`）、OpenAI 兼容格式（`/v1/chat/completions`）、OpenAI Responses API（`/v1/responses`，仅 GPT 系列）、Gemini 原生格式（`/v1beta/models/{model}:generateContent`）和图像生成（`/v1/images`）

文中的 `YOUR_API_KEY` 请替换为你自己的 Key，妥善保管、不要提交到代码仓库。

---

## **一、Base URL 与请求头**

根据使用的模型选择对应的兼容格式：

**全部模型**

**OpenAIAnthropicGoogle**

不同格式的鉴权 Header 不同，按使用的协议选择：


| **协议**    | **Header**                                                     |
| --------- | -------------------------------------------------------------- |
| Anthropic | `x-api-key: YOUR_API_KEY` + `anthropic-version: 2023-06-01` |
| OpenAI    | `Authorization: Bearer YOUR_API_KEY`                        |
| Gemini    | `Authorization: Bearer YOUR_API_KEY`                        |


---

## **二、可用模型**

通过 `GET /v1/models` 实时拉取完整列表：

BASH复制

```bash
curl https://api.teamorouter.com/v1/models \
  -H "Authorization: Bearer YOUR_API_KEY"

```

当前主要模型（节选）：


| **厂商**    | **模型 ID**                                                                                                                                       |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Anthropic | `claude-fable-5`、`claude-opus-5`、`claude-sonnet-5`、`claude-opus-4-8`、`claude-opus-4-7`、`claude-opus-4-6`、`claude-sonnet-4-6`、`claude-haiku-4-5` |
| OpenAI    | `gpt-5.6-sol`、 `gpt-5.6-terra`、 `gpt-5.6-luna`、 `gpt-5.5`、 `gpt-5.4`、 `gpt-5.4-mini`、 `gpt-image-2`                                             |
| Google    | `gemini-3.6-flash`、`gemini-3.5-flash-lite`、`gemini-3.1-pro-preview`、`gemini-3.5-flash`、`gemini-3.1-flash-lite-preview`                          |
| Kimi      | `kimi-k3`                                                                                                                                       |
| DeepSeek  | `deepseek-v4-pro`、`deepseek-v4-flash`、`deepseek-v4-flash-free`（免费版）                                                                             |
| GLM       | `glm-5.2`                                                                                                                                       |


---

## **三、Anthropic 原生格式**

端点：`POST /v1/messages`

### **3.1 基础请求**

BASH复制

```bash
curl https://api.teamorouter.com/v1/messages \
  -H "x-api-key: YOUR_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-fable-5",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "用一句话介绍你自己"}
    ]
  }'

```

返回（节选）：

JSON复制

```json
{
  "id": "msg_01KxDE...",
  "type": "message",
  "role": "assistant",
  "model": "claude-fable-5",
  "content": [{"type": "text", "text": "我是 Claude……"}],
  "stop_reason": "end_turn",
  "usage": {"input_tokens": 159, "output_tokens": 34}
}

```

### **3.2 流式（SSE）**

加 `"stream": true`，响应为 `text/event-stream`：

BASH复制

```bash
curl https://api.teamorouter.com/v1/messages \
  -H "x-api-key: YOUR_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-fable-5",
    "max_tokens": 1024,
    "stream": true,
    "messages": [{"role": "user", "content": "写一首五言绝句"}]
  }'

```

事件序列：`message_start` → `content_block_start` → 多个 `content_block_delta` → `content_block_stop` → `message_delta` → `message_stop`。

### **3.3 Python SDK（anthropic）**

PYTHON复制

```python
from anthropic import Anthropic

client = Anthropic(
    api_key="YOUR_API_KEY",
    base_url="https://api.teamorouter.com",
)

resp = client.messages.create(
    model="claude-fable-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.content[0].text)

```

---

## **四、OpenAI 兼容格式**

端点：`POST /v1/chat/completions`（Chat Completions）与 `POST /v1/responses`（Responses API，仅 GPT 系列）

### **4.1 Chat Completions 基础请求**

BASH复制

```bash
curl https://api.teamorouter.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello"}]
  }'

```

返回为标准 OpenAI `chat.completion` 结构：

JSON复制

```json
{
  "object": "chat.completion",
  "model": "gpt-5.6-sol",
  "choices": [
    {"index": 0, "message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}
  ],
  "usage": {"prompt_tokens": 214, "completion_tokens": 3, "total_tokens": 217}
}

```

### **4.2 Python SDK（openai）**

PYTHON复制

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://api.teamorouter.com/v1",
)

resp = client.chat.completions.create(
    model="gpt-5.6-sol",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)

```

### **4.3 流式**

加 `"stream": true`，返回标准 OpenAI SSE（`data: {...}` 分片，以 `data: [DONE]` 结束）。

### **4.4 Responses API 基础请求**

如果你的应用已经迁移到 OpenAI Responses API，可以直接调用 `/v1/responses`：

BASH复制

```bash
curl https://api.teamorouter.com/v1/responses \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-5.6-sol",
    "input": "用一句话介绍 TeamoRouter"
  }'

```

`/v1/responses` 仅支持 GPT 系列模型，请求 Claude / Gemini 会直接返回 400。Claude 请走 `/v1/messages`，Gemini 请走 Gemini 原生格式。

### **4.5 Python SDK（openai responses）**

PYTHON复制

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://api.teamorouter.com/v1",
)

resp = client.responses.create(
    model="gpt-5.6-sol",
    input="用一句话介绍 TeamoRouter",
)
print(resp.output_text)

```

### **4.6 Responses API 流式**

加 `"stream": true`，返回 OpenAI Responses API 的标准流式事件。

### **4.7 快速模式（Fast mode）**

TeamoRouter 的 OpenAI 兼容接口支持快速模式（Fast mode，原名 Priority processing）。在 Chat Completions 或 Responses API 请求中加入：

JSON复制

```json
"service_tier": "fast"

```

Python 示例：

PYTHON复制

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://api.teamorouter.com/v1",
)

resp = client.responses.create(
    model="gpt-5.6-sol",
    input="帮我分析这个需求",
    service_tier="fast",
)
print(resp.output_text)

```

JavaScript 示例：

JAVASCRIPT复制

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "YOUR_API_KEY",
  baseURL: "https://api.teamorouter.com/v1",
});

const resp = await client.responses.create({
  model: "gpt-5.6-sol",
  input: "帮我分析这个需求",
  service_tier: "fast",
});
console.log(resp.output_text);

```

旧写法仍然兼容：

JSON复制

```json
"service_tier": "priority"

```

`fast` 为当前推荐写法，旧值 `priority` 同样有效，两者效果相同，适用于所有支持快速模式的 GPT 系列模型。`gpt-5.6-sol` 开启后最高可达标准速度的 2.5 倍。快速模式按标准价 2 倍计费。对于 GPT-5.6 及更早模型，响应对象中的 `service_tier` 可能仍返回 `"priority"`，这是正常现象。

---

## **五、Gemini 原生格式**

端点：`POST /v1beta/models/{model}:generateContent`

### **5.1 基础请求**

BASH复制

```bash
curl https://api.teamorouter.com/v1beta/models/gemini-3.5-flash:generateContent \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "content-type: application/json" \
  -d '{
    "contents": [
      {"role": "user", "parts": [{"text": "用一句话介绍你自己"}]}
    ]
  }'

```

返回（节选）：

JSON复制

```json
{
  "candidates": [
    {
      "content": {"role": "model", "parts": [{"text": "我是 Gemini……"}]},
      "finishReason": "STOP"
    }
  ],
  "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 22, "totalTokenCount": 34}
}

```

### **5.2 流式（SSE）**

使用 `streamGenerateContent`，并加上 `alt=sse`：

BASH复制

```bash
curl "https://api.teamorouter.com/v1beta/models/gemini-3.5-flash:streamGenerateContent?alt=sse" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "content-type: application/json" \
  -d '{
    "contents": [
      {"role": "user", "parts": [{"text": "写一首五言绝句"}]}
    ]
  }'

```

### **5.3 环境变量**

如果你的工具或 SDK 支持自定义 Gemini Base URL，可以按下面方式配置：

BASH复制

```bash
export GOOGLE_GEMINI_BASE_URL="https://api.teamorouter.com"
export GEMINI_API_KEY="YOUR_API_KEY"
export GEMINI_API_KEY_AUTH_MECHANISM="bearer"

```

不同 Gemini SDK 对自定义 endpoint 的字段名可能不同，常见名称包括 `base_url`、`baseURL`、`apiEndpoint` 或环境变量。核心原则：Base URL 指向 `https://api.teamorouter.com`，Key 使用**你的 TeamoRouter API Key**。

---

## **六、图像生成**

图像模型 `gpt-image-2` 使用独立的 `/v1/images` 端点，鉴权为 `Authorization: Bearer`。

### **6.1 生成图像**

端点：`POST /v1/images/generations`

BASH复制

```bash
curl https://api.teamorouter.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "content-type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "一只在键盘上打字的橘猫，插画风格"
  }'

```

返回（节选），`data[0].b64_json` 为 Base64 编码的图片：

JSON复制

```json
{
  "created": 1752345600,
  "data": [
    {"b64_json": "iVBORw0KGgo..."}
  ]
}

```

建议超时时间设置为300秒。生图模型响应时间较长，短于300秒可能调用超时失败

### **6.2 编辑图像**

端点：`POST /v1/images/edits`

以 `multipart/form-data` 上传原图并给出修改指令：

BASH复制

```bash
curl https://api.teamorouter.com/v1/images/edits \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F model="gpt-image-2" \
  -F image="@photo.png" \
  -F prompt="把背景换成星空"

```

接口与 OpenAI Images API 兼容。

---

## **七、在 Agent 工具中接入**

Claude Code 走 Anthropic 协议、Codex 走 OpenAI 协议、Gemini CLI 走 Gemini 协议。

只需用环境变量把 Base URL 和 API Key 指向 TeamoRouter 即可，无需改动工具本身。

**Claude Code（Anthropic 协议）：**

BASH复制

```bash
export ANTHROPIC_BASE_URL="https://api.teamorouter.com"
export ANTHROPIC_API_KEY="YOUR_API_KEY"

```

**OpenAI 协议的工具（Chat Completions / Responses API 均可）：**

BASH复制

```bash
export OPENAI_BASE_URL="https://api.teamorouter.com/v1"
export OPENAI_API_KEY="YOUR_API_KEY"

```

**Gemini CLI：**

BASH复制

```bash
export GOOGLE_GEMINI_BASE_URL="https://api.teamorouter.com"
export GEMINI_API_KEY="YOUR_API_KEY"
export GEMINI_API_KEY_AUTH_MECHANISM="bearer"

```

---

## **八、常见问题**

**出现401报错 / 鉴权失败？**

先核对协议与 Header 的对应关系：Anthropic 用 `x-api-key`，OpenAI / Gemini 用 `Authorization: Bearer`，Gemini 原生端点也接受 `x-goog-api-key`。再确认 Key 复制完整（`provider-issued-` 开头、无多余空格）且未在控制台删除；另外注意 base_url 写法：OpenAI SDK 需要带 `/v1`，Anthropic SDK 不带。

**用 OpenAI 格式调 Claude 报错 / 变贵 / 效果差？**

**Claude 模型请务必使用 Anthropic 原生协议（**`/v1/messages`**）调用**，Claude Code 等 Agent 工具必须按 Anthropic 协议配置。用 OpenAI 兼容格式调用 Claude 可能导致 prompt cache、thinking 等能力丢失（成本更高、能力降级），仅适合简单对话场景；`/v1/responses` 不支持 Claude / Gemini（会返回 400）。

**模型不可用？**

请先用 `GET /v1/models` 拉取实时列表，核对模型 ID 拼写（全小写，留意 `-` 与 `.` 的区别）。同时确认端点与模型的对应关系。

**超时 / 首字慢？**

Opus / Fable 这类大模型在思考阶段首字延迟数秒到数十秒属正常，不代表请求失败。生产环境建议加 `"stream": true` 用流式提升体感，并把客户端读超时调大（服务端支持长达 600 秒的响应）。

**Key 安全**：

放入环境变量或密钥管理服务，切勿硬编码、提交到 Git，或打包进前端 / 客户端对外分发。若怀疑 Key 已泄露，立即在控制台删除该 Key 并新建替换。