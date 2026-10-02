"""Teil 3 – Grundlage für die Kodierung der Merkmale im GLM.

Vergleicht je Merkmal mehrere Kodierungen (linear, logarithmiert, Klassen, Splines, ...)
und für Region mehrere Arten der Zusammenfassung. Bewertet wird mit 5-facher
Kreuzvalidierung auf den Trainingsdaten (Folds nach Merkmalsprofil gruppiert) und der
mittleren Poisson-Deviance. Die Testdaten werden hier nicht verwendet.

Jedes Merkmal wird einzeln betrachtet (Achsenabschnitt + Merkmal, Offset log(Exposure)).
Für Region zusätzlich zusammen mit Density, weil beide geografisch sind.

Aufruf:
    python src/teil3_merkmale.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import patsy

from teil3_grundlagen import OUT, SEED, cv_folds, fit_nb, lade_mit_split, poisson_deviance, predict

K_FOLDS = 5


# ---------------------------------------------------------------------------
# Kodierungen: fit(train) lernt nur aus den Trainingsdaten, transform(df) liefert Spalten ohne Achsenabschnitt
# ---------------------------------------------------------------------------


class Linear:
    def __init__(self, col):
        self.col, self.name = col, "linear"

    def fit(self, df):
        return self

    def transform(self, df):
        return df[[self.col]].to_numpy(float)


class Log:
    def __init__(self, col, shift=0):
        self.col, self.shift = col, shift
        self.name = "log(x)" if shift == 0 else f"log(x+{shift})"

    def fit(self, df):
        return self

    def transform(self, df):
        return np.log(df[[self.col]].to_numpy(float) + self.shift)


class Klassen:
    """Klassen mit ungefähr gleicher Exposure; Grenzen aus den Trainingsdaten."""

    def __init__(self, col, k):
        self.col, self.k, self.name = col, k, f"{k} Klassen"

    def fit(self, df):
        d = df.sort_values(self.col)
        cum = d["Exposure"].cumsum().to_numpy() / d["Exposure"].sum()
        x = d[self.col].to_numpy()
        grenzen = [x[np.searchsorted(cum, q)] for q in np.arange(1, self.k) / self.k]
        # Grenze g trennt x ≤ g von x > g; Grenzen am Maximum ergeben leere Klassen
        self.grenzen = np.unique([g for g in grenzen if g < x.max()])
        return self

    def transform(self, df):
        klasse = np.searchsorted(self.grenzen, df[self.col].to_numpy(), side="left")
        return np.eye(len(self.grenzen) + 1)[klasse][:, 1:]


class Spline:
    def __init__(self, col, df_):
        self.col, self.df_, self.name = col, df_, f"Spline ({df_} FG)"

    def fit(self, df):
        self.info = patsy.dmatrix(f"cr({self.col}, df={self.df_}, constraints='center') - 1", df).design_info
        return self

    def transform(self, df):
        x = df[[self.col]].clip(self._min, self._max) if hasattr(self, "_min") else df[[self.col]]
        return np.asarray(patsy.build_design_matrices([self.info], x)[0])

    def fit_and_bounds(self, df):
        self._min, self._max = df[self.col].min(), df[self.col].max()
        return self.fit(df)


class Kategorie:
    """Jeder Wert eine eigene Kategorie; Referenz = häufigster Wert."""

    def __init__(self, col, name="je Wert"):
        self.col, self.name = col, name

    def fit(self, df):
        e = df.groupby(self.col)["Exposure"].sum().sort_values(ascending=False)
        self.werte = list(e.index[1:])
        return self

    def transform(self, df):
        x = df[self.col].to_numpy()
        return np.column_stack([(x == w).astype(float) for w in self.werte])


class Gruppiert(Kategorie):
    """Kategorie über eine Zuordnung Wert → Gruppe, die aus den Trainingsdaten gelernt wird."""

    def __init__(self, col, name, zuordnen):
        super().__init__(col, name)
        self.zuordnen = zuordnen

    def fit(self, df):
        self.map = self.zuordnen(df)
        return super().fit(df.assign(**{self.col: df[self.col].map(self.map)}))

    def transform(self, df):
        return super().transform(df.assign(**{self.col: df[self.col].map(self.map).fillna(self.werte[0] if self.werte else "")}))


def region_klein(schwelle):
    def f(df):
        e = df.groupby("Region")["Exposure"].sum()
        anteil = e / e.sum()
        return {r: ("kleine Regionen" if anteil[r] < schwelle else r) for r in e.index}

    return f


def region_rang(k):
    """Regionen nach Frequenz im Training sortiert, dann in k Gruppen gleicher Exposure geteilt."""

    def f(df):
        g = df.groupby("Region").agg(n=("ClaimNb", "sum"), e=("Exposure", "sum"))
        g = g.assign(freq=g["n"] / g["e"]).sort_values("freq")
        cum = (g["e"].cumsum() - g["e"] / 2) / g["e"].sum()
        gruppe = np.minimum((cum * k).astype(int), k - 1)
        return {r: f"Gruppe {gr + 1}" for r, gr in gruppe.items()}

    return f


KANDIDATEN = {
    "DrivAge": [Linear("DrivAge"), Log("DrivAge"), Klassen("DrivAge", 5), Klassen("DrivAge", 10), Klassen("DrivAge", 20),
                Spline("DrivAge", 4), Spline("DrivAge", 8)],
    "BonusMalus": [Linear("BonusMalus"), Log("BonusMalus"), Klassen("BonusMalus", 5), Klassen("BonusMalus", 10),
                   Spline("BonusMalus", 4), Spline("BonusMalus", 8)],
    "VehAge": [Linear("VehAge"), Log("VehAge", 1), Klassen("VehAge", 5), Klassen("VehAge", 10), Spline("VehAge", 4),
               Spline("VehAge", 8)],
    "VehPower": [Linear("VehPower"), Log("VehPower"), Kategorie("VehPower"), Spline("VehPower", 4)],
    "Density": [Linear("Density"), Log("Density"), Klassen("Density", 5), Klassen("Density", 10), Klassen("Density", 20),
                Spline("Density", 4)],
}

REGION_KANDIDATEN = [
    Kategorie("Region", "22 einzeln"),
    Gruppiert("Region", "Regionen < 1 % Exposure zusammen", region_klein(0.01)),
    Gruppiert("Region", "Regionen < 2 % Exposure zusammen", region_klein(0.02)),
    Gruppiert("Region", "3 Gruppen nach Frequenz", region_rang(3)),
    Gruppiert("Region", "5 Gruppen nach Frequenz", region_rang(5)),
    Gruppiert("Region", "8 Gruppen nach Frequenz", region_rang(8)),
]


# ---------------------------------------------------------------------------


def design(kodierungen, df):
    teile = [np.ones((len(df), 1))] + [k.transform(df) for k in kodierungen]
    return np.hstack(teile)


def fitte(kodierungen, train, alpha):
    for k in kodierungen:
        (k.fit_and_bounds if isinstance(k, Spline) else k.fit)(train)
    X = design(kodierungen, train)
    return fit_nb(X, train["ClaimNb"].to_numpy(), np.log(train["Exposure"].to_numpy()), alpha=alpha, cov=False)


def cv_deviance(kodierungen, train, folds, alpha):
    werte = []
    for k in range(K_FOLDS):
        tr, va = train[folds != k], train[folds == k]
        m = fitte(kodierungen, tr, alpha)
        mu = predict(m, design(kodierungen, va), np.log(va["Exposure"].to_numpy()))
        werte.append(poisson_deviance(va["ClaimNb"], mu))
    return np.array(werte)


def referenz_alpha(train):
    """Ein gemeinsames α für alle Vergleiche, geschätzt in einem Modell mit allen Merkmalen in 10 Klassen."""
    kod = [Klassen(c, 10) for c in ["DrivAge", "BonusMalus", "VehAge", "Density"]] + [
        Kategorie("VehPower"), Kategorie("VehBrand"), Kategorie("VehGas"), Kategorie("Region")
    ]
    return fitte(kod, train, alpha=None)["alpha"]


def vergleich(train, folds, alpha, kandidaten, basis=()):
    basis_fold = cv_deviance(list(basis), train, folds, alpha)
    rows, je_fold = [], []
    for k in kandidaten:
        kods = list(basis) + [k]
        m = fitte(kods, train, alpha)
        d = cv_deviance(kods, train, folds, alpha)
        je_fold.append(d)
        rows.append({"Kodierung": k.name, "Parameter": len(m["beta"]) - 1 - sum(len(b.transform(train.iloc[:1])[0]) for b in basis),
                     "CV-Deviance": d.mean(), "Verbesserung ggü. ohne": basis_fold.mean() - d.mean()})
    t = pd.DataFrame(rows)
    beste = je_fold[int(t["CV-Deviance"].idxmin())]
    # Abstand je Fold gepaart: dieselben Folds für alle Kodierungen
    t["Abstand zur besten"] = [(d - beste).mean() for d in je_fold]
    t["± SE Abstand"] = [(d - beste).std(ddof=1) / np.sqrt(K_FOLDS) for d in je_fold]
    return t, basis_fold.mean()


def md(t, basis_dev):
    cols = list(t.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in t.itertuples(index=False):
        vals = []
        for c, v in zip(cols, r):
            vals.append(f"{v:.6f}" if isinstance(v, float) else str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return f"CV-Deviance ohne dieses Merkmal: {basis_dev:.6f}\n\n" + "\n".join(lines)


def plot_merkmal(col, kandidaten, train, alpha, ax):
    g = train.groupby(col).agg(n=("ClaimNb", "sum"), e=("Exposure", "sum"))
    gesamt = train["ClaimNb"].sum() / train["Exposure"].sum()
    if col == "Density":
        x = np.unique(np.quantile(train[col], np.linspace(0, 1, 300)))
        b = pd.qcut(train[col], 30, duplicates="drop")
        gg = train.groupby(b, observed=True).agg(n=("ClaimNb", "sum"), e=("Exposure", "sum"), x=(col, "median"))
        ax.scatter(gg["x"], gg["n"] / gg["e"] / gesamt, s=12, color="0.5", label="beobachtet (30 Klassen)")
        ax.set_xscale("log")
    else:
        x = np.arange(train[col].min(), train[col].max() + 1)
        gross = g["e"] >= 100
        ax.scatter(g.index[gross], (g["n"] / g["e"])[gross] / gesamt, s=10, color="0.5", label="beobachtet (≥ 100 Jahre)")
    grid = pd.DataFrame({col: x, "Exposure": 1.0})
    for k in kandidaten:
        m = fitte([k], train, alpha)
        f = predict(m, design([k], grid), np.zeros(len(grid)))
        ax.plot(x, f / gesamt, lw=1.2, label=k.name, drawstyle="steps-mid" if isinstance(k, (Klassen, Kategorie)) else "default")
    ax.axhline(1, color="0.3", lw=0.6, ls=":")
    ax.set_title(f"{col}: geschätzter Faktor relativ zur Portfoliofrequenz (Training)")
    ax.set_ylabel("Faktor")
    ax.legend(fontsize=7, ncol=2)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    freq = lade_mit_split()
    train = freq[~freq["Test"]].reset_index(drop=True)
    folds = cv_folds(train["Profil"].to_numpy(), K_FOLDS, SEED)
    alpha = referenz_alpha(train)
    print(f"α = {alpha:.4f}")

    sections = [
        "# Teil 3 – Kodierung der Merkmale im GLM (automatisch erzeugt)",
        f"Erzeugt von `src/teil3_merkmale.py`. Nur Trainingsdaten, {K_FOLDS}-fache Kreuzvalidierung mit Folds nach "
        "Merkmalsprofil. Metrik: mittlere Poisson-Deviance pro Police auf dem jeweils ausgelassenen Fold "
        "(kleiner ist besser). „± SE Abstand“ = Standardfehler des Abstands zur besten Kodierung, gepaart über dieselben Folds; ein Abstand von weniger als etwa 2 SE ist nicht klar von der besten unterscheidbar. Negativ-Binomial-GLM mit Log-Link und Offset "
        f"log(Exposure); α für alle Vergleiche fest = {alpha:.4f} (geschätzt im Modell mit allen Merkmalen in "
        "10 Klassen). Klassen = ungefähr gleiche Exposure je Klasse, Grenzen aus den Trainingsdaten. "
        "Spline = natürlicher kubischer Regressionsspline mit FG Freiheitsgraden.",
        "Achtung: Jedes Merkmal wird einzeln betrachtet. Teile der Effekte können von anderen Merkmalen stammen.",
    ]
    fig, axes = plt.subplots(len(KANDIDATEN), 1, figsize=(11, 4.2 * len(KANDIDATEN)))
    for i, (col, kand) in enumerate(KANDIDATEN.items()):
        t, basis = vergleich(train, folds, alpha, kand)
        t.to_csv(OUT / f"kodierung_{col}.csv", index=False)
        sections += [f"## M3.{i + 1} {col}", md(t, basis)]
        plot_merkmal(col, kand, train, alpha, axes[i])
        print(col, "fertig")
    fig.tight_layout()
    fig.savefig(OUT / "kodierung_merkmale.png", dpi=110)
    plt.close(fig)

    t, basis = vergleich(train, folds, alpha, REGION_KANDIDATEN)
    sections += [f"## M3.{len(KANDIDATEN) + 1} Region allein", md(t, basis)]
    t2, basis2 = vergleich(train, folds, alpha, REGION_KANDIDATEN, basis=[Log("Density")])
    sections += [
        f"## M3.{len(KANDIDATEN) + 2} Region zusätzlich zu Density",
        "Density hier nur als Kontrolle mit log(x) im Modell, damit sichtbar wird, was Region über Density hinaus erklärt.",
        md(t2, basis2),
    ]
    zuordnung = pd.DataFrame({k.name: pd.Series(k.fit(train).map) for k in REGION_KANDIDATEN if isinstance(k, Gruppiert)})
    e = train.groupby("Region").agg(n=("ClaimNb", "sum"), e=("Exposure", "sum"))
    zuordnung.insert(0, "Frequenz", (e["n"] / e["e"]).round(4))
    zuordnung.insert(0, "Anteil Exposure", (e["e"] / e["e"].sum()).map("{:.2%}".format))
    zuordnung = zuordnung.sort_values("Frequenz")
    sections += [f"## M3.{len(KANDIDATEN) + 3} Zuordnung der Regionen (Training)",
                 "| Region | " + " | ".join(zuordnung.columns) + " |\n|" + "---|" * (len(zuordnung.columns) + 1) + "\n" +
                 "\n".join("| " + r + " | " + " | ".join(map(str, v)) + " |" for r, v in zip(zuordnung.index, zuordnung.values))]
    sections += ["## P3.1 Geschätzte Verläufe je Kodierung", "![kodierung_merkmale.png](kodierung_merkmale.png)"]
    (OUT / "merkmale.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print("Geschrieben: reports/teil3/merkmale.md")


if __name__ == "__main__":
    main()
