# 常见生图服务商配置参考

三种模式按接口形态选：同步返回选 `openai`，GET 直出选 `url`，先建任务再查结果的选 `task`。

## 异步任务制接口（type: task）

适用于「POST 创建任务 → 轮询查询结果」的接口。

### hfsyapi（gpt-image-2，当前默认 provider）

已实测可用配置：

```json
{
  "provider": "hfsy",
  "providers": {
    "hfsy": {
      "type": "task",
      "base_url": "https://www.hfsyapi.cn",
      "create_endpoint": "https://www.hfsyapi.cn/v1/image/create",
      "query_endpoint": "https://www.hfsyapi.cn/v1/image/query/{task_id}",
      "query_method": "GET",
      "model": "gpt-image-2",
      "api_key": "sk-xxxxx",
      "size_mode": "pixels",
      "poll_interval": 4,
      "poll_timeout": 300
    }
  }
}
```

接口要点：

- 创建：`POST /v1/image/create`，鉴权 `Authorization: Bearer sk-xxx`，body 为 `model`、`prompt`（必填，最长 5000 字）、`size`、`reference_images`（可选，图片 URL 数组，最多 6 张）
- 查询：**必须用 `GET /v1/image/query/{task_id}`**。官方文档的 curl 示例写成了 POST，实测 POST 返回 404 `Invalid URL`，GET 才通
- 创建响应：`{"id":"task_xxxxx","object":"image.task","model":"gpt-image-2","status":"queued","images":[],"error":null}`
- 完成响应：`{"status":"completed","finished_at":...,"images":[{"url":"https://file.hfsyapi.cn/...png","revised_prompt":"..."}],"error":null}`
- 状态取值：`queued` → `in_progress` → `completed`，实测单张约 25 秒
- 尺寸：文档正文写「尺寸可选 1K」，但实际传 `1024x1024` 可用（`size_mode: pixels`）；若将来报尺寸错误就改 `label`
- 提示词支持中文，返回的 `revised_prompt` 会回显润色后的提示词

### 其他任务制接口

```json
{
  "type": "task",
  "base_url": "https://接口域名",
  "api_key": "你的key",
  "query_method": "GET 或 POST（按文档）",
  "create_endpoint": "https://接口域名/v1/image/create",
  "query_endpoint": "https://接口域名/v1/image/query/{task_id}",
  "size_mode": "pixels 或 label",
  "size_labels": { "1K": 1152, "2K": 2304, "4K": 4608 },
  "poll_interval": 3,
  "poll_timeout": 300,
  "extra_payload": {}
}
```

- `create_endpoint` / `query_endpoint` 不填时，按 `base_url` 自动拼 `/v1/image/create` 与 `/v1/image/query/{task_id}`
- 鉴权默认 `Authorization: Bearer <key>`；接口要求别的头时加 `create_headers` / `query_headers`
- 响应字段名不确定也没事，脚本会递归匹配 `id` / `task_id` / `url` / `image_url` / `b64_json` 等常见键，并兜底扫全量字符串里的图片链接

## OpenAI 兼容同步接口（type: openai）

填 `base_url`（到 /v1 为止，脚本自动拼 `/images/generations`），再加 `api_key` 和 `model`。

### SiliconFlow（硅基流动，有免费额度）

```json
{
  "type": "openai",
  "base_url": "https://api.siliconflow.cn/v1",
  "api_key": "sk-xxx",
  "model": "Kwai-Kolors/Kolors"
}
```

### 智谱 BigModel（CogView-3-Flash 免费）

```json
{
  "type": "openai",
  "base_url": "https://open.bigmodel.cn/api/paas/v4",
  "api_key": "xxx",
  "model": "cogview-3-flash"
}
```

### 通义万相 / DashScope

兼容模式地址：`https://dashscope.aliyuncs.com/compatible-mode/v1`，model 如 `wanx2.1-t2i-turbo`。注意万相部分模型走异步任务接口，兼容模式支持情况以阿里云文档为准，不行就用中转聚合服务或改成 `task` 模式。

### 聚合中转（云雾、OpenRouter 风格）

绝大多数聚合站都是 OpenAI 兼容格式，`base_url` 换成它们给的地址、`model` 换成站内模型名即可。

## URL 直出（type: url）

```json
{
  "provider": "pollinations",
  "providers": {
    "pollinations": {
      "type": "url",
      "url_template": "https://image.pollinations.ai/prompt/{prompt}?width={width}&height={height}&nologo=true&seed={seed}"
    }
  }
}
```

适用于任何「GET 一个 URL 直接回图片」的服务，`url_template` 可用占位符：`{prompt}` `{width}` `{height}` `{seed}` `{model}`。

## 注意

- 各家对 `size` 的支持不同，报错就换成该服务商文档里列出的尺寸
- 以上信息为 2026-09 整理，地址和模型名可能变动，以官方文档为准
- key 不要提交到公开仓库
