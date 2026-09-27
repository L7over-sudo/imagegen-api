---
name: imagegen-api
description: 用用户自建的生图 API 生成图片，不消耗 WorkBuddy 积分。当用户要求生成图片、插画、封面配图，并希望走自定义 API 而非内置 ImageGen 时使用。支持免 key 的 Pollinations 与任意 OpenAI 兼容生图接口（智谱/通义/SiliconFlow/云雾等），改 config.json 即可切换服务商。
---

# imagegen-api：自定义生图 API

把用户自己的生图接口封装成一条命令。核心脚本 `scripts/generate.py`（纯标准库），服务商配置在根目录 `config.json`。

## 使用方法（Agent 直接执行）

```bash
python "C:/Users/Jay/.workbuddy/skills/imagegen-api/scripts/generate.py" "提示词" --out 输出路径.jpg --size 1024x1024
```

- `--out` 可省略，默认按时间戳存到当前目录
- `--size` 默认取 config.json 的 `default_size`（1024x1024）
- `--provider` 临时切换服务商，默认用 config.json 的 `provider` 字段
- 环境变量 `IMG_API_KEY` 优先于 config 里的 `api_key`
- 手机/云端环境用 `python3` 代替 `python`

成功输出 `OK <绝对路径> <字节数> <格式>`，失败输出 `ERROR: 原因`。出图后把路径用 present_files 展示给用户。

## 切换服务商

编辑 `config.json`，`provider` 字段决定默认用哪个。支持三种模式：

| type | 适用接口 | 已配置的 provider |
|---|---|---|
| `url` | GET 一个 URL 直接回图片 | `pollinations`（免 key） |
| `openai` | OpenAI images 同步接口（b64/url 返回） | `openai_compatible`（SiliconFlow/智谱/通义/中转） |
| `task` | 异步任务制：POST 建任务 → 轮询查结果 | `hfsy`（gpt-image-2，已填域名路径，只差 key） |

当前默认 `provider` 是 `hfsy`。key 没填时会返回 401，此时改用 `--provider pollinations` 出图，或提醒用户补 key。

`task` 模式关键参数：`base_url`、`create_endpoint`、`query_endpoint`、`query_method`（GET/POST，按接口实际要求）、`api_key`、`size_mode`（`pixels` 传 1024x1024，`label` 传 1K/2K/4K）、`size_labels`（档位映射）、`poll_interval`、`poll_timeout`、`extra_payload`、`create_headers` / `query_headers`（非 Bearer 鉴权时用）。

## 图生图（参考图）

接口支持参考图时（如 hfsy 的 gpt-image-2，最多 6 张），加 `--ref` 传图片 URL：

```bash
python generate.py "把背景换成雪景" --ref https://xxx.jpg https://yyy.png
```

注意 `reference_images` 只接受 URL，不接受本地文件路径。本地图要先传成可访问的链接。

尺寸参数支持两种写法：`--size 1024x1024`（像素）或 `--size 2K`（档位）。

响应字段名不确定时不用怕：脚本会递归匹配 `task_id`、`b64_json`、`url`、`image_url` 等常见键，还会兜底扫全量字符串里的图片链接。真拿不到会打印原始响应，照提示补 `extra_payload` 即可。

常见服务商的 base_url 和 model 参考 `references/providers.md`，以各家官方文档为准。

## 手机端

本 skill 装在电脑本地，手机小程序调用不到。手机端用法：把技能文件夹推到 GitHub 私有仓库，在小程序对话框里发送安装指令装一份云端副本（仓库版打包在 imagegen-api-github 目录，含 README 安装说明）。

## 注意

- config.json 一旦填入真实 api_key，不要把技能目录原样传到公开仓库；GitHub 版保持占位符，或改用中转服务藏 key
- 脚本只依赖标准库，Windows/macOS/Linux/云端沙箱都能跑
- 服务商报错时，ERROR 信息会带响应开头内容，先看服务商说了什么再排查
