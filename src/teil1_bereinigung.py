"""Teil 1 – Bereinigung der Rohdaten gemäss den Entscheidungen in ENTSCHEIDUNGEN.md.

Liest data/raw/, schreibt data/processed/freq_clean.csv und sev_clean.csv
sowie ein Protokoll mit den betroffenen Zeilen nach reports/teil1/bereinigung.md.

Aufruf (aus dem Repo-Wurzelverzeichnis):
    python src/teil1_bereinigung.py
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REPORT = ROOT / "reports" / "teil1" / "bereinigung.md"

# Entfernungsregeln: (Kurzname, Beschreibung, Bedingung auf freq).
# Policen, auf die eine Regel zutrifft, werden mit allen zugehörigen Schadenbeträgen entfernt.
REGELN = [
    ("exposure_gt_1", "Exposure > 1 Jahr", lambda f: f["Exposure"] > 1),
    ("vehage_ge_99", "VehAge ≥ 99 (Platzhalter)", lambda f: f["VehAge"] >= 99),
    ("vehage_40_98", "VehAge zwischen 40 und 98", lambda f: f["VehAge"].between(40, 98)),
    ("drivage_99", "DrivAge = 99 (Platzhalter)", lambda f: f["DrivAge"] == 99),
]

# Bewusst NICHT bereinigt (siehe ENTSCHEIDUNGEN.md): kurze Exposure, Policen mit
# vielen Schäden inkl. Cluster, junge Fahrer mit BonusMalus 50, Schadenhöhen.


def main():
    freq = pd.read_csv(RAW / "freMTPL2freq.csv")
    sev = pd.read_csv(RAW / "freMTPL2sev.csv")
    freq["IDpol"] = freq["IDpol"].astype("int64")

    rows = []
    keep = pd.Series(True, index=freq.index)
    for key, beschreibung, regel in REGELN:
        m = regel(freq)
        neu = m & keep
        rows.append(
            {
                "Regel": beschreibung,
                "Zeilen (für sich)": int(m.sum()),
                "davon neu entfernt": int(neu.sum()),
                "Exposure entfernt": float(freq.loc[neu, "Exposure"].sum()),
                "Schäden entfernt": int(freq.loc[neu, "ClaimNb"].sum()),
            }
        )
        keep &= ~m

    freq_clean = freq[keep].reset_index(drop=True)
    sev_clean = sev[sev["IDpol"].isin(freq_clean["IDpol"])].reset_index(drop=True)

    # Konsistenz nach der Bereinigung
    n_sev = sev_clean.groupby("IDpol").size()
    nb = freq_clean.set_index("IDpol")["ClaimNb"]
    assert (nb[nb > 0] == n_sev.reindex(nb[nb > 0].index, fill_value=0)).all()
    assert n_sev.index.isin(nb.index).all()

    PROCESSED.mkdir(parents=True, exist_ok=True)
    freq_clean.to_csv(PROCESSED / "freq_clean.csv", index=False)
    sev_clean.to_csv(PROCESSED / "sev_clean.csv", index=False)

    log = pd.DataFrame(rows)
    summary = pd.DataFrame(
        {
            "": ["Policen", "Exposure (Jahre)", "Schäden (ClaimNb)", "Zeilen sev", "Schadensumme"],
            "roh": [len(freq), freq["Exposure"].sum(), freq["ClaimNb"].sum(), len(sev), sev["ClaimAmount"].sum()],
            "bereinigt": [
                len(freq_clean),
                freq_clean["Exposure"].sum(),
                freq_clean["ClaimNb"].sum(),
                len(sev_clean),
                sev_clean["ClaimAmount"].sum(),
            ],
        }
    )
    summary["Veränderung"] = summary["bereinigt"] / summary["roh"] - 1

    def table(df, fmt):
        cols = list(df.columns)
        lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
        for r in df.itertuples(index=False):
            lines.append("| " + " | ".join(fmt(c, v) for c, v in zip(cols, r)) + " |")
        return "\n".join(lines)

    def fmt(col, v):
        if isinstance(v, str):
            return v
        if col == "Veränderung":
            return f"{v:+.2%}"
        if float(v).is_integer():
            return f"{v:,.0f}"
        return f"{v:,.1f}"

    REPORT.write_text(
        "\n\n".join(
            [
                "# Teil 1 – Bereinigungsprotokoll (automatisch erzeugt)",
                "Erzeugt von `src/teil1_bereinigung.py`. Regeln werden der Reihe nach angewendet; "
                "„davon neu entfernt“ zählt nur Policen, die nicht schon eine frühere Regel entfernt hat. "
                "Mit einer Police werden auch ihre Schadenbeträge aus sev entfernt.",
                "## B1.1 Entfernte Policen je Regel",
                table(log, fmt),
                "## B1.2 Datenbestand vor und nach der Bereinigung",
                table(summary, fmt),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(log.to_string(index=False))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
