#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用文生图命令行脚本（imagegen-api skill）

三种模式（config.json 里 providers.<名字>.type）:
  url    : GET 一个模板 URL，直接返回图片字节（如 pollinations）
  openai : OpenAI images 接口格式，同步返回 b64_json 或 url
  task   : 异步任务制，POST 创建任务 → 轮询查询结果（如 gpt-image-2.5-flare）

用法:
  python generate.py "提示词" --out out.jpg --size 1024x1024
  python generate.py "提示词" --provider flare --size 2K

配置: 技能根目录 config.json；环境变量 IMG_API_KEY 优先于配置里的 api_key。
仅用标准库，无第三方依赖。
"""
import argparse
import base64
import datetime
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RETRYABLE_CODES = {429, 500, 502, 503, 504}


def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def find_config(explicit):
    candidates = []
    if explicit:
        candidates.append(explicit)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "..", "config.json"))
    candidates.append(os.path.join(here, "config.json"))
    candidates.append("config.json")
    for c in candidates:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    fail("找不到 config.json，用 --config 指定路径")


def sniff(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def with_retry(fetch, attempts=3, base_delay=2.0):
    last = None
    for i in range(attempts):
        try:
            return fetch()
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read()[:200].decode("utf-8", "ignore")
            except Exception:
                pass
            last = "HTTP %s %s" % (e.code, body)
            if e.code in RETRYABLE_CODES and i < attempts - 1:
                time.sleep(base_delay * (i + 1))
                continue
            fail(last)
        except Exception as e:
            last = str(e)
            if i < attempts - 1:
                time.sleep(base_delay * (i + 1))
                continue
            fail("网络请求失败: " + last)


def _headers(api_key, extra=None):
    h = {"User-Agent": "Mozilla/5.0"}
    if api_key:
        h["Authorization"] = "Bearer " + api_key
    if extra:
        h.update(extra)
    return h


def http_get(url, timeout=180, api_key=None, headers=None):
    h = _headers(api_key, headers)

    def fetch():
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    return with_retry(fetch)


def http_get_json(url, timeout=180, api_key=None):
    raw = http_get(url, timeout=timeout, api_key=api_key)
    try:
        return json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        fail("查询接口返回的不是 JSON: " + raw[:300].decode("utf-8", "ignore"))


def http_post_json(url, payload=None, api_key=None, timeout=180, headers=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    h = _headers(api_key, headers)
    h["Content-Type"] = "application/json"

    def fetch():
        req = urllib.request.Request(url, data=body, headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))

    return with_retry(fetch)


# ---------- 响应字段模糊匹配（应对文档不全的情况） ----------

def _iter_strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            for s in _iter_strings(v):
                yield s
    elif isinstance(obj, list):
        for v in obj:
            for s in _iter_strings(v):
                yield s
    elif isinstance(obj, str):
        yield obj


def _deep_find(obj, keys):
    keys = {k.lower() for k in keys}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (str, int)) and k.lower() in keys:
                return v
        for v in obj.values():
            r = _deep_find(v, keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_find(v, keys)
            if r is not None:
                return r
    return None


def extract_task_id(resp):
    v = _deep_find(resp, {"task_id", "taskid", "task_no", "id"})
    if v is None:
        fail("创建任务的响应里找不到 task_id: " + json.dumps(resp, ensure_ascii=False)[:400])
    return str(v)


def extract_image(resp):
    b64 = _deep_find(resp, {"b64_json", "b64", "image_base64", "imagebase64", "base64"})
    if isinstance(b64, str) and len(b64) > 200:
        return base64.b64decode(b64)
    url = _deep_find(resp, {"image_url", "imageurl", "url", "image", "img", "output"})
    if isinstance(url, str) and url.startswith("http"):
        return http_get(url)
    for s in _iter_strings(resp):
        if s.startswith("http") and re.search(r"\.(png|jpe?g|webp|gif)(\?|$)", s, re.I):
            return http_get(s)
    return None


def size_label(w, h, p):
    """异步任务接口常用 1K/2K/4K 这类档位，把像素映射成档位。"""
    if p.get("size_labels"):
        labels = p["size_labels"]
    else:
        labels = {"1K": 1152, "2K": 2304, "4K": 4608}
    m = max(w, h)
    best = None
    for name, limit in sorted(labels.items(), key=lambda kv: kv[1]):
        if m <= limit:
            best = name
            break
    return best or sorted(labels.keys())[-1]


# ---------- 三种模式 ----------

def gen_url(p, prompt, w, h):
    seed = random.randint(1, 10 ** 9)
    url = p["url_template"].format(
        prompt=urllib.parse.quote_plus(prompt),
        width=w, height=h, seed=seed,
        model=urllib.parse.quote_plus(p.get("model", "")),
    )
    return http_get(url, api_key=p.get("api_key"))


def gen_openai(p, prompt, w, h):
    if "endpoint" in p:
        endpoint = p["endpoint"]
    else:
        base = p.get("base_url", "").rstrip("/")
        if not base:
            fail("openai 模式缺少 base_url（填到 /v1 为止）或直接给 endpoint")
        endpoint = base + "/images/generations"
    payload = {"model": p.get("model", ""), "prompt": prompt, "n": 1, "size": "%dx%d" % (w, h)}
    payload.update(p.get("extra_payload", {}))
    resp = http_post_json(endpoint, payload, api_key=p.get("api_key"))
    if isinstance(resp, dict) and resp.get("error"):
        fail("API 返回错误: " + json.dumps(resp["error"], ensure_ascii=False)[:400])
    arr = resp.get("data") or []
    if not arr:
        fail("响应里没有 data 数组: " + json.dumps(resp, ensure_ascii=False)[:400])
    item = arr[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        return http_get(item["url"])
    fail("data[0] 里既没有 b64_json 也没有 url: " + json.dumps(item, ensure_ascii=False)[:400])


def gen_task(p, prompt, w, h):
    base = p.get("base_url", "").rstrip("/")
    if not base and "create_endpoint" not in p:
        fail("task 模式缺少 base_url 或 create_endpoint")
    create_url = p.get("create_endpoint") or (base + "/v1/image/create")
    query_url = p.get("query_endpoint") or (base + "/v1/image/query/{task_id}")

    if p.get("size_mode", "label") == "label":
        size_val = size_label(w, h, p)
    else:
        size_val = "%dx%d" % (w, h)

    payload = {"prompt": prompt, "size": size_val}
    if p.get("model"):
        payload["model"] = p["model"]
    if p.get("_ref"):
        payload["reference_images"] = p["_ref"]
    payload.update(p.get("extra_payload", {}))

    resp = http_post_json(create_url, payload, api_key=p.get("api_key"),
                          headers=p.get("create_headers"))
    if isinstance(resp, dict) and resp.get("error"):
        fail("创建任务失败: " + json.dumps(resp["error"], ensure_ascii=False)[:400])
    task_id = extract_task_id(resp)
    print("task_id=%s 已提交（size=%s），开始轮询..." % (task_id, size_val), file=sys.stderr)

    interval = float(p.get("poll_interval", 3))
    timeout_s = float(p.get("poll_timeout", 300))
    method = str(p.get("query_method", "GET")).upper()
    t0 = time.time()
    qresp = None
    last_note = ""
    while time.time() - t0 < timeout_s:
        time.sleep(interval)
        qurl = query_url.format(task_id=task_id)
        if method == "POST":
            qresp = http_post_json(qurl, None, api_key=p.get("api_key"),
                                   headers=p.get("query_headers"))
        else:
            qresp = http_get_json(qurl, api_key=p.get("api_key"))
        data = extract_image(qresp)
        if data:
            return data
        st = _deep_find(qresp, {"status", "state", "task_status"})
        note = str(st) if st is not None else json.dumps(qresp, ensure_ascii=False)[:120]
        if note != last_note:
            print("轮询中: %s" % note, file=sys.stderr)
            last_note = note
        err = _deep_find(qresp, {"error", "errmsg"})
        if isinstance(st, str) and st.lower() in ("failed", "fail", "error"):
            fail("任务失败: " + json.dumps(qresp, ensure_ascii=False)[:400])
        if err and str(err).lower() not in ("none", "null", ""):
            fail("任务出错: %s" % str(err)[:300])
    fail("轮询超时（%ss）: %s" % (timeout_s, json.dumps(qresp, ensure_ascii=False)[:400] if qresp else "无响应"))


MODES = {"url": gen_url, "openai": gen_openai, "task": gen_task}


def main():
    ap = argparse.ArgumentParser(description="imagegen-api: 自定义生图 API 命令行")
    ap.add_argument("prompt", help="生图提示词")
    ap.add_argument("--out", default=None, help="输出文件路径")
    ap.add_argument("--size", default=None, help="宽x高（如 1024x1024）或档位（如 2K）")
    ap.add_argument("--provider", default=None, help="临时指定服务商（默认取 config.json 的 provider）")
    ap.add_argument("--config", default=None, help="config.json 路径（默认自动查找）")
    ap.add_argument("--ref", nargs="*", default=None, help="参考图 URL 列表（图生图用，最多 6 张）")
    a = ap.parse_args()

    cfg_path = find_config(a.config)
    try:
        cfg = json.load(open(cfg_path, encoding="utf-8"))
    except Exception as e:
        fail("config.json 解析失败: %s" % e)

    name = a.provider or cfg.get("provider")
    providers = cfg.get("providers", {})
    if name not in providers:
        fail("config.json 里没有 provider: %s（现有: %s）" % (name, ", ".join(providers)))
    p = dict(providers[name])
    env_key = os.environ.get("IMG_API_KEY")
    if env_key:
        p["api_key"] = env_key
    if a.ref:
        p["_ref"] = a.ref[:6]

    size = str(a.size or cfg.get("default_size", "1024x1024")).strip()
    m = re.match(r"^(\d{2,5})\s*[xX*]\s*(\d{2,5})$", size)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
    elif re.match(r"^\d+[kK]$", size):
        base_px = int(size[:-1]) * 1024
        w = h = base_px
    else:
        fail("size 格式应为 宽x高（1024x1024）或档位（1K/2K/4K）")

    mode = p.get("type")
    if mode not in MODES:
        fail("未知 type: %s（支持 %s）" % (mode, " / ".join(MODES)))

    try:
        data = MODES[mode](p, a.prompt, w, h)
    except SystemExit:
        raise
    except Exception as e:
        fail("生成失败: " + repr(e))

    kind = sniff(data)
    if not kind:
        fail("返回内容不是图片。响应开头: " + data[:300].decode("utf-8", "ignore"))

    out = a.out or ("imagegen_%s.%s" % (datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), kind))
    out = os.path.abspath(out)
    with open(out, "wb") as f:
        f.write(data)
    print("OK %s %d %s" % (out, len(data), kind))


if __name__ == "__main__":
    main()
