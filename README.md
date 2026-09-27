# imagegen-api

把任意生图 API 封装成 WorkBuddy 技能，一条命令出图，不消耗 WorkBuddy 积分。

## 功能

- 三种接口模式：`url`（GET 直出，如 Pollinations，免 key）、`openai`（OpenAI images 同步格式）、`task`（异步任务制：建任务 + 轮询查询，如 hfsyapi 的 gpt-image-2）
- 支持参考图（图生图）：`--ref <URL>`，最多 6 张
- 尺寸支持像素（`1024x1024`）与档位（`2K`）两种写法
- 仅标准库，无第三方依赖；网络抖动自动重试 3 次

## 用法

```bash
python scripts/generate.py "提示词" --out out.jpg --size 1024x1024
python scripts/generate.py "提示词" --provider openai_compatible
python scripts/generate.py "把背景换成雪景" --ref https://xxx.jpg
```

成功输出 `OK <路径> <字节数> <格式>`。

## 电脑端安装

把整个文件夹放到 `~/.workbuddy/skills/imagegen-api/`，重启对话即可被自动发现。

或者：在电脑端对话框里说“帮我安装这个 zip”并附上本仓库的压缩包（本地上传只支持电脑端）。

## 手机端（微信小程序）安装

手机端读不到电脑本地技能，必须装一份云端副本，走 GitHub 导入：

1. 本仓库必须保持**公开**（私有仓库手机端的云端沙箱取不到）
2. 微信打开 WorkBuddy 小程序，在对话框里直接说：

```text
帮我安装 github.com/L7over-sudo/imagegen-api
```

3. 等约 30 秒装完，技能列表里会出现 `imagegen-api`
4. 装完后补 key（同样在小程序里说）：

```text
把 imagegen-api 技能里 config.json 的 api_key 改成 sk-你的真实key
```

5. 之后直接说“生成一张 xx 的图”即可

注意：公开仓库里的 `config.json` 必须保持占位符 key，真实 key 装完再在对话里补。手机端和电脑端是两份独立副本，改内容要分别维护。

## 配置

编辑 `config.json`：

- `provider`：默认服务商，当前为 `hfsy`（异步任务制）
- `hfsy`：已填好 base_url、接口路径、model（`gpt-image-2`），**只需补 `api_key`**
- `openai_compatible`：填 `base_url`（到 /v1 为止）、`api_key`、`model`
- `pollinations`：免 key 直连，作为备胎保留，用 `--provider pollinations` 切换

常见服务商参数见 `references/providers.md`。

## 已实测记录

hfsyapi 的接口文档有一处错误，已在本项目中修正：

```text
GET  /v1/image/query/{task_id}     ← 实际可用（本文档采用）
POST /v1/image/query/{task_id}     ← 文档 curl 示例写的，实测 404
```

接口要点：

- 创建：`POST /v1/image/create`，鉴权 `Authorization: Bearer sk-xxx`
- body：`model`、`prompt`（必填，最长 5000 字）、`size`、`reference_images`（可选，图片 URL 数组，最多 6 张）
- 完成响应：`{"status":"completed","images":[{"url":"https://file.hfsyapi.cn/...png"}]}`
- 单张约 25 秒，状态流转 `queued → in_progress → completed`

## 安全提醒

- 填入真实 api_key 后不要推到公开仓库
- 更稳妥的做法：用云函数把 API 中转一层，key 藏在云端，仓库里只留中转地址
