"""Teil 3 – Frequenzmodelle: GLM und Gradient Boosting, je ohne (a) und mit (b) Laufzeitklassen.

Ablauf:
1. Kappung der stetigen Merkmale am 99.5 %-Exposure-Quantil (Grenzen aus dem Training).
2. Auswahl VehPower und Regionsgruppierung im vollen GLM per gruppierter Kreuzvalidierung
   (1-SE-Regel: einfachste Variante, die höchstens 1 Standardfehler hinter der besten liegt).
3. GLM a und b (Negativ-Binomial, Log-Link, Offset log(Exposure)) auf dem ganzen Training.
4. Gradient Boosting (Poisson-Verlust) a und b, Hyperparameter per Kreuzvalidierung.
5. Vergleich aller Modelle auf den Testdaten (Poisson-Deviance, Kalibrierung).

Die Testdaten werden nur in Schritt 5 verwendet.

Aufruf:
    python src/teil3_frequenz.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from teil3_grundlagen import OUT, PROCESSED, SEED, cv_folds, fit_nb, kalibrierung, lade_mit_split, poisson_deviance, predict
from teil3_merkmale import K_FOLDS, Gruppiert, Kategorie, Linear, Log, Spline, design, fitte, region_klein, region_rang

KAPPUNG_QUANTIL = 0.995
GEKAPPT = ["DrivAge", "BonusMalus", "VehAge"]
EXPOSURE_GRENZEN = [0, 0.05, 0.1, 0.25, 0.5, 0.75, 0.99, 1.0]
GBM_MERKMALE = ["VehPower", "VehAge", "DrivAge", "BonusMalus", "VehBrand", "VehGas", "Density", "Region"]
GBM_KATEGORIAL = ["VehBrand", "VehGas", "Region"]
GBM_GRID = [{"max_leaf_nodes": n, "min_samples_leaf": 500} for n in (7, 15, 31)]
GBM_MAX_ITER = 1000
GBM_LERNRATE = 0.05


# ---------------------------------------------------------------------------
# Vorbereitung
# ---------------------------------------------------------------------------


def kappungsgrenzen(train):
    grenzen = {}
    for c in GEKAPPT:
        d = train.sort_values(c)
        cum = d["Exposure"].cumsum().to_numpy() / d["Exposure"].sum()
        grenzen[c] = int(d[c].to_numpy()[np.searchsorted(cum, KAPPUNG_QUANTIL)])
    return grenzen


def vorbereiten(df, grenzen):
    df = df.copy()
    for c, g in grenzen.items():
        df[c] = df[c].clip(upper=g)
    df["ExpKlasse"] = pd.cut(df["Exposure"], EXPOSURE_GRENZEN).astype(str)
    return df


def basis_kodierung():
    return [
        Spline("DrivAge", 8),
        Spline("BonusMalus", 8),
        Spline("VehAge", 4),
        Log("Density"),
        Kategorie("VehBrand"),
        Kategorie("VehGas"),
    ]


def region_bereinigt(k, alpha):
    """Regionen nach ihrem Effekt *zusätzlich zu log(Density)* sortiert, dann k Gruppen gleicher Exposure."""

    def f(df):
        reg = Kategorie("Region")
        m = fitte([Log("Density"), reg], df, alpha)
        effekt = pd.Series(0.0, index=sorted(df["Region"].unique()))
        effekt[reg.werte] = m["beta"][2:]
        e = df.groupby("Region")["Exposure"].sum().loc[effekt.index]
        order = effekt.sort_values().index
        cum = (e[order].cumsum() - e[order] / 2) / e.sum()
        gruppe = np.minimum((cum * k).astype(int), k - 1)
        return {r: f"Gruppe {g + 1}" for r, g in gruppe.items()}

    return f


# ---------------------------------------------------------------------------
# Auswahl per Kreuzvalidierung
# ---------------------------------------------------------------------------


def cv_vergleich(varianten, train, folds, alpha):
    """varianten: {Name: (Anzahl Zusatzparameter-Schätzer, Funktion → Kodierungsliste)}"""
    je_fold, params = {}, {}
    for name, bauen in varianten.items():
        werte = []
        for k in range(K_FOLDS):
            tr, va = train[folds != k], train[folds == k]
            kods = bauen()
            m = fitte(kods, tr, alpha)
            mu = predict(m, design(kods, va), np.log(va["Exposure"].to_numpy()))
            werte.append(poisson_deviance(va["ClaimNb"], mu))
        je_fold[name] = np.array(werte)
        kods = bauen()
        params[name] = len(fitte(kods, train, alpha)["beta"])
        print(f"  {name}: {je_fold[name].mean():.6f}")
    t = pd.DataFrame({"Parameter": params, "CV-Deviance": {n: v.mean() for n, v in je_fold.items()}})
    beste = t["CV-Deviance"].idxmin()
    t["Abstand zur besten"] = [(je_fold[n] - je_fold[beste]).mean() for n in t.index]
    t["± SE Abstand"] = [(je_fold[n] - je_fold[beste]).std(ddof=1) / np.sqrt(K_FOLDS) for n in t.index]
    # 1-SE-Regel: einfachste Variante (wenigste Parameter), deren Abstand ≤ 1 SE ist
    ok = t[t["Abstand zur besten"] <= t["± SE Abstand"] + 1e-12]
    gewaehlt = ok.sort_values(["Parameter", "CV-Deviance"]).index[0]
    t["gewählt"] = ["✔" if n == gewaehlt else "" for n in t.index]
    return t.rename_axis("Variante"), gewaehlt


# ---------------------------------------------------------------------------
# Gradient Boosting
# ---------------------------------------------------------------------------


def gbm_X(df, kategorien, mit_exposure):
    x = df[GBM_MERKMALE].copy()
    for c in GBM_KATEGORIAL:
        x[c] = pd.Categorical(x[c], categories=kategorien[c])
    if mit_exposure:
        x["Exposure"] = df["Exposure"].to_numpy()
    return x


def gbm_modell(params, n_iter):
    return HistGradientBoostingRegressor(
        loss="poisson", learning_rate=GBM_LERNRATE, max_iter=n_iter, early_stopping=False,
        categorical_features="from_dtype", random_state=SEED, **params,
    )


def gbm_tuning(train, folds, kategorien, mit_exposure):
    rows = []
    for params in GBM_GRID:
        kurven = []
        for k in range(K_FOLDS):
            tr, va = train[folds != k], train[folds == k]
            m = gbm_modell(params, GBM_MAX_ITER)
            m.fit(gbm_X(tr, kategorien, mit_exposure), tr["ClaimNb"] / tr["Exposure"], sample_weight=tr["Exposure"])
            Xv = gbm_X(va, kategorien, mit_exposure)
            kurven.append([poisson_deviance(va["ClaimNb"], p * va["Exposure"]) for p in m.staged_predict(Xv)])
        kurve = np.mean(kurven, axis=0)
        best = int(np.argmin(kurve))
        rows.append({**params, "Iterationen": best + 1, "CV-Deviance": kurve[best]})
        print(f"  GBM {params}: {best + 1} Iterationen, {kurve[best]:.6f}")
    t = pd.DataFrame(rows)
    return t, t.loc[t["CV-Deviance"].idxmin()]


# ---------------------------------------------------------------------------
# Darstellung
# ---------------------------------------------------------------------------


def md_table(df, fmt=None, index=True):
    fmt = fmt or {}
    if index:
        df = df.reset_index()
    cols = list(df.columns)

    def f(c, v):
        if c in fmt:
            return fmt[c].format(v)
        if isinstance(v, (float, np.floating)):
            return f"{v:.6f}"
        if isinstance(v, (int, np.integer)):
            return f"{v:,}"
        return str(v)

    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(f(c, v) for c, v in zip(cols, r)) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


def faktoren_kategorial(modell, kods):
    """exp(β) mit 95 %-KI für alle kategorialen Kodierungen."""
    rows, pos = [], 1
    for k in kods:
        n = len(k.transform(modell["_train1"])[0])
        if isinstance(k, Kategorie):
            ref = k.fit_ref if hasattr(k, "fit_ref") else None
            rows.append({"Merkmal": k.col, "Ausprägung": f"{ref} (Referenz)", "Faktor": 1.0, "KI unten": np.nan, "KI oben": np.nan})
            for j, w in enumerate(k.werte):
                b, se = modell["beta"][pos + j], np.sqrt(modell["cov"][pos + j, pos + j])
                rows.append({"Merkmal": k.col, "Ausprägung": w, "Faktor": np.exp(b), "KI unten": np.exp(b - 1.96 * se),
                             "KI oben": np.exp(b + 1.96 * se)})
        pos += n
    return pd.DataFrame(rows)


def tarif_export(modell, kods, train, roh, grenzen):
    """Beitrag jedes Merkmalswerts zum linearen Prädiktor (log-Skala), für das Dashboard.

    Für jedes Merkmal: Beitrag je möglichem Rohwert (stetige Merkmale nach Kappung) und das
    Exposure-gewichtete Mittel im Training (Vergleich mit dem Portfolio).
    """
    out = {"achsenabschnitt": float(modell["beta"][0]), "alpha": float(modell["alpha"]), "kappung": grenzen,
           "merkmale": {}}
    pos = 1
    for k in kods:
        n = len(k.transform(train.iloc[[0]])[0])
        b = modell["beta"][pos:pos + n]
        mittel = float(np.average(k.transform(train) @ b, weights=train["Exposure"]))
        eintrag = {"kodierung": k.name, "mittel": mittel}
        if isinstance(k, Log):
            eintrag.update(typ="log", koeffizient=float(b[0]), verschiebung=k.shift)
        elif isinstance(k, Linear):
            eintrag.update(typ="linear", koeffizient=float(b[0]))
        else:
            if isinstance(k, Spline):
                werte = np.arange(roh[k.col].min(), roh[k.col].max() + 1)
                x = pd.DataFrame({k.col: np.minimum(werte, grenzen.get(k.col, werte.max()))})
            else:
                werte = np.array(sorted(roh[k.col].unique()) if k.col in roh else sorted(train[k.col].unique()))
                x = pd.DataFrame({k.col: werte})
            beitrag = k.transform(x) @ b
            eintrag.update(typ="tabelle", werte={str(w): float(v) for w, v in zip(werte, beitrag)})
            if isinstance(k, Gruppiert):
                eintrag["gruppen"] = {str(r): g for r, g in k.map.items()}
        out["merkmale"][k.col] = eintrag
        pos += n
    return out


def plot_stetig(modell, kods, train, pfad):
    stetig = [k for k in kods if isinstance(k, (Spline, Log, Linear))]
    fig, axes = plt.subplots(len(stetig), 1, figsize=(9, 3.4 * len(stetig)))
    axes = np.atleast_1d(axes)
    ref = train.iloc[[0]].copy()
    for ax, k in zip(axes, stetig):
        lo, hi = train[k.col].min(), train[k.col].max()
        x = np.unique(np.geomspace(max(lo, 1), hi, 200).round()) if k.col == "Density" else np.arange(lo, hi + 1)
        grid = pd.concat([ref] * len(x), ignore_index=True)
        grid[k.col] = x
        # nur die Spalten dieses Merkmals variieren; Faktor relativ zum Exposure-gewichteten Mittel
        pos = 1
        for kk in kods:
            n = len(kk.transform(ref)[0])
            if kk is k:
                sl = slice(pos, pos + n)
            pos += n
        Z = k.transform(grid)
        eta = Z @ modell["beta"][sl]
        zm = np.average(k.transform(train), axis=0, weights=train["Exposure"])
        eta = eta - zm @ modell["beta"][sl]
        cov = modell["cov"][sl, sl]
        d = Z - zm
        se = np.sqrt(np.einsum("ij,jk,ik->i", d, cov, d))
        ax.plot(x, np.exp(eta), color="tab:blue")
        ax.fill_between(x, np.exp(eta - 1.96 * se), np.exp(eta + 1.96 * se), color="tab:blue", alpha=0.2)
        ax.axhline(1, color="0.3", lw=0.6, ls=":")
        if k.col == "Density":
            ax.set_xscale("log")
        ax.set_title(f"{k.col} ({k.name}): Faktor relativ zum Portfoliomittel, 95 %-KI")
    fig.tight_layout()
    fig.savefig(pfad, dpi=110)
    plt.close(fig)


# ---------------------------------------------------------------------------


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    freq = lade_mit_split()
    roh_freq = freq.copy()
    roh_train = freq[~freq["Test"]]
    grenzen = kappungsgrenzen(roh_train)
    freq = vorbereiten(freq, grenzen)
    train = freq[~freq["Test"]].reset_index(drop=True)
    test = freq[freq["Test"]].reset_index(drop=True)
    folds = cv_folds(train["Profil"].to_numpy(), K_FOLDS, SEED)

    alpha0 = fitte(basis_kodierung() + [Kategorie("Region"), Linear("VehPower")], train, alpha=None)["alpha"]
    print(f"Kappung: {grenzen}, α (Auswahl) = {alpha0:.4f}")

    print("Auswahl VehPower")
    vp = {
        "ohne VehPower": lambda: basis_kodierung() + [Kategorie("Region")],
        "VehPower linear": lambda: basis_kodierung() + [Kategorie("Region"), Linear("VehPower")],
        "VehPower je Wert": lambda: basis_kodierung() + [Kategorie("Region"), Kategorie("VehPower")],
    }
    t_vp, wahl_vp = cv_vergleich(vp, train, folds, alpha0)
    vp_kod = {"ohne VehPower": [], "VehPower linear": [Linear("VehPower")], "VehPower je Wert": [Kategorie("VehPower")]}

    def mit_vp():
        return [type(k)(k.col) for k in vp_kod[wahl_vp]]

    print("Auswahl Regionsgruppierung")
    reg = {
        "22 einzeln": lambda: Kategorie("Region", "22 einzeln"),
        "Regionen < 1 % zusammen": lambda: Gruppiert("Region", "< 1 %", region_klein(0.01)),
        "8 Gruppen nach roher Frequenz": lambda: Gruppiert("Region", "8 roh", region_rang(8)),
        "4 Gruppen nach Effekt zusätzlich zu Density": lambda: Gruppiert("Region", "4 ber.", region_bereinigt(4, alpha0)),
        "6 Gruppen nach Effekt zusätzlich zu Density": lambda: Gruppiert("Region", "6 ber.", region_bereinigt(6, alpha0)),
        "8 Gruppen nach Effekt zusätzlich zu Density": lambda: Gruppiert("Region", "8 ber.", region_bereinigt(8, alpha0)),
    }
    t_reg, wahl_reg = cv_vergleich({n: (lambda b=b: basis_kodierung() + mit_vp() + [b()]) for n, b in reg.items()},
                                   train, folds, alpha0)

    def kodierung(variante):
        kods = basis_kodierung() + mit_vp() + [reg[wahl_reg]()]
        if variante == "b":
            kods.append(Kategorie("ExpKlasse"))
        return kods

    # GLM a und b auf dem ganzen Training
    glm = {}
    for v in ["a", "b"]:
        kods = kodierung(v)
        for k in kods:
            (k.fit_and_bounds if isinstance(k, Spline) else k.fit)(train)
            if isinstance(k, Kategorie):
                src = train[k.col].map(k.map) if isinstance(k, Gruppiert) else train[k.col]
                k.fit_ref = train.assign(_g=src).groupby("_g")["Exposure"].sum().idxmax()
        X = design(kods, train)
        m = fit_nb(X, train["ClaimNb"].to_numpy(), np.log(train["Exposure"].to_numpy()))
        m["_train1"] = train.iloc[[0]]
        glm[v] = {"modell": m, "kods": kods}
        print(f"GLM {v}: α = {m['alpha']:.4f}, {len(m['beta'])} Parameter")

    # Gradient Boosting a und b
    kategorien = {c: sorted(freq[c].unique()) for c in GBM_KATEGORIAL}
    gbm, gbm_tabellen = {}, {}
    for v in ["a", "b"]:
        print(f"GBM {v} Tuning")
        t, best = gbm_tuning(train, folds, kategorien, v == "b")
        gbm_tabellen[v] = t
        params = {k: int(best[k]) for k in ("max_leaf_nodes", "min_samples_leaf")}
        m = gbm_modell(params, int(best["Iterationen"]))
        m.fit(gbm_X(train, kategorien, v == "b"), train["ClaimNb"] / train["Exposure"], sample_weight=train["Exposure"])
        gbm[v] = m

    # ---- Test ----
    off_te = np.log(test["Exposure"].to_numpy())
    vorhersagen = {
        "Portfoliofrequenz (Nullmodell)": np.full(len(test), train["ClaimNb"].sum() / train["Exposure"].sum()) * test["Exposure"],
        "GLM a (ohne Laufzeit)": predict(glm["a"]["modell"], design(glm["a"]["kods"], test), off_te),
        "GLM b (mit Laufzeitklassen)": predict(glm["b"]["modell"], design(glm["b"]["kods"], test), off_te),
        "GBM a (ohne Laufzeit)": gbm["a"].predict(gbm_X(test, kategorien, False)) * test["Exposure"],
        "GBM b (mit Exposure)": gbm["b"].predict(gbm_X(test, kategorien, True)) * test["Exposure"],
    }
    y = test["ClaimNb"].to_numpy()
    voll = (test["Exposure"] >= 0.99).to_numpy()
    rows = []
    for name, mu in vorhersagen.items():
        mu = np.asarray(mu)
        rows.append({
            "Modell": name,
            "Deviance Test": poisson_deviance(y, mu),
            "Deviance Test, nur volle Jahre": poisson_deviance(y[voll], mu[voll]),
            "beobachtet/vorhergesagt": y.sum() / mu.sum(),
            "beob./vorh., nur volle Jahre": y[voll].sum() / mu[voll].sum(),
        })
    t_test = pd.DataFrame(rows).set_index("Modell")
    t_test["Verbesserung ggü. Nullmodell"] = t_test.loc["Portfoliofrequenz (Nullmodell)", "Deviance Test"] - t_test["Deviance Test"]

    kal = pd.DataFrame({
        name: kalibrierung(y, np.asarray(mu), test["ExpKlasse"])["beobachtet/vorhergesagt"]
        for name, mu in vorhersagen.items() if "Null" not in name
    })
    kal = kal.loc[[str(c) for c in pd.cut(test["Exposure"], EXPOSURE_GRENZEN).cat.categories if str(c) in kal.index]]

    # Faktoren und Plots für GLM b und a
    for v in ["a", "b"]:
        plot_stetig(glm[v]["modell"], glm[v]["kods"], train, OUT / f"glm_{v}_stetig.png")
    fak = {v: faktoren_kategorial(glm[v]["modell"], glm[v]["kods"]) for v in ["a", "b"]}
    zuordnung = pd.Series(glm["b"]["kods"][-2].map, name="Gruppe") if isinstance(glm["b"]["kods"][-2], Gruppiert) else None

    for v in ["a", "b"]:
        export = tarif_export(glm[v]["modell"], glm[v]["kods"], train, roh_freq, grenzen)
        (PROCESSED / f"tarif_frequenz_glm_{v}.json").write_text(json.dumps(export, indent=1), encoding="utf-8")

    fmt_test = {c: "{:.6f}" for c in t_test.columns}
    fmt_test.update({"beobachtet/vorhergesagt": "{:.3f}", "beob./vorh., nur volle Jahre": "{:.3f}"})
    fmt_fak = {"Faktor": "{:.3f}", "KI unten": "{:.3f}", "KI oben": "{:.3f}"}
    sections = [
        "# Teil 3 – Frequenzmodelle (automatisch erzeugt)",
        "Erzeugt von `src/teil3_frequenz.py`. Auswahl nur per Kreuzvalidierung auf dem Training "
        f"({K_FOLDS} Folds nach Profil); Testdaten nur in F3.5–F3.6.",
        "## F3.1 Kappung (99.5 %-Exposure-Quantil im Training)",
        md_table(pd.Series(grenzen, name="obere Grenze").rename_axis("Merkmal").to_frame()),
        "## F3.2 Auswahl VehPower (volles GLM, Region 22 einzeln)",
        "1-SE-Regel: gewählt wird die Variante mit den wenigsten Parametern, deren Abstand zur besten höchstens "
        "ihrem Standardfehler entspricht.",
        md_table(t_vp, {"Parameter": "{:d}"}),
        "## F3.3 Auswahl Regionsgruppierung (volles GLM)",
        md_table(t_reg, {"Parameter": "{:d}"}),
    ]
    if zuordnung is not None:
        z = zuordnung.to_frame().assign(Region=lambda d: d.index).groupby("Gruppe")["Region"].apply(lambda s: ", ".join(sorted(s)))
        sections += ["Zuordnung der gewählten Gruppierung (Training):", md_table(z.to_frame())]
    sections += [
        "## F3.4 Gradient Boosting: Tuning",
        f"Lernrate {GBM_LERNRATE}, Poisson-Verlust, Iterationen per Kreuzvalidierung gewählt.",
        "### Variante a", md_table(gbm_tabellen["a"], index=False),
        "### Variante b (Exposure als Merkmal)", md_table(gbm_tabellen["b"], index=False),
        "## F3.5 Vergleich auf den Testdaten",
        "Deviance = mittlere Poisson-Deviance pro Police (kleiner ist besser). "
        "„nur volle Jahre“ = Testpolicen mit Exposure ≥ 0.99; das ist die Laufzeit, für die der Tarif gerechnet wird.",
        md_table(t_test, fmt_test),
        "## F3.6 Kalibrierung auf den Testdaten je Laufzeitklasse (beobachtet / vorhergesagt)",
        md_table(kal.rename_axis("Exposure-Klasse"), {c: "{:.3f}" for c in kal.columns}),
        "## F3.7 GLM b: Faktoren der kategorialen Merkmale (exp(β), 95 %-KI)",
        md_table(fak["b"], fmt_fak, index=False),
        "## F3.8 GLM b: Verläufe der stetigen Merkmale",
        "![glm_b_stetig.png](glm_b_stetig.png)",
        "## F3.9 GLM a: Faktoren der kategorialen Merkmale",
        md_table(fak["a"], fmt_fak, index=False),
        "![glm_a_stetig.png](glm_a_stetig.png)",
    ]
    (OUT / "frequenz.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(t_test.to_string())
    print(kal.to_string())


if __name__ == "__main__":
    main()
