"""
Cairn : modèle de prédiction des passages aux points de contrôle.

Version générique du notebook cairn_prediction.ipynb : aucune variable globale,
les données arrivent sous forme d'un DataFrame « long » (une ligne par coureur et par édition),
quelle que soit leur source (exports Pyrénées Chrono, API LiveTrail…).

Colonnes attendues :
  edition (int), cle (identifiant du coureur, stable d'une édition à l'autre),
  statut ('finisher' | 'abandon' | 'hors_delai'), t_final (heures depuis le départ, NaN si non finisher),
  cp_<nom> (heures depuis le départ au point <nom>, NaN si pas de pointage).

Modèle : log(temps final) = niveau du coureur + facteur édition ;
fraction du temps final à chaque point = a + b × (niveau − moyenne) + résidu tiré chez les coureurs de niveau voisin ;
simulation Monte-Carlo de N éditions → passages par créneau avec bande P10–P90.
"""
import numpy as np
import pandas as pd


# ---------------------------------------------------------------- diagnostic
def diagnostic(df, cps_par_ed):
    """Une ligne par édition + liste d'alertes (édition, type, message)."""
    lignes, alertes = [], []
    for e in sorted(df.edition.unique()):
        d = df[df.edition == e]
        f = d[d.statut == 'finisher']
        lignes.append(dict(edition=e, partants=len(d), finishers=len(f),
                           taux_abandon=round(1 - len(f) / max(len(d), 1), 3),
                           t_median_h=round(f.t_final.median(), 2) if len(f) else np.nan,
                           dernier_sur_median=round(f.t_final.max() / f.t_final.median(), 2) if len(f) else np.nan))
    diag = pd.DataFrame(lignes).set_index('edition')
    med_ab, med_rat = diag.taux_abandon.median(), diag.dernier_sur_median.median()
    for e, r in diag.iterrows():
        if len(diag) >= 2 and r.taux_abandon > max(3 * med_ab, 0.10) and r.taux_abandon - med_ab > 0.05:
            alertes.append((e, 'troncature', f"taux d'abandon {r.taux_abandon:.0%} contre {med_ab:.0%} habituellement"))
        # queue coupée : seulement si elle s'accompagne d'abandons en hausse (course neutralisée) ou si elle est massive
        if len(diag) >= 2 and (r.dernier_sur_median < 0.70 * med_rat or
                               (r.dernier_sur_median < 0.85 * med_rat and r.taux_abandon > med_ab + 0.03)):
            alertes.append((e, 'troncature', f'queue de course coupée (dernier/médian = {r.dernier_sur_median} contre {med_rat})'))
        f = df[(df.edition == e) & (df.statut == 'finisher')]
        if cps_par_ed.get(e) and len(f) >= 20:
            quint = pd.qcut(f.t_final.rank(method='first'), 5, labels=False)
            for c in cps_par_ed[e]:
                manq = f['cp_' + c].isna()
                lent, reste = manq[quint == 4].mean(), manq[quint < 4].mean()
                if lent > 0.2 and lent > 3 * max(reste, 0.01):
                    alertes.append((e, 'censure', f'point « {c} » : {lent:.0%} des 20 % les plus lents sans pointage'))
    return diag, alertes


def poids_editions(diag, alertes, cible, demi_vie=3, exclues=(), garder=()):
    tronquees = {e for e, t, _ in alertes if t == 'troncature'} - set(garder)
    return pd.Series({e: 0.0 if (e in tronquees or e in exclues) else 0.5 ** ((cible - 1 - e) / demi_vie)
                      for e in diag.index})


# ---------------------------------------------------------------- facteurs édition
def facteurs_edition(df, editions, shrink_k=10, n_min=5):
    f = df[(df.statut == 'finisher') & df.edition.isin(editions)].copy()
    f['y'] = np.log(f.t_final)
    rec = f.groupby('cle').edition.transform('nunique') >= 2
    e = pd.Series(0.0, index=sorted(editions))
    for _ in range(100):                                   # moindres carrés alternés, version robuste
        f['e'] = f.edition.map(e)
        f['a'] = f.cle.map((f.y - f.e).groupby(f.cle).mean())
        r = f[rec]
        nouv = (r.y - r.a).groupby(r.edition).median().reindex(e.index).fillna(0)
        nouv -= nouv.iloc[-1]                              # référence = édition la plus récente
        if np.allclose(nouv, e, atol=1e-6):
            break
        e = nouv
    n_rec = f[rec].groupby('edition').size().reindex(e.index).fillna(0)
    e_shr = e * n_rec / (n_rec + shrink_k)
    e_shr[n_rec < n_min] = 0.0
    return e_shr, n_rec


