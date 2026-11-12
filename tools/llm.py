#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一调用免费 LLM，不用装任何 SDK，只用标准库。
改一行就换平台。

用法：
    export LLM_KEY=你的key
    export LLM_BASE=https://open.bigmodel.cn/api/paas/v4
    export LLM_MODEL=glm-4-flash
    python3 llm.py "你好"

或者代码里：
    from llm import chat
    print(chat("写一句诗", platform="zhipu"))
"""
import json
import os
import sys
import urllib.request
import urllib.error

# 平台预设：id -> (base_url, 默认模型, 环境变量名)
PRESETS = {
    "zhipu":       ("https://open.bigmodel.cn/api/paas/v4", "glm-4-flash", "ZHIPU_KEY"),
    "siliconflow": ("https://api.siliconflow.cn/v1", "Qwen/Qwen2.5-7B-Instruct", "SILICONFLOW_KEY"),
    "dashscope":   ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-turbo", "DASHSCOPE_KEY"),
    "xfyun":       ("https://spark-api-open.xf-yun.com/v1", "lite", "XFYUN_KEY"),
    "qianfan":     ("https://qianfan.baidubce.com/v2", "ernie-speed-128k", "QIANFAN_KEY"),
    "deepseek":    ("https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_KEY"),
    "groq":        ("https://api.groq.com/openai/v1", "llama-3.1-8b-instant", "GROQ_KEY"),
    "cerebras":    ("https://api.cerebras.ai/v1", "llama3.1-8b", "CEREBRAS_KEY"),
    "openrouter":  ("https://openrouter.ai/api/v1", "meta-llama/llama-3.2-3b-instruct:free", "OPENROUTER_KEY"),
    "google":      ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash", "GOOGLE_KEY"),
    "mistral":     ("https://api.mistral.ai/v1", "open-mistral-nemo", "MISTRAL_KEY"),
}


def chat(prompt, platform=None, key=None, model=None, system=None, max_tokens=512,
         temperature=0.7, timeout=60, history=None):
    """返回模型回复的纯文本。出错抛 RuntimeError，带可读原因。"""
    platform = platform or os.environ.get("LLM_PLATFORM", "zhipu")

    if platform in PRESETS:
        base, dmodel, env = PRESETS[platform]
    else:
        base = os.environ.get("LLM_BASE", "")
        dmodel, env = "", "LLM_KEY"
        if not base:
            raise RuntimeError("未知平台 %r，也没设 LLM_BASE 环境变量" % platform)

    key = key or os.environ.get(env) or os.environ.get("LLM_KEY") or ""
    model = model or os.environ.get("LLM_MODEL") or dmodel

    if not key:
        raise RuntimeError("缺少 key。设环境变量 %s=你的key，或调用时传 key=" % env)
    if not model:
        raise RuntimeError("缺少模型名。传 model= 或设 LLM_MODEL")

    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    if history:
        msgs.extend(history)
    msgs.append({"role": "user", "content": prompt})

    body = json.dumps({
        "model": model,
        "messages": msgs,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
            "User-Agent": "llm-client/1.0",
        })

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read()[:500].decode("utf-8", "ignore")
        hint = {
            400: "模型名可能不存在，或者参数不被支持",
            401: "key 无效 / 没带 Authorization 头 / key 过期",
            402: "余额不足",
            403: "该 key 没有这个模型的权限，或 IP 被风控",
            404: "base_url 路径错了，检查是否少 / 多了 /v1",
            429: "限速或额度用完，等一会，或换平台",
        }.get(e.code, "服务端错误")
        raise RuntimeError("HTTP %d（%s）\n平台=%s 模型=%s\n返回：%s"
                           % (e.code, hint, platform, model, raw))
    except Exception as e:
        raise RuntimeError("连不上 %s：%s\n检查是否需要代理，或跑 llm-test.py 诊断" % (base, e))

    try:
        return d["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise RuntimeError("返回格式异常：%s" % json.dumps(d, ensure_ascii=False)[:400])


def main():
    if len(sys.argv) < 2:
        print("用法: python3 llm.py \"你的问题\" [平台id]")
        print("平台: " + ", ".join(PRESETS))
        return
    prompt = sys.argv[1]
    platform = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        print(chat(prompt, platform=platform))
    except RuntimeError as e:
        print("[失败] " + str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
