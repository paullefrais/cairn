"""Construit data/montcalm.js (données de l'interface Cairn) à partir de l'extraction LiveTrail anonymisée."""
import json, re, unicodedata, datetime as dt
import numpy as np, pandas as pd
import cairn_model as cm

SRC = 'data/cairn_montcalm_livetrail.json'
CIBLE = 2027
TZ = dt.timezone(dt.timedelta(hours=2))
RACES = ['marath', 'picari', 'picapic', 'novis', 'mineurs', 'kv', 'bynight']
VARIANTES_2026 = {'marath': ['marath2', 'marath3', 'marath4'], 'picapic': ['pica2', 'pica3', 'pica4']}
NOMS = {'marath': 'Marathon du Montcalm', 'picari': 'PicAriège', 'picapic': 'PICaPICA', 'novis': 'Trail des Novis',
        'mineurs': 'Trail des Mineurs', 'kv': 'KV du Sarrasi', 'bynight': 'Trail By Night'}
ALIAS = {'lartigue a': 'artigue a', 'lartigue r': 'artigue r', 'pinet 1': 'pinet a', 'pinet 2': 'pinet r',
         'estats': 'estat', 'lagardelle': 'col la gar', 'cret de be': 'crete de b', 'bassies': 'refbassies',
         'arrivee kv': 'arrivee', 'start': 'depart'}

raw = json.load(open(SRC))


def canon(short):
    s = unicodedata.normalize('NFKD', short or '').encode('ascii', 'ignore').decode().lower()
    s = re.sub(r"^l'", 'l', s).strip()
    return ALIAS.get(s, s)


def r1(a, nd=1):
    return [round(float(v), nd) for v in a]


def charger(ed, rid):
    """DataFrame coureurs d'une édition + description des points (clé canonique)."""
    m = raw['editions'].get(str(ed), {}).get(rid)
    if not m or not m['runners'] or not m['points']:
        return None
    pts = sorted([p for p in m['points'] if not p.get('disabled')], key=lambda p: p['km'])
    ids = {str(p['id']): canon(p['short']) for p in pts}
    rows = []
    for ru in m['runners']:
        t = {}
        for pid, (a, b) in ru['p'].items():
            c = ids.get(pid)
            if c is None:
                continue
            v = a or b
            if c not in t:
                t[c] = (v - m['start']) / 3600
        inter = {c: v for c, v in t.items() if c not in ('depart', 'arrivee', 'prefinish')}
        arr = t.get('arrivee')
        st = ru['st']
        if st == 'FINISHER' or (st in ('ON_RACE', 'UNRANKED') and arr):
            if not arr:
                continue
            statut = 'finisher'
        elif st == 'OUT_OF_TIME':
            statut = 'hors_delai'
        else:
            statut = 'abandon'
        if statut != 'finisher' and not inter:
            statut = 'non_partant'
        row = dict(edition=ed, cle=ru['k'], statut=statut, t_final=arr if statut == 'finisher' else np.nan)
        row.update({'cp_' + c: v for c, v in inter.items()})
        rows.append(row)
    return pd.DataFrame(rows), pts, m


def info_points(pts):
    out, vus = [], []
    for p in pts:
        c = canon(p['short'])
        if c in ('depart', 'prefinish') or c in [o['key'] for o in out]:
            continue
        if out and abs(p['km'] - out[-1]['km_m']) < 300 and c != 'arrivee':   # doublon entrée/sortie
            continue
        out.append(dict(key=c, km_m=p['km'], name=p['name'], short=p['short'], alt=p['alt'],
                        cutoff=p['cutoff'], services=p['services'] or []))
    return out


def clock(ts):
    d = dt.datetime.fromtimestamp(ts, TZ)
    return d.hour + d.minute / 60 + d.second / 3600