# ---------------------------------------------------------------- splits
def modele_splits(df, editions, ordre_cp, e_fact):
    cols = ['cp_' + c for c in ordre_cp]
    if not ordre_cp:
        return None
    f = df[(df.statut == 'finisher') & df.edition.isin(editions)].copy()
    f['x'] = np.log(f.t_final) - f.edition.map(e_fact).fillna(0)
    xbar = f.x.mean()
    coefs, resid = {}, pd.DataFrame(index=f.index)
    for c in ordre_cp:
        fr = f['cp_' + c] / f.t_final
        ok = fr.notna() & (fr > 0) & (fr < 1)
        if ok.sum() >= 10:
            b, a = np.polyfit(f.x[ok] - xbar, fr[ok], 1)
        else:
            b, a = 0.0, float(fr[ok].median()) if ok.any() else np.nan
        coefs[c] = (a, b)
        resid[c] = np.where(ok, fr - (a + b * (f.x - xbar)), np.nan)
    # points jamais observés : interpolation linéaire entre voisins (sécurité)
    a_s = pd.Series({c: coefs[c][0] for c in ordre_cp}).interpolate(limit_direction='both')
    for c in ordre_cp:
        if np.isnan(coefs[c][0]):
            coefs[c] = (float(a_s[c]), 0.0)
    # réservoir de résidus : coureurs les plus complets ; trous éventuels mis à 0
    taux = resid.notna().mean(axis=1)
    if taux.max() == 0:                                     # aucun point intermédiaire observé : pas de dispersion
        return dict(cps=list(ordre_cp), coefs=coefs, xbar=xbar,
                    pool_x=f.x.values, pool_r=np.zeros((len(f), len(ordre_cp))))
    pool = resid[taux >= min(taux.max(), max(0.5, taux.quantile(0.5)))]
    return dict(cps=list(ordre_cp), coefs=coefs, xbar=xbar,
                pool_x=f.x[pool.index].values, pool_r=pool.fillna(0).values)


# ---------------------------------------------------------------- entraînement
def entrainer(df, cps_par_ed, ordre_cp, editions, cible, n_inscrits=None, partants_hist=None,
              exclues=(), demi_vie=3):
    """partants_hist : série édition -> nombre de partants (peut inclure des éditions exclues du modèle de forme)."""
    d = df[df.edition.isin(editions)]
    diag, alertes = diagnostic(d, {e: cps_par_ed.get(e, []) for e in editions})
    w = poids_editions(diag, alertes, cible, demi_vie, exclues)
    valides = [e for e in editions if w.get(e, 0) > 0]
    if not valides:                                         # tout est exclu : on garde la plus récente
        valides = [max(editions)]; w[valides[0]] = 1.0
    e_fact, n_rec = facteurs_edition(df, valides)
    f = df[(df.statut == 'finisher') & df.edition.isin(valides)].copy()
    f['x'] = np.log(f.t_final) - f.edition.map(e_fact)
    f['w'] = f.edition.map(w) / f.edition.map(f.edition.value_counts())
    # nombre de partants
    part = partants_hist if partants_hist is not None else diag.partants
    part = part[[e for e in part.index if e < cible]].sort_index()
    if n_inscrits:
        n_pred, n_sd = float(n_inscrits), 0.02 * n_inscrits
    elif len(part) >= 2:
        ww = np.array([0.5 ** ((cible - 1 - e) / demi_vie) for e in part.index])
        p = np.polyfit(part.index, part.values, 1, w=np.sqrt(ww))
        n_pred = float(np.clip(np.polyval(p, cible), 0.7 * part.iloc[-1], 1.3 * part.iloc[-1]))
        n_sd = max(float(np.std(part.values - np.polyval(p, part.index))), (0.07 if len(part) >= 3 else 0.12) * n_pred)
    else:
        n_pred, n_sd = float(part.iloc[-1]), 0.10 * float(part.iloc[-1])
    p_dnf = float(np.average(diag.loc[valides, 'taux_abandon'], weights=w[valides]))
    spl = modele_splits(df, valides, ordre_cp, e_fact)
    seg_dnf = None
    if spl:
        nd = df[df.edition.isin(valides) & (df.statut != 'finisher')]
        if len(nd):
            m = nd[['cp_' + c for c in ordre_cp]].notna().values
            dernier = np.where(m.any(axis=1), m.shape[1] - np.argmax(m[:, ::-1], axis=1), 0)  # nb de points franchis
            seg_dnf = np.bincount(dernier, minlength=len(ordre_cp) + 1).astype(float)
            seg_dnf /= seg_dnf.sum()
    sd_e = max(float(np.std(e_fact.values)), 0.03)
    return dict(cible=cible, poids=w, valides=valides, e_fact=e_fact, n_rec=n_rec, sd_e=sd_e,
                niveaux=f.x.values, w_niv=(f.w / f.w.sum()).values, n_pred=n_pred, n_sd=n_sd,
                p_dnf=p_dnf, seg_dnf=seg_dnf, splits=spl, alertes=alertes, diag=diag)


