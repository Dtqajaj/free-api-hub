# Free API Hub

把 2387 个免费 API 做成一个**不需要服务器**的查询接口。

GitHub 仓库即是服务器：Pages 当静态文件服务器（无限流量 + 全球 CDN），
Actions 当定时任务服务器（每 6 小时自动抓取更新），raw 直连当可跨域 CDN。

## 现状

| 指标 | 数值 |
|---|---|
| API 总数 | 2387 |
| 免 Key 直连 | 1172 |
| 分类 | 52 |
| 免费 LLM 平台 | 14 |
| 更新频率 | 每 6 小时（GitHub Actions） |
| 成本 | 0 |

## 端点

站点根：`https://<user>.github.io/free-api-hub/`

| 路径 | 内容 | 大小 |
|---|---|---|
| `/api/v1/index.json` | 元信息（总数、更新时间、数据源状态） | <1 KB |
| `/api/v1/apis.json` | 全量 API | 590 KB |
| `/api/v1/nokey.json` | 仅免 Key 的 1172 条 | 290 KB |
| `/api/v1/llm.json` | 免费 LLM 平台额度表 | 7 KB |
| `/api/v1/categories.json` | 分类及每类数量 | 8 KB |
| `/api/v1/category/{slug}.json` | 单分类 | 5-40 KB |
| `/api/v1/stats.json` | 统计（鉴权分布、CORS 数量） | 2 KB |
| `/api/v1/status.json` | 连通性探测结果（Actions 每轮生成） | 100 KB |

raw 直连（带 `Access-Control-Allow-Origin: *`，前端可直接 fetch）：

```
https://raw.githubusercontent.com/<user>/free-api-hub/main/docs/api/v1/nokey.json
```

## 数据结构

```json
{
  "id": "open-meteo",
  "name": "Open-Meteo",
  "url": "https://api.open-meteo.com/v1/forecast",
  "description": "Free weather forecast API for non-commercial use",
  "category": "Weather",
  "auth": "No",
  "https": true,
  "cors": "Yes",
  "source": "public-apis"
}
```

`auth` 为 `"No"` 即无需注册直接调用。`cors` 为 `Yes` 表示浏览器端可跨域直连。

## 三条用法

**1. 当静态数据源**

```bash
curl https://<user>.github.io/free-api-hub/api/v1/nokey.json \
  | jq -r '.[] | select(.category=="Weather") | .url'
```

**2. 前端直接查**

```js
const apis = await fetch('https://<user>.github.io/free-api-hub/api/v1/nokey.json').then(r=>r.json());
const weather = apis.filter(a => a.category === 'Weather' && a.cors === 'Yes');
```

**3. 当自己的 API 后端（Cloudflare Worker 代理）**

静态文件做不了带参数的查询。需要一个动态层时，在 Cloudflare Workers 建一个免费 Worker：

```js
export default {
  async fetch(req) {
    const u = new URL(req.url);
    const q = (u.searchParams.get('q') || '').toLowerCase();
    const cat = u.searchParams.get('category') || '';
    const nokey = u.searchParams.get('nokey') === '1';
    const limit = Math.min(parseInt(u.searchParams.get('limit') || '50'), 500);

    const r = await fetch('https://<user>.github.io/free-api-hub/api/v1/apis.json',
      { cf: { cacheTtl: 3600 } });
    let data = await r.json();

    if (nokey) data = data.filter(a => a.auth === 'No');
    if (cat) data = data.filter(a => a.category === cat);
    if (q) data = data.filter(a => (a.name + a.description + a.category + a.url).toLowerCase().includes(q));

    return new Response(JSON.stringify({
      total: data.length,
      items: data.slice(0, limit)
    }, null, 2), {
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'public, max-age=3600'
      }
    });
  }
};
```

免费额度 10 万请求/天，够用。之后就能这样调：

```
GET https://<worker>.workers.dev/?q=weather&nokey=1&limit=10
```

## 本地运行

```bash
python3 scripts/build.py --offline   # 用本地缓存生成
python3 scripts/check.py --limit 100 # 探测前 100 个
python3 -m http.server 8000 --directory docs
# 打开 http://localhost:8000
```

## 目录

```
free-api-hub/
├── .github/workflows/
│   ├── refresh.yml       # 每 6 小时抓取 + 生成 + 探测 + 提交
│   └── pages.yml         # 推送 docs/ 时自动部署
├── scripts/
│   ├── build.py          # 解析 markdown 表格 → JSON
│   └── check.py          # 并发探测端点存活
├── data/
│   ├── llm.json          # 免费 LLM 平台表（手工维护）
│   └── cache/            # 上游 README 缓存
└── docs/                 # Pages 根目录，全部是静态文件
    ├── index.html        # 搜索界面
    └── api/v1/*.json
```

## 启用 Pages

仓库 Settings → Pages → Source 选 **GitHub Actions**。
之后每次 push `docs/` 都会自动部署。
