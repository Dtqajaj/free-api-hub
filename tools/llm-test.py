#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
免费 LLM 接口一键诊断。
用法：
    python3 llm-test.py                      # 只测网络连通性
    python3 llm-test.py --key 你的key          # 指定平台
    python3 llm-test.py --key sk-xxx --id groq

它会依次检查 4 层，卡在哪层直接告诉你：
    L1 DNS/TCP/TLS   → 通不通
    L2 HTTP 可达      → 路由对不对
    L3 鉴权           → key 有没有效
    L4 推理           → 模型名对不对、额度够不够
"""
import json
import socket
import ssl
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

TIMEOUT = 6
socket.setdefaulttimeout(6)

PLATFORMS = [
    # id, 平台, base_url, 测试模型, 是否OpenAI兼容, 申请地址, 国内直连
    ("zhipu", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash", True,
     "https://open.bigmodel.cn/usercenter/apikeys", "直连"),
    ("siliconflow", "硅基流动", "https://api.siliconflow.cn/v1", "Qwen/Qwen2.5-7B-Instruct", True,
     "https://cloud.siliconflow.cn/account/ak", "直连"),
    ("dashscope", "阿里百炼", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-turbo", True,
     "https://bailian.console.aliyun.com/", "直连"),
    ("xfyun", "讯飞星火", "https://spark-api-open.xf-yun.com/v1", "lite", True,
     "https://console.xfyun.cn/services/cbm", "直连"),
    ("qianfan", "百度千帆", "https://qianfan.baidubce.com/v2", "ernie-speed-128k", True,
     "https://console.bce.baidu.com/qianfan/", "直连"),
    ("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat", True,
     "https://platform.deepseek.com/api_keys", "直连(需充值)"),
    ("groq", "Groq", "https://api.groq.com/openai/v1", "llama-3.1-8b-instant", True,
     "https://console.groq.com/keys", "需代理"),
    ("cerebras", "Cerebras", "https://api.cerebras.ai/v1", "llama3.1-8b", True,
     "https://cloud.cerebras.ai/", "需代理"),
    ("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "meta-llama/llama-3.2-3b-instruct:free", True,
     "https://openrouter.ai/keys", "需代理"),
    ("google", "Google AI Studio", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash", True,
     "https://aistudio.google.com/apikey", "需代理"),
    ("mistral", "Mistral", "https://api.mistral.ai/v1", "open-mistral-nemo", True,
     "https://console.mistral.ai/api-keys/", "需代理"),
]


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def l1(host):
    """DNS + TCP + TLS。"""
    t0 = time.time()
    try:
        socket.getaddrinfo(host, 443, socket.AF_INET)
    except Exception as e:
        return False, "DNS 解析失败: %s" % e, 0
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        s = socket.create_connection((host, 443), timeout=TIMEOUT)
        s = ctx.wrap_socket(s, server_hostname=host)
        s.close()
        return True, "TCP+TLS OK", int((time.time() - t0) * 1000)
    except Exception as e:
        return False, "TCP/TLS 失败: %s" % e, int((time.time() - t0) * 1000)


def l2(base):
    """HTTP 可达性：能收到任何 HTTP 响应就算通。"""
    t0 = time.time()
    try:
        req = urllib.request.Request(base, headers={"User-Agent": "llm-test/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return True, "HTTP %d" % r.status, int((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        # 4xx 说明服务端活着，路由也对
        return True, "HTTP %d（服务在线）" % e.code, int((time.time() - t0) * 1000)
    except Exception as e:
        return False, "无 HTTP 响应: %s" % e, int((time.time() - t0) * 1000)


def l3l4(base, key, model):
    """真的发一次 chat/completions，同时验证 key 和模型名。"""
    url = base.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "说'通'一个字"}],
        "max_tokens": 8,
        "stream": False,
    }).encode()
    t0 = time.time()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
        "User-Agent": "llm-test/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
            msg = d.get("choices", [{}])[0].get("message", {}).get("content", "")
            return True, "推理成功 → %r" % (msg[:40] or "(空)"), int((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        raw = e.read()[:400].decode("utf-8", "ignore")
        return False, "HTTP %d | %s" % (e.code, explain(e.code, raw)), int((time.time() - t0) * 1000)
    except Exception as e:
        return False, "请求失败: %s" % e, int((time.time() - t0) * 1000)


def explain(code, raw):
    m = {
        400: "请求格式错，多半是模型名不存在或参数不支持",
        401: "key 无效 / 过期 / 没带上 Authorization 头",
        402: "余额不足，要充值",
        403: "key 无该模型权限，或 IP 被风控",
        404: "路径错了，检查 base_url 是否少了或多了 /v1",
        413: "请求体太大",
        422: "参数校验失败，看下面原始返回",
        429: "限速或当日额度用完，等一会或换平台",
        500: "服务端挂了，换一家",
        503: "模型过载，重试或换模型",
    }.get(code, "未归类")
    return m + " | " + raw.replace("\n", " ")[:200]


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    only = arg("--id")
    key = arg("--key", "")
    show_all = "--all" in sys.argv

    print("=" * 78)
    print("免费 LLM 接口诊断  |  四层检测：网络 → 路由 → 鉴权 → 推理")
    print("=" * 78)

    targets = [p for p in PLATFORMS if (only is None or p[0] == only)]
    if not targets:
        print("没有匹配的平台 id。可选：", ", ".join(p[0] for p in PLATFORMS))
        return

    # ---------- 第 1 层：网络 ----------
    print("\n[L1] 网络连通性（DNS + TCP + TLS）")
    reachable = []

    def probe_one(p):
        pid, name, base, model, compat, signup, note = p
        host = base.split("//")[1].split("/")[0]
        ok, msg, ms = l1(host)
        return (p, host, ok, msg, ms)

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(probe_one, targets))

    for p, host, ok, msg, ms in results:
        pid, name, base, model, compat, signup, note = p
        print("  %s %-18s %-42s %s (%dms)" % ("OK  " if ok else "FAIL", name, host, msg, ms))
        if ok:
            reachable.append(p)
        else:
            print("       └─ 这一家需要代理 / 换网络 / 换 DNS，跳过后面检测")

    if not key:
        print("\n[L1 结束] 没给 key，只做网络诊断。")
        print("\n能连的：" + (", ".join(n[1] for n in reachable) or "无"))
        blocked = [p[1] for p in targets if p[1] not in [n[1] for n in reachable]]
        if blocked:
            print("连不上的：" + ", ".join(blocked))
            print("\n下一步：")
            print("  1. 连不上的那几家，换用上面能连的（国内直连的优先）")
            print("  2. 拿到 key 后重跑：python3 llm-test.py --key 你的key --all")
        return

    # ---------- 第 2-4 层：带 key 实测 ----------
    print("\n[L2-L4] 带 key 实测（%d 家）" % len(reachable))
    good = []
    for pid, name, base, model, compat, signup, note in reachable:
        print("\n  ── %s" % name)
        ok2, msg2, ms2 = l2(base)
        print("     L2 路由   %s  %s (%dms)" % ("OK  " if ok2 else "FAIL", msg2, ms2))
        if not ok2:
            continue
        ok3, msg3, ms3 = l3l4(base, key, model)
        print("     L3+L4     %s  %s (%dms)" % ("OK  " if ok3 else "FAIL", msg3, ms3))
        if ok3:
            good.append((name, base, model))

    print("\n" + "=" * 78)
    if good:
        print("跑通的 %d 家，直接抄下面的配置：" % len(good))
        for name, base, model in good:
            print("\n  # %s" % name)
            print("  base_url = %s" % base)
            print("  model    = %s" % model)
    else:
        print("没有一家跑通。按上面的 L2/L3/L4 报错逐条对照修。")
    print("=" * 78)


if __name__ == "__main__":
    main()