# ---------------------------------------------------------------- simulation
def simuler(m, n_sim=1000, scenario=None, seed=42, n_fixe=None):
    rng = np.random.default_rng(seed)
    if n_fixe:
        N = np.full(n_sim, int(n_fixe))
    else:
        N = np.maximum(rng.normal(m['n_pred'], m['n_sd'], n_sim).round().astype(int), 1)
    sim = np.repeat(np.arange(n_sim), N)
    tot = len(sim)
    e = rng.normal(0, m['sd_e'], n_sim) if scenario is None else np.full(n_sim, scenario)
    x = rng.choice(m['niveaux'], tot, p=m['w_niv']) + rng.normal(0, 0.02, tot)
    t_fin = np.exp(x + e[sim])
    spl = m['splits']
    cps = spl['cps'] if spl else []
    pas = {}
    if spl:
        order = np.argsort(spl['pool_x'])
        px, pr = spl['pool_x'][order], spl['pool_r'][order]
        pos = np.clip(np.searchsorted(px, x) + rng.integers(-7, 8, tot), 0, len(px) - 1)
        fr = np.column_stack([spl['coefs'][c][0] + spl['coefs'][c][1] * (x - spl['xbar']) for c in cps]) + pr[pos]
        fr = np.clip(np.maximum.accumulate(fr, axis=1), 0.005, 0.995)
        for j, c in enumerate(cps):
            pas[c] = fr[:, j] * t_fin
    dnf = rng.random(tot) < m['p_dnf']
    nseg = len(cps) + 1
    probs = m['seg_dnf'] if m['seg_dnf'] is not None else np.ones(nseg) / nseg
    stop = np.where(dnf, rng.choice(nseg, tot, p=probs), nseg)
    out = {c: (sim[stop > j], pas[c][stop > j]) for j, c in enumerate(cps)}
    out['Arrivée'] = (sim[stop == nseg], t_fin[stop == nseg])
    # abandons : (simulation, heure du dernier pointage, index du dernier point franchi)
    ab = stop < nseg
    t_last = np.zeros(tot)
    for j, c in enumerate(cps):
        t_last = np.where(stop > j, pas[c], t_last)
    out_ab = (sim[ab], t_last[ab], stop[ab])
    return out, out_ab, n_sim


# ---------------------------------------------------------------- agrégation
def comptes_sim(sim_idx, t, n_sim, edges):
    b = np.clip(np.digitize(t, edges) - 1, 0, len(edges) - 2)
    return np.bincount(sim_idx * (len(edges) - 1) + b, minlength=n_sim * (len(edges) - 1)).reshape(n_sim, -1)


def resumer(passages, n_sim, pas_min=15, t_max=None):
    """Retourne edges (heures depuis le départ) et, par point : bandes P10/P50/P90 et indicateurs clés."""
    t_max = t_max or max(t.max() for _, t in passages.values() if len(t))
    edges = np.arange(0, np.ceil(t_max) + pas_min / 60, pas_min / 60)
    res = {}
    for c, (s, t) in passages.items():
        if not len(t):
            continue
        C = comptes_sim(s, t, n_sim, edges)
        p10, p50, p90 = np.percentile(C, [10, 50, 90], axis=0)
        n = np.bincount(s, minlength=n_sim)
        g = pd.DataFrame({'s': s, 't': t}).groupby('s').t
        prem, p05, p95, dern = g.min(), g.quantile(0.05), g.quantile(0.95), g.max()
        pk = C.max(axis=1)
        res[c] = dict(p10=p10, p50=p50, p90=p90,
                      n=np.percentile(n, [10, 50, 90]),
                      premier=float(np.median(prem)), p05=float(np.median(p05)), p95=float(np.median(p95)),
                      dernier=float(np.median(dern)), dernier_p90=float(np.percentile(dern, 90)),
                      pic=np.percentile(pk, [10, 50, 90]),
                      heure_pic=float(edges[int(np.argmax(p50))]))
    return edges, res


def histo_reel(t, edges):
    t = np.asarray(t, float)
    t = t[~np.isnan(t)]
    return np.histogram(t, bins=edges)[0]


def metriques(reel, p10, p50, p90, edges):
    nz = (reel > 0) | (p90 > 0)
    cum_r, cum_m = np.cumsum(reel), np.cumsum(p50)
    t_r = np.repeat(edges[:-1], reel)
    t_m = np.repeat(edges[:-1], np.round(p50).astype(int))
    q = lambda t, p: np.percentile(t, p) if len(t) else np.nan
    return {'reel': int(reel.sum()), 'predit': float(p50.sum()),
            'err_cumul': float(np.mean(np.abs(cum_r - cum_m))),
            'err_pic': float(p50.max() - reel.max()),
            'err_heure_pic_min': float((edges[int(np.argmax(p50))] - edges[int(np.argmax(reel))]) * 60),
            'err_p95_min': float((q(t_m, 95) - q(t_r, 95)) * 60) if len(t_r) and len(t_m) else None,
            'couverture': float(np.mean((reel[nz] >= p10[nz]) & (reel[nz] <= p90[nz]))) if nz.any() else None}
