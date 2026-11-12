const INDEX = 'https://raw.githubusercontent.com/USER/REPO/main/docs/api/v1/apis.json';

export default {
  async fetch(req, env) {
    const cors = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET,OPTIONS',
      'Access-Control-Allow-Headers': '*'
    };
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors });

    const u = new URL(req.url);
    const p = u.pathname.replace(/\/+$/, '');

    if (p === '' || p === '/') {
      return json({
        name: 'free-api-hub',
        endpoints: {
          '/search': 'q=&category=&nokey=1&limit=50&offset=0',
          '/random': 'random=true&category=&nokey=1',
          '/stats': '统计',
          '/:id': '按 id 取单条'
        }
      }, cors);
    }

    let data;
    try {
      const r = await fetch(INDEX, { cf: { cacheTtl: 3600 } });
      if (!r.ok) throw new Error('upstream ' + r.status);
      data = await r.json();
    } catch (e) {
      return json({ error: 'upstream fetch failed', detail: String(e) }, cors, 502);
    }

    if (p === '/stats') {
      const byAuth = {}, byCat = {};
      for (const a of data) {
        byAuth[a.auth] = (byAuth[a.auth] || 0) + 1;
        byCat[a.category] = (byCat[a.category] || 0) + 1;
      }
      return json({ total: data.length, by_auth: byAuth, by_category: byCat }, cors);
    }

    if (p === '/random') {
      let pool = filter(data, u.searchParams);
      if (!pool.length) return json({ error: 'no match' }, cors, 404);
      return json(pool[Math.floor(Math.random() * pool.length)], cors);
    }

    if (p === '/search' || p === '') {
      let pool = filter(data, u.searchParams);
      const limit = Math.min(parseInt(u.searchParams.get('limit') || '50', 10) || 50, 500);
      const offset = Math.max(parseInt(u.searchParams.get('offset') || '0', 10) || 0, 0);
      return json({
        total: pool.length,
        limit,
        offset,
        items: pool.slice(offset, offset + limit)
      }, cors);
    }

    const id = p.slice(1).toLowerCase();
    const hit = data.find(a => a.id === id || a.name.toLowerCase() === id);
    if (!hit) return json({ error: 'not found', id }, cors, 404);
    return json(hit, cors);
  }
};

function filter(data, sp) {
  const q = (sp.get('q') || '').trim().toLowerCase();
  const cat = (sp.get('category') || '').trim();
  const nokey = sp.get('nokey') === '1' || sp.get('nokey') === 'true';
  const corsOnly = sp.get('cors') === '1';

  return data.filter(a => {
    if (nokey && a.auth !== 'No') return false;
    if (corsOnly && !/yes/i.test(a.cors)) return false;
    if (cat && a.category.toLowerCase() !== cat.toLowerCase()) return false;
    if (q) {
      const hay = (a.name + ' ' + a.description + ' ' + a.category + ' ' + a.url).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function json(obj, headers, status) {
  return new Response(JSON.stringify(obj, null, 2), {
    status: status || 200,
    headers: Object.assign({
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'public, max-age=3600'
    }, headers)
  });
}