data = {'source': raw['source'], 'cible': CIBLE, 'races': []}
for rid in RACES:
    eds, pts_ed, meta_ed, partants, notes = {}, {}, {}, {}, {}
    for ed in range(2022, 2027):
        res = charger(ed, rid)
        if res is None:
            continue
        df, pts, m = res
        eds[ed], pts_ed[ed], meta_ed[ed] = df, pts, m
        partants[ed] = int((df.statut != 'non_partant').sum())
    # 2026 : parcours éclatés → partants = somme des variantes, édition exclue du modèle de forme
    exclues = set()
    if rid in VARIANTES_2026 and 2026 in eds:
        tot, det = partants[2026], []
        for v in VARIANTES_2026[rid]:
            mv = raw['editions']['2026'].get(v)
            if mv:   # variantes sans arrivée chronométrée : partant = au moins un pointage après le départ
                n = sum(1 for ru in mv['runners'] if len(ru['p']) >= 2); tot += n
                det.append(f"{raw['editions']['2026'][v]['name']} {raw['editions']['2026'][v]['distance']/1000:.0f} km : {n}")
        det.insert(0, f"parcours officiel : {partants[2026]}")
        partants[2026] = tot
        exclues.add(2026)
        notes[2026] = ('Parcours éclaté en plusieurs variantes raccourcies le jour J (' + ' ; '.join(det) +
                       '). Édition comptée pour la fréquentation, exclue du modèle de forme.')
    ref = max(e for e in eds if e not in exclues)
    P = info_points(pts_ed[ref])
    # garder les points réellement pointés sur l'édition de référence
    dref = eds[ref]; nref = (dref.statut != 'non_partant').sum()
    P = [p for p in P if p['key'] == 'arrivee' or dref.get('cp_' + p['key'], pd.Series(dtype=float)).notna().sum() >= 0.3 * nref]
    ordre = [p['key'] for p in P if p['key'] != 'arrivee']
    # ravitos : services déclarés sur au moins une édition
    rav = {}
    for ed, pts in pts_ed.items():
        for p in pts:
            if any(('AID' in s or 'SUPPLY' in s) for s in (p['services'] or [])):
                rav[canon(p['short'])] = True
    df = pd.concat([d[d.statut != 'non_partant'] for d in eds.values()], ignore_index=True)
    for c in ordre:
        if 'cp_' + c not in df:
            df['cp_' + c] = np.nan
    cps_par_ed = {e: [c for c in ordre if d.get('cp_' + c, pd.Series(dtype=float)).notna().any()] for e, d in eds.items()}
    part = pd.Series(partants).sort_index()
    editions = sorted(eds)

    # ---------- prédiction de l'édition cible
    m = cm.entrainer(df, cps_par_ed, ordre, editions, CIBLE, partants_hist=part, exclues=exclues)
    pas, ab, n_sim = cm.simuler(m, n_sim=1000)
    edges, R = cm.resumer(pas, n_sim)
    start_clock = clock(meta_ed[ref]['start'])
    pred = {}
    for p in P:
        r = R.get(p['key'] if p['key'] != 'arrivee' else 'Arrivée')
        if r is None:
            continue
        nz = np.nonzero(r['p90'] > 0.05)[0]
        if not len(nz):
            continue
        i0, i1 = int(nz[0]), int(nz[-1]) + 1
        cut = (p['cutoff'] - meta_ed[ref]['start']) / 3600 if p['cutoff'] else None
        apres = None
        if cut is not None:
            s, t = pas[p['key'] if p['key'] != 'arrivee' else 'Arrivée']
            apres = float(np.median(np.bincount(s[t > cut], minlength=n_sim)))
        pred[p['key']] = dict(i0=i0, p10=r1(r['p10'][i0:i1]), p50=r1(r['p50'][i0:i1]), p90=r1(r['p90'][i0:i1]),
                              n=r1(r['n'], 0), premier=round(r['premier'], 3), p05=round(r['p05'], 3), p95=round(r['p95'], 3),
                              dernier=round(r['dernier'], 3), dernier_p90=round(r['dernier_p90'], 3),
                              pic=r1(r['pic'], 0), heure_pic=round(r['heure_pic'], 3), apres_barriere=apres)
    # abandons prévus : par point (dernier franchi) et par heure
    s_ab, t_ab, k_ab = ab
    keys = ['depart'] + ordre
    ab_pt = {keys[k]: float(np.median(np.bincount(s_ab[k_ab == k], minlength=n_sim))) for k in range(len(keys))}
    hrs = np.arange(0, np.ceil(edges[-1]) + 1)
    Cab = cm.comptes_sim(s_ab, t_ab, n_sim, hrs)
    s_f, t_f = pas['Arrivée']
    Cf = cm.comptes_sim(s_f, t_f, n_sim, hrs)
    horaire = dict(h0=0, abandons=r1(np.median(Cab, axis=0)), arrivees=r1(np.median(Cf, axis=0)))

    # ---------- backtest : prédire l'édition de référence avec les éditions antérieures
    bt = None
    train = [e for e in editions if e < ref]
    if train:
        try:
            mb = cm.entrainer(df, cps_par_ed, ordre, train, ref, partants_hist=part, exclues=exclues)
            n_reel = int(part[ref])
            pb, _, nb = cm.simuler(mb, n_sim=1000, n_fixe=n_reel)
            eb, Rb = cm.resumer(pb, nb, t_max=edges[-1])
            pts_bt = {}
            vus = {c for e in mb['valides'] for c in cps_par_ed.get(e, [])} | {'arrivee'}
            for p in P:
                k = p['key']; kk = k if k != 'arrivee' else 'Arrivée'
                if kk not in Rb or k not in vus:     # point absent des éditions d'entraînement : pas de test équitable
                    continue
                d = dref[dref.statut != 'non_partant']
                t_reel = d.t_final if k == 'arrivee' else d['cp_' + k]
                reel = cm.histo_reel(t_reel, eb)
                r = Rb[kk]
                nz = np.nonzero((r['p90'] > 0.05) | (reel > 0))[0]
                if not len(nz):
                    continue
                i0, i1 = int(nz[0]), int(nz[-1]) + 1
                pts_bt[k] = dict(i0=i0, reel=[int(v) for v in reel[i0:i1]], p10=r1(r['p10'][i0:i1]), p50=r1(r['p50'][i0:i1]),
                                 p90=r1(r['p90'][i0:i1]), m=cm.metriques(reel, r['p10'], r['p50'], r['p90'], eb))
            bt = dict(edition=ref, train=[e for e in mb['valides']], n_reel=n_reel,
                      n_tendance=round(mb['n_pred']), points=pts_bt)
        except Exception as ex:
            print('backtest impossible', rid, ex)

    # ---------- historique par édition
    hist = []
    for ed in editions:
        d = eds[ed]; f = d[d.statut == 'finisher']
        nf = d[d.statut.isin(['abandon', 'hors_delai'])]
        lieux = {}
        for _, r in nf.iterrows():
            last = 'depart'
            for c in ordre:
                if not pd.isna(r.get('cp_' + c, np.nan)):
                    last = c
            lieux[last] = lieux.get(last, 0) + 1
        pics = {}
        for p in P:
            col = d.t_final if p['key'] == 'arrivee' else d.get('cp_' + p['key'])
            if col is None or col.notna().sum() == 0:
                continue
            h = np.histogram(col.dropna(), bins=np.arange(0, col.max() + 0.5, 0.25))[0]
            pics[p['key']] = [int(h.max()), round(float(np.argmax(h) * 0.25), 2), int(col.notna().sum())]
        hist.append(dict(edition=ed, pics=pics, partants=int(part[ed]), partants_officiel=int((d.statut != 'non_partant').sum()),
                         finishers=len(f), abandons=int((d.statut == 'abandon').sum()), hors_delai=int((d.statut == 'hors_delai').sum()),
                         non_partants=int((d.statut == 'non_partant').sum()),
                         premier=round(float(f.t_final.min()), 3) if len(f) else None,
                         median=round(float(f.t_final.median()), 3) if len(f) else None,
                         dernier=round(float(f.t_final.max()), 3) if len(f) else None,
                         depart=round(clock(meta_ed[ed]['start']), 5),
                         date=dt.datetime.fromtimestamp(meta_ed[ed]['start'], TZ).strftime('%Y-%m-%d'),
                         lieux_abandon=lieux, note=notes.get(ed), exclue=bool(ed in exclues or m['poids'].get(ed, 1) == 0)))

    # ---------- rejeu de l'édition de référence
    kmof = {p['key']: p['km_m'] / 1000 for p in P}
    rep = []
    for _, r in dref[dref.statut != 'non_partant'].iterrows():
        tr = [0.0, 0.0]
        for c in ordre:
            v = r.get('cp_' + c, np.nan)
            if not pd.isna(v):
                tr += [round(float(v), 3), kmof[c]]
        if r.statut == 'finisher':
            tr += [round(float(r.t_final), 3), kmof['arrivee']]
        rep.append([{'finisher': 0, 'abandon': 1, 'hors_delai': 2}[r.statut], tr])

    # ---------- profil
    prof = None
    for ed in sorted(meta_ed, reverse=True):
        if meta_ed[ed].get('profile') and ed not in exclues:
            prof = [[round(k / 1000, 2), a] for k, a in meta_ed[ed]['profile']]
            break
    if prof is None:
        prof = [[0, P[0]['alt']]] + [[p['km_m'] / 1000, p['alt']] for p in P]

    data['races'].append(dict(
        id=rid, name=NOMS[rid], distance=meta_ed[ref]['distance'] / 1000, dplus=meta_ed[ref]['dplus'],
        ref=ref, start_clock=round(start_clock, 5), start_place=meta_ed[ref].get('startPlace') or 'Auzat',
        date_ref=dt.datetime.fromtimestamp(meta_ed[ref]['start'], TZ).strftime('%Y-%m-%d'),
        points=[dict(key=p['key'], name=p['name'], short=p['short'], km=round(p['km_m'] / 1000, 2), alt=p['alt'],
                     ravito=bool(rav.get(p['key'])),
                     cutoff=round((p['cutoff'] - meta_ed[ref]['start']) / 3600, 5) if p['cutoff'] else None) for p in P],
        profile=prof, history=hist,
        model=dict(valides=m['valides'], poids={int(k): round(float(v), 2) for k, v in m['poids'].items()},
                   e_fact={int(k): round(float(v), 3) for k, v in m['e_fact'].items()},
                   alertes=[[int(e), t, msg] for e, t, msg in m['alertes']],
                   n_pred=round(m['n_pred']), n_sd=round(m['n_sd']), p_dnf=round(m['p_dnf'], 3)),
        pred=dict(step=0.25, n=r1(np.percentile(np.bincount(pas['Arrivée'][0], minlength=n_sim), [10, 50, 90]), 0),
                  points=pred, abandons_point=ab_pt, horaire=horaire),
        backtest=bt, replay=dict(edition=ref, runners=rep)))
    print(f"{rid}: réf {ref}, éditions {editions}, valides {m['valides']}, N {m['n_pred']:.0f}±{m['n_sd']:.0f}, "
          f"abandon {m['p_dnf']:.1%}, points {ordre}, alertes {m['alertes']}")

js = 'window.CAIRN_DATA = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
open('data/montcalm.js', 'w').write(js)
print('montcalm.js', round(len(js) / 1e3), 'ko')
