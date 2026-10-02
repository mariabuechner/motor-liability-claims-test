"""Teil 1 – Datenverständnis: Übersicht, Plausibilität und Konsistenz der Rohdaten.

Das Skript verändert keine Daten und trifft keine Bereinigungsentscheidungen.
Es erzeugt Tabellen und Plots unter reports/teil1/, auf die in ENTSCHEIDUNGEN.md
verwiesen werden kann.

Aufruf (aus dem Repo-Wurzelverzeichnis):
    python src/teil1_datenuebersicht.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "reports" / "teil1"

NUM_VARS = ["VehPower", "VehAge", "DrivAge", "BonusMalus", "Density"]
CAT_VARS = ["VehBrand", "VehGas", "Area", "Region"]
FEATURES = NUM_VARS + CAT_VARS


def load():
    freq = pd.read_csv(RAW / "freMTPL2freq.csv")
    sev = pd.read_csv(RAW / "freMTPL2sev.csv")
    return freq, sev


def md_table(df, index=True, floatfmt="{:,.4g}"):
    """Einfache Markdown-Tabelle ohne Zusatzpaket."""
    if index:
        df = df.reset_index()

    def fmt(v):
        if isinstance(v, (float, np.floating)):
            if np.isnan(v):
                return "–"
            if "%" not in floatfmt and (float(v).is_integer() or abs(v) >= 1e4):
                return f"{v:,.0f}"
            return floatfmt.format(v)
        if isinstance(v, (int, np.integer)):
            return f"{v:,}"
        return str(v)

    header = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, sep, *rows])


def savefig(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=110)
    plt.close(fig)
    return f"![{name}]({name})"


# ---------------------------------------------------------------------------
# Tabellen
# ---------------------------------------------------------------------------


def variable_overview(freq, sev):
    rows = []
    for name, df in [("freq", freq), ("sev", sev)]:
        for c in df.columns:
            s = df[c]
            numeric = pd.api.types.is_numeric_dtype(s)
            rows.append(
                {
                    "Datei": name,
                    "Variable": c,
                    "Typ": str(s.dtype),
                    "fehlend": int(s.isna().sum()),
                    "eindeutige Werte": int(s.nunique()),
                    "min": s.min() if numeric else "",
                    "Median": s.median() if numeric else "",
                    "max": s.max() if numeric else "",
                }
            )
    return pd.DataFrame(rows)


def consistency(freq, sev):
    n_sev = sev.groupby("IDpol").size().rename("Zeilen_sev")
    j = freq.set_index("IDpol")[["ClaimNb"]].join(n_sev, how="outer")
    in_freq = j["ClaimNb"].notna()
    j["Zeilen_sev"] = j["Zeilen_sev"].fillna(0)
    checks = {
        "IDpol doppelt in freq": int(freq["IDpol"].duplicated().sum()),
        "IDpol nicht ganzzahlig (freq)": int((freq["IDpol"] % 1 != 0).sum()),
        "sev-Zeilen ohne Police in freq": int((~sev["IDpol"].isin(freq["IDpol"])).sum()),
        "Policen mit ClaimNb > 0": int((j["ClaimNb"] > 0).sum()),
        "Summe ClaimNb in freq": int(freq["ClaimNb"].sum()),
        "Zeilen in sev": len(sev),
        "Policen mit ClaimNb > 0, aber ohne Betrag in sev": int(((j["ClaimNb"] > 0) & (j["Zeilen_sev"] == 0)).sum()),
        "Policen mit ClaimNb = 0, aber Betrag in sev": int((in_freq & (j["ClaimNb"] == 0) & (j["Zeilen_sev"] > 0)).sum()),
        "Policen mit ClaimNb ≠ Anzahl sev-Zeilen": int((in_freq & (j["ClaimNb"] != j["Zeilen_sev"])).sum()),
        "ClaimAmount ≤ 0": int((sev["ClaimAmount"] <= 0).sum()),
    }
    return pd.DataFrame({"Prüfung": list(checks), "Anzahl": list(checks.values())})


def anomalies(freq, sev):
    """Auffällige Wertebereiche, jeweils mit Zeilen, Exposure und Schäden."""
    cases = {
        "Exposure > 1 Jahr": freq["Exposure"] > 1,
        "Exposure < 0.05 Jahre (≈ 18 Tage)": freq["Exposure"] < 0.05,
        "Exposure < 0.05 und ClaimNb > 0": (freq["Exposure"] < 0.05) & (freq["ClaimNb"] > 0),
        "ClaimNb ≥ 4": freq["ClaimNb"] >= 4,
        "VehAge ≥ 99": freq["VehAge"] >= 99,
        "VehAge zwischen 40 und 98": freq["VehAge"].between(40, 98),
        "DrivAge = 99": freq["DrivAge"] == 99,
        "DrivAge ≥ 90": freq["DrivAge"] >= 90,
        "DrivAge < 21 und BonusMalus = 50": (freq["DrivAge"] < 21) & (freq["BonusMalus"] == 50),
        "BonusMalus > 150": freq["BonusMalus"] > 150,
        "Density = 27000 (Maximalwert)": freq["Density"] == 27000,
    }
    rows = []
    for name, m in cases.items():
        rows.append(
            {
                "Auffälligkeit": name,
                "Zeilen": int(m.sum()),
                "Exposure": float(freq.loc[m, "Exposure"].sum()),
                "Schäden": int(freq.loc[m, "ClaimNb"].sum()),
            }
        )
    amount = sev["ClaimAmount"]
    for name, m in {
        "ClaimAmount < 10": amount < 10,
        "ClaimAmount < 100": amount < 100,
        "ClaimAmount > 100'000": amount > 1e5,
    }.items():
        rows.append({"Auffälligkeit": name, "Zeilen": int(m.sum()), "Exposure": np.nan, "Schäden": int(m.sum())})
    return pd.DataFrame(rows)


def high_claimnb(freq):
    return freq[freq["ClaimNb"] >= 4].sort_values("ClaimNb").astype({"IDpol": "int64"})


def identical_profiles(freq):
    sizes = freq.groupby(FEATURES).size()
    dist = sizes.value_counts().sort_index()
    table = pd.DataFrame({"Policen mit genau diesem Profil": dist.index, "Anzahl Profile": dist.values})
    table["Zeilen"] = table["Policen mit genau diesem Profil"] * table["Anzahl Profile"]
    big = table["Policen mit genau diesem Profil"] > 5
    tail = pd.DataFrame(
        {
            "Policen mit genau diesem Profil": ["> 5"],
            "Anzahl Profile": [table.loc[big, "Anzahl Profile"].sum()],
            "Zeilen": [table.loc[big, "Zeilen"].sum()],
        }
    )
    table = table[~big].astype({"Policen mit genau diesem Profil": str})
    return pd.concat([table, tail], ignore_index=True)


def area_density(freq):
    return freq.groupby("Area")["Density"].agg(["min", "median", "max", "count"])


def amount_concentration(sev):
    a = sev["ClaimAmount"].sort_values(ascending=False).reset_index(drop=True)
    total = a.sum()
    rows = []
    for share in [0.0001, 0.001, 0.01, 0.1, 0.5]:
        k = max(1, int(round(share * len(a))))
        rows.append(
            {"grösste Schäden (Anteil)": f"{share:.2%}", "Anzahl": k, "Anteil an Schadensumme": a.iloc[:k].sum() / total}
        )
    return pd.DataFrame(rows)


def frequent_amounts(sev):
    vc = sev["ClaimAmount"].value_counts().head(10)
    return pd.DataFrame({"ClaimAmount": vc.index, "Anzahl": vc.values, "Anteil": vc.values / len(sev)})


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------


def plot_numeric(freq):
    fig, axes = plt.subplots(len(NUM_VARS), 1, figsize=(10, 3.2 * len(NUM_VARS)))
    for ax, c in zip(axes, NUM_VARS):
        if c == "Density":
            bins = np.logspace(0, np.log10(freq[c].max() + 1), 60)
            ax.set_xscale("log")
        else:
            bins = np.arange(freq[c].min(), freq[c].max() + 2) - 0.5
        ax.hist(freq[c], bins=bins, weights=freq["Exposure"], color="tab:blue")
        ax.set_yscale("log")
        ax.set_title(f"{c}: Exposure (Jahre) je Wert, y-Achse logarithmisch")
        ax.set_ylabel("Exposure")
    return savefig(fig, "numerische_merkmale.png")


def plot_categorical(freq):
    fig, axes = plt.subplots(len(CAT_VARS), 1, figsize=(10, 3.4 * len(CAT_VARS)))
    for ax, c in zip(axes, CAT_VARS):
        e = freq.groupby(c)["Exposure"].sum().sort_values(ascending=False)
        ax.bar(e.index.astype(str), e.values, color="tab:blue")
        ax.set_title(f"{c}: Exposure (Jahre) je Ausprägung")
        ax.tick_params(axis="x", rotation=60 if c == "Region" else 0, labelsize=8)
    return savefig(fig, "kategoriale_merkmale.png")


def plot_exposure_claimnb(freq):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].hist(freq["Exposure"], bins=np.arange(0, 2.05, 0.02), color="tab:blue")
    axes[0].axvline(1, color="tab:red", ls="--", lw=1)
    axes[0].set_yscale("log")
    axes[0].set_title("Exposure: Anzahl Policen (y log), rote Linie = 1 Jahr")
    vc = freq["ClaimNb"].value_counts().sort_index()
    axes[1].bar(vc.index.astype(str), vc.values, color="tab:blue")
    axes[1].set_yscale("log")
    axes[1].set_title("ClaimNb: Anzahl Policen (y log)")
    return savefig(fig, "exposure_claimnb.png")


def plot_amounts(sev):
    a = sev["ClaimAmount"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].hist(a, bins=np.logspace(0, np.log10(a.max()), 80), color="tab:blue")
    axes[0].set_xscale("log")
    axes[0].set_title("ClaimAmount: Histogramm (x log)")
    s = np.sort(a.values)[::-1]
    axes[1].plot(np.arange(1, len(s) + 1) / len(s), np.cumsum(s) / s.sum(), color="tab:blue")
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Anteil der grössten Schäden")
    axes[1].set_ylabel("Anteil an Schadensumme")
    axes[1].set_title("Konzentration der Schadensumme")
    axes[1].grid(alpha=0.3)
    return savefig(fig, "schadenhoehen.png")


def plot_area_density(freq):
    fig, ax = plt.subplots(figsize=(8, 4))
    areas = sorted(freq["Area"].unique())
    ax.boxplot([freq.loc[freq["Area"] == a, "Density"] for a in areas], tick_labels=areas, whis=(0, 100))
    ax.set_yscale("log")
    ax.set_xlabel("Area")
    ax.set_ylabel("Density (log)")
    ax.set_title("Density je Area (Whisker = min/max)")
    return savefig(fig, "area_vs_density.png")


def plot_drivage_bm(freq):
    young = freq[freq["DrivAge"] <= 30]
    share = young.groupby("DrivAge").apply(
        lambda d: d.loc[d["BonusMalus"] == 50, "Exposure"].sum() / d["Exposure"].sum(), include_groups=False
    )
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(share.index, share.values, color="tab:blue")
    ax.set_xlabel("DrivAge")
    ax.set_ylabel("Exposure-Anteil mit BonusMalus = 50")
    ax.set_title("Junge Fahrer: Anteil mit tiefstem BonusMalus-Wert")
    return savefig(fig, "drivage_bonusmalus50.png")


# ---------------------------------------------------------------------------


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    freq, sev = load()

    sections = [
        "# Teil 1 – Datenübersicht (automatisch erzeugt)",
        "Erzeugt von `src/teil1_datenuebersicht.py` aus `data/raw/`. Nicht von Hand bearbeiten.",
        f"- freq: {len(freq):,} Zeilen × {freq.shape[1]} Spalten, Exposure gesamt {freq['Exposure'].sum():,.1f} Jahre",
        f"- sev: {len(sev):,} Zeilen × {sev.shape[1]} Spalten, Schadensumme {sev['ClaimAmount'].sum():,.0f}",
        "## T1.1 Variablenübersicht",
        md_table(variable_overview(freq, sev), index=False),
        "## T1.2 Konsistenz freq ↔ sev",
        md_table(consistency(freq, sev), index=False),
        "## T1.3 Auffällige Wertebereiche",
        md_table(anomalies(freq, sev), index=False, floatfmt="{:,.1f}"),
        "## T1.4 Policen mit ClaimNb ≥ 4",
        md_table(high_claimnb(freq), index=False),
        "## T1.5 Policen mit identischem Merkmalsprofil",
        "Profil = alle 9 Merkmale ausser IDpol, Exposure und ClaimNb.",
        md_table(identical_profiles(freq), index=False),
        "## T1.6 Density je Area",
        md_table(area_density(freq)),
        "## T1.7 Konzentration der Schadensumme",
        md_table(amount_concentration(sev), index=False, floatfmt="{:.1%}"),
        "## T1.8 Häufigste Schadenbeträge",
        md_table(frequent_amounts(sev), index=False, floatfmt="{:,.4f}"),
        "## Plots",
        "### P1.1 Numerische Merkmale",
        plot_numeric(freq),
        "### P1.2 Kategoriale Merkmale",
        plot_categorical(freq),
        "### P1.3 Exposure und ClaimNb",
        plot_exposure_claimnb(freq),
        "### P1.4 Schadenhöhen",
        plot_amounts(sev),
        "### P1.5 Area vs. Density",
        plot_area_density(freq),
        "### P1.6 Junge Fahrer und BonusMalus",
        plot_drivage_bm(freq),
    ]
    (OUT / "uebersicht.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(f"Geschrieben: {OUT.relative_to(ROOT)}/uebersicht.md und Plots")


if __name__ == "__main__":
    main()
