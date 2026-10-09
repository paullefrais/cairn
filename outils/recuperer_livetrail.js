// Cairn : récupération anonymisée des passages LiveTrail du Challenge du Montcalm (2022-2026)
// À coller dans la console de Safari, sur un onglet ouvert sur https://montcalm.v3.livetrail.net
(async () => {
  const A = 'https://api.v3.livetrail.net/api/events/';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const g = async (p, t) => {
    for (let i = 0; i < 3; i++) {
      const r = await fetch(A + p, { headers: { 'X-Tenant': t } });
      if (r.ok) return r.json();
      if (r.status < 500) return { err: r.status };
      await sleep(800);
    }
    return { err: 500 };
  };
  // Anonymisation : empreinte SHA-256 du nom, avec un sel aléatoire jamais enregistré
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const norm = s => (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toUpperCase()
    .replace(/[^A-Z ]/g, ' ').split(/\s+/).filter(Boolean).sort().join(' ');
  const hash = async s => {
    const b = new TextEncoder().encode(s), m = new Uint8Array(salt.length + b.length);
    m.set(salt); m.set(b, salt.length);
    const h = new Uint8Array(await crypto.subtle.digest('SHA-256', m));
    return [...h.slice(0, 6)].map(x => x.toString(16).padStart(2, '0')).join('');
  };
  const ts = s => (s ? Math.round(Date.parse(s) / 1000) : null);
  const out = {
    source: 'LiveTrail – Challenge du Montcalm (api.v3.livetrail.net), extrait le ' +
      new Date().toISOString().slice(0, 10) + ' ; données anonymisées (identifiant haché salé, sel non conservé)',
    editions: {}
  };
  for (const y of [2022, 2023, 2024, 2025, 2026]) {
    const t = 'montcalm_' + y;
    const races = await g('races/summaries', t);
    if (!Array.isArray(races)) { console.log(y, 'indisponible'); continue; }
    out.editions[y] = {};
    for (const r of races) {
      const id = r.raceId;
      const meta = { name: r.fullname, distance: r.distance, dplus: r.elevationGain, start: ts(r.startDate),
        startPlace: r.startPlace, profile: r.trackSummaryProfile || null };
      const pts = await g('points?raceId=' + id, t);
      meta.points = Array.isArray(pts) ? pts.map(p => ({ id: p.pointId, name: p.name, short: p.shortName,
        km: p.distance, alt: p.altitude, dplus: p.elevationGain, lat: p.lat, lon: p.lon, type: p.type,
        services: p.services, cutoff: ts(p.cutoff), access: p.access, assist: p.isAssistance, disabled: p.isDisabled })) : null;
      const runners = []; let page = 0, total = null, err = null;
      while (true) {
        const ps = await g(`passings/${id}?display=DATETIME&limit=200&page=${page}`, t);
        if (ps.err) { err = ps.err; break; }
        total = ps.total;
        for (const row of ps.rows) {
          const ru = row.runner, pp = {};
          for (const [k, v] of Object.entries(row.passingsByPointId || {})) {
            const a = ts(v.datetimeIn), b = ts(v.datetimeOut);
            if (a || b) pp[k] = [a, b];
          }
          runners.push({ k: await hash(norm((ru.lastName || '') + ' ' + (ru.firstName || ''))),
            sex: ru.sex, cat: ru.category, st: ru.status, p: pp });
        }
        page++;
        if (runners.length >= total || ps.rows.length === 0) break;
        await sleep(250);
      }
      meta.runners = runners; meta.total = total; meta.err = err;
      out.editions[y][id] = meta;
      console.log(`${y} ${id} : ${runners.length} coureurs${err ? ' (indisponible)' : ''}`);
      await sleep(300);
    }
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out)], { type: 'application/json' }));
  a.download = 'cairn_montcalm_livetrail.json';
  document.body.appendChild(a); a.click();
  console.log('Terminé : fichier cairn_montcalm_livetrail.json téléchargé');
})();
