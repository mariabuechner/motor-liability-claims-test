"""Teil 2 – Visualisierung der Schadenfrequenz und der Schadenhöhen.

Liest die bereinigten Daten aus data/processed/ und erzeugt Tabellen und Plots
unter reports/teil2/.

Frequenz einer Gruppe = Summe ClaimNb / Summe Exposure (Schäden pro Versicherungsjahr).
Das 95 %-Konfidenzintervall ist das exakte Poisson-Intervall für die Schadenanzahl,
geteilt durch die Exposure. Es dient nur dazu, die Unsicherheit kleiner Gruppen zu zeigen.

Aufruf (aus dem Repo-Wurzelverzeichnis):
    python src/teil2_visualisierung.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import chi2

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "reports" / "teil2"

# Merkmale mit wenigen Werten: ein Punkt pro Wert.
EINZELWERTE = ["VehPower", "VehAge", "DrivAge", "BonusMalus"]
# Density hat >1'500 Werte: nur für die Darstellung in Klassen gleicher Exposure eingeteilt.
DENSITY_KLASSEN = 20
KATEGORIAL = ["VehBrand", "VehGas", "Area", "Region"]
# Nur für die Darstellung: Gruppen mit weniger Exposure bestimmen nicht die y-Achse.
YLIM_MIN_EXPOSURE = 100


def load():
    freq = pd.read_csv(PROCESSED / "freq_clean.csv")
    sev = pd.read_csv(PROCESSED / "sev_clean.csv")
    return freq, sev


def frequenz(df, by):
    g = df.groupby(by, observed=True).agg(Policen=("ClaimNb", "size"), Exposure=("Exposure", "sum"), Schaeden=("ClaimNb", "sum"))
    n = g["Schaeden"]
    lo = np.where(n > 0, chi2.ppf(0.025, 2 * n) / 2, 0.0)
    hi = chi2.ppf(0.975, 2 * (n + 1)) / 2
    g["Frequenz"] = n / g["Exposure"]
    g["KI_unten"] = lo / g["Exposure"]
    g["KI_oben"] = hi / g["Exposure"]
    g["Anteil_Exposure"] = g["Exposure"] / g["Exposure"].sum()
    return g


def md_table(df, fmt=None):
    fmt = fmt or {}
    df = df.reset_index()
    cols = list(df.columns)

    def f(c, v):
        if c in fmt:
            return fmt[c].format(v)
        if isinstance(v, (float, np.floating)):
            return f"{v:,.0f}" if float(v).is_integer() or abs(v) >= 1e4 else f"{v:,.4g}"
        if isinstance(v, (int, np.integer)):
            return f"{v:,}"
        return str(v)

    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(f(c, v) for c, v in zip(cols, r)) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


FMT_FREQ = {
    "Frequenz": "{:.4f}",
    "KI_unten": "{:.4f}",
    "KI_oben": "{:.4f}",
    "Anteil_Exposure": "{:.2%}",
    "Exposure": "{:,.1f}",
}


def savefig(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=110)
    plt.close(fig)
    return f"![{name}]({name})"


def plot_frequenz(ax, g, gesamt, titel, x=None, labels=None, logx=False):
    """Balken = Exposure (rechte Achse), Punkte mit 95 %-KI = Frequenz (linke Achse)."""
    x = np.asarray(g.index if x is None else x, dtype=float)
    ax2 = ax.twinx()
    ax2.set_zorder(0)
    ax.set_zorder(1)
    ax.patch.set_visible(False)
    if logx:
        breite = np.diff(np.log10(x)).min() * 0.8 if len(x) > 1 else 0.1
        ax2.bar(x, g["Exposure"], width=x * (10**breite - 1), color="0.85", align="center")
        ax.set_xscale("log")
        ax2.set_xscale("log")
    else:
        breite = np.diff(x).min() * 0.8 if len(x) > 1 else 0.8
        ax2.bar(x, g["Exposure"], width=breite, color="0.85")
    ax2.set_ylabel("Exposure (Jahre)", color="0.4")
    ax2.tick_params(axis="y", colors="0.4")

    gross = (g["Exposure"] >= YLIM_MIN_EXPOSURE).values
    yerr = np.vstack([g["Frequenz"] - g["KI_unten"], g["KI_oben"] - g["Frequenz"]])
    ax.errorbar(x[gross], g["Frequenz"][gross], yerr=yerr[:, gross], fmt="o", ms=3, color="tab:blue",
                ecolor="tab:blue", elinewidth=0.8, label="Frequenz mit 95 %-KI")
    if (~gross).any():
        ax.plot(x[~gross], g["Frequenz"][~gross], "o", ms=3, mfc="none", color="tab:blue",
                label=f"< {YLIM_MIN_EXPOSURE} Jahre Exposure (ohne KI)")
    ax.axhline(gesamt, color="tab:red", ls="--", lw=1, label=f"Portfolio {gesamt:.4f}")
    top = g.loc[gross, "KI_oben"].max() if gross.any() else g["KI_oben"].max()
    ax.set_ylim(0, top * 1.1)
    ausserhalb = g["Frequenz"] > top * 1.1
    if ausserhalb.any():
        ax.plot(x[ausserhalb.values], np.full(ausserhalb.sum(), top * 1.08), "^", color="tab:orange", ms=6,
                label="Punkt oberhalb der Achse")
    ax.set_ylabel("Frequenz (Schäden/Jahr)")
    ax.set_title(titel)
    if labels is not None:
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=60 if len(labels) > 8 else 0, ha="right" if len(labels) > 8 else "center",
                           fontsize=8)
    ax.legend(loc="upper right", fontsize=8)


# ---------------------------------------------------------------------------


def definitionen(freq):
    rate = freq["ClaimNb"] / freq["Exposure"]
    rows = [
        ("A: Σ ClaimNb / Σ Exposure", freq["ClaimNb"].sum() / freq["Exposure"].sum(), "Schäden pro Versicherungsjahr im Portfolio"),
        ("B: Mittelwert von ClaimNb / Exposure je Police", rate.mean(), "jede Police zählt gleich, egal wie lange versichert"),
        ("C: Mittelwert von ClaimNb je Police", freq["ClaimNb"].mean(), "ignoriert die Versicherungsdauer"),
        ("D: Anteil Policen mit ≥ 1 Schaden", (freq["ClaimNb"] > 0).mean(), "ignoriert Dauer und Mehrfachschäden"),
    ]
    return pd.DataFrame(rows, columns=["Definition", "Wert", "Bemerkung"]).set_index("Definition")


def nach_exposure(freq):
    klassen = pd.cut(freq["Exposure"], [0, 0.05, 0.1, 0.25, 0.5, 0.75, 0.99, 1.0])
    g = frequenz(freq.assign(Exposure_Klasse=klassen.astype(str)), "Exposure_Klasse")
    return g.loc[[str(c) for c in klassen.cat.categories]]


def density_klassen(freq):
    """Klassen mit ungefähr gleicher Exposure; dargestellt am Exposure-gewichteten Median."""
    order = freq.sort_values("Density")
    cum = order["Exposure"].cumsum() / order["Exposure"].sum()
    k = np.minimum((cum * DENSITY_KLASSEN).astype(int), DENSITY_KLASSEN - 1)
    # gleiche Density-Werte immer in dieselbe Klasse
    k = k.groupby(order["Density"]).transform("min")
    order = order.assign(Klasse=k.values)
    g = frequenz(order, "Klasse")
    bereich = order.groupby("Klasse")["Density"].agg(["min", "max", "median"])
    return g.join(bereich)


def severity_tabelle(sev):
    a = sev["ClaimAmount"]
    q = a.quantile([0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 0.999])
    rows = {"Anzahl": len(a), "Mittelwert": a.mean(), "Standardabweichung": a.std(), "Variationskoeffizient": a.std() / a.mean()}
    rows.update({f"Quantil {p:.1%}": v for p, v in q.items()})
    rows["Maximum"] = a.max()
    rows["Mittelwert ohne grösste 0.1 %"] = a[a <= a.quantile(0.999)].mean()
    return pd.DataFrame({"Wert": rows}).rename_axis("Kennzahl")


def plot_severity(sev):
    a = sev["ClaimAmount"].values
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    axes[0].hist(a, bins=np.logspace(0, np.log10(a.max()), 100), color="tab:blue")
    axes[0].set_xscale("log")
    axes[0].axvline(np.median(a), color="tab:green", ls="--", lw=1, label=f"Median {np.median(a):,.0f}")
    axes[0].axvline(a.mean(), color="tab:red", ls="--", lw=1, label=f"Mittelwert {a.mean():,.0f}")
    axes[0].set_title("Schadenhöhe: Histogramm (x log)")
    axes[0].set_ylabel("Anzahl Schäden")
    axes[0].legend(fontsize=8)

    s = np.sort(a)
    surv = 1 - np.arange(len(s)) / len(s)
    axes[1].loglog(s, surv, color="tab:blue")
    axes[1].set_title("Überschreitungswahrscheinlichkeit P(X > x), log-log")
    axes[1].set_xlabel("Schadenhöhe x")
    axes[1].grid(alpha=0.3, which="both")

    # mittlerer Exzess: durchschnittlicher Betrag über der Schwelle u, minus u
    u = np.quantile(a, np.linspace(0.5, 0.995, 80))
    me = [a[a > t].mean() - t for t in u]
    axes[2].plot(u, me, "o-", ms=3, color="tab:blue")
    axes[2].set_xscale("log")
    axes[2].set_title("Mittlerer Exzess E[X − u | X > u]")
    axes[2].set_xlabel("Schwelle u")
    axes[2].grid(alpha=0.3)
    return savefig(fig, "schadenhoehe_verteilung.png")


def plot_severity_ohne_spitzen(sev):
    """Wie stark prägen die häufigsten Einzelbeträge die Verteilung?"""
    a = sev["ClaimAmount"]
    top = a.value_counts().head(3).index
    fig, ax = plt.subplots(figsize=(10, 4))
    bins = np.logspace(0, np.log10(a.max()), 100)
    ax.hist(a, bins=bins, color="0.8", label="alle Schäden")
    ax.hist(a[~a.isin(top)], bins=bins, color="tab:blue", alpha=0.8,
            label="ohne die 3 häufigsten Beträge (" + ", ".join(f"{v:,.2f}" for v in top) + ")")
    ax.set_xscale("log")
    ax.set_title("Schadenhöhe mit und ohne die häufigsten Einzelbeträge")
    ax.legend(fontsize=8)
    return savefig(fig, "schadenhoehe_haeufige_betraege.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tabellen").mkdir(exist_ok=True)
    freq, sev = load()
    gesamt = freq["ClaimNb"].sum() / freq["Exposure"].sum()

    sections = [
        "# Teil 2 – Schadenfrequenz und Schadenhöhe (automatisch erzeugt)",
        "Erzeugt von `src/teil2_visualisierung.py` aus `data/processed/`. Nicht von Hand bearbeiten.",
        "In den Frequenzplots: graue Balken = Exposure (rechte Achse), blaue Punkte = Frequenz "
        "Σ ClaimNb / Σ Exposure mit exaktem 95 %-Poisson-Intervall (linke Achse), rote Linie = Portfolio. "
        f"Gruppen mit weniger als {YLIM_MIN_EXPOSURE} Jahren Exposure sind als leere Punkte ohne KI gezeichnet und bestimmen die y-Achse nicht; "
        "Punkte oberhalb der y-Achse sind als orange Dreiecke markiert. Alle Werte stehen in `tabellen/`.",
        "## T2.1 Definitionen der Schadenfrequenz im Vergleich",
        md_table(definitionen(freq), {"Wert": "{:.4f}"}),
        "## T2.2 Frequenz nach Versicherungsdauer",
        md_table(nach_exposure(freq), FMT_FREQ),
    ]

    # P2.1 Frequenz nach Versicherungsdauer
    g = nach_exposure(freq)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    plot_frequenz(ax, g, gesamt, "Frequenz nach Versicherungsdauer (Exposure-Klasse)", x=np.arange(len(g)), labels=list(g.index))
    sections += ["### P2.1 Frequenz nach Versicherungsdauer", savefig(fig, "frequenz_exposure.png")]

    # P2.2 numerische Merkmale
    fig, axes = plt.subplots(len(EINZELWERTE) + 1, 1, figsize=(12, 4.2 * (len(EINZELWERTE) + 1)))
    for ax, c in zip(axes, EINZELWERTE):
        g = frequenz(freq, c)
        g.to_csv(OUT / "tabellen" / f"frequenz_{c}.csv")
        plot_frequenz(ax, g, gesamt, f"Frequenz nach {c}")
    g = density_klassen(freq)
    g.to_csv(OUT / "tabellen" / "frequenz_Density_klassen.csv")
    plot_frequenz(axes[-1], g, gesamt, f"Frequenz nach Density ({DENSITY_KLASSEN} Klassen gleicher Exposure, x = Median)",
                  x=g["median"].values, logx=True)
    sections += ["## Frequenz je Merkmal", "### P2.2 Numerische Merkmale", savefig(fig, "frequenz_numerisch.png")]

    # P2.3 kategoriale Merkmale
    fig, axes = plt.subplots(len(KATEGORIAL), 1, figsize=(12, 4.2 * len(KATEGORIAL)))
    kat_tabellen = []
    for ax, c in zip(axes, KATEGORIAL):
        g = frequenz(freq, c)
        g = g.sort_values("Frequenz") if c in ("VehBrand", "Region") else g
        g.to_csv(OUT / "tabellen" / f"frequenz_{c}.csv")
        plot_frequenz(ax, g, gesamt, f"Frequenz nach {c}", x=np.arange(len(g)), labels=list(g.index))
        kat_tabellen += [f"### T2.3 {c}", md_table(g.drop(columns="Policen"), FMT_FREQ)]
    sections += ["### P2.3 Kategoriale Merkmale", savefig(fig, "frequenz_kategorial.png")]
    sections += ["## T2.3 Frequenztabellen kategoriale Merkmale", *kat_tabellen]

    sections += [
        "## T2.4 Frequenztabelle Density-Klassen",
        md_table(density_klassen(freq).drop(columns="Policen"), FMT_FREQ),
        "## Schadenhöhe",
        "### T2.5 Kennzahlen der Schadenhöhe",
        md_table(severity_tabelle(sev), {"Wert": "{:,.2f}"}),
        "### P2.4 Verteilung der Schadenhöhe",
        plot_severity(sev),
        "### P2.5 Einfluss der häufigsten Einzelbeträge",
        plot_severity_ohne_spitzen(sev),
    ]

    (OUT / "uebersicht.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(f"Geschrieben: {OUT.relative_to(ROOT)}/uebersicht.md, Plots und tabellen/")


if __name__ == "__main__":
    main()
