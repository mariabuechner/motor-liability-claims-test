"""Teil 3 – gemeinsame Bausteine: Train/Test-Aufteilung, Metrik und Negativ-Binomial-GLM.

Entscheidungen (siehe ENTSCHEIDUNGEN.md):
- Verteilungsannahme Frequenz: Negativ-Binomial (NB2, Var = μ + α μ²), Log-Link,
  log(Exposure) als Offset.
- Metrik: Poisson-Deviance auf den Testdaten.
- Aufteilung: nach Merkmalsprofil gruppiert, damit identische Profile nicht auf
  beiden Seiten landen.

Als Skript ausgeführt, erzeugt es die Aufteilung (data/processed/split.csv) und ein
Protokoll (reports/teil3/aufteilung.md):
    python src/teil3_grundlagen.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "reports" / "teil3"

PROFIL = ["VehPower", "VehAge", "DrivAge", "BonusMalus", "VehBrand", "VehGas", "Area", "Density", "Region"]
TEST_ANTEIL = 0.2
SEED = 20261002


# ---------------------------------------------------------------------------
# Aufteilung
# ---------------------------------------------------------------------------


def profil_id(freq):
    return freq.groupby(PROFIL, sort=False).ngroup()


def gruppen_aufteilung(gruppen, anteil, seed):
    """Zieht ganze Gruppen zufällig, bis ungefähr `anteil` der Zeilen erreicht ist."""
    rng = np.random.default_rng(seed)
    ids = np.unique(gruppen)
    gewaehlt = rng.random(len(ids)) < anteil
    return np.isin(gruppen, ids[gewaehlt])


def lade_mit_split():
    freq = pd.read_csv(PROCESSED / "freq_clean.csv")
    split = pd.read_csv(PROCESSED / "split.csv")
    freq = freq.merge(split, on="IDpol", how="left", validate="one_to_one")
    assert freq["Test"].notna().all()
    return freq


def cv_folds(gruppen, k, seed):
    """Fold-Nummer je Zeile; ganze Gruppen landen im selben Fold."""
    rng = np.random.default_rng(seed)
    ids = np.unique(gruppen)
    fold_der_gruppe = pd.Series(rng.integers(0, k, len(ids)), index=ids)
    return fold_der_gruppe.loc[gruppen].to_numpy()


# ---------------------------------------------------------------------------
# Metrik
# ---------------------------------------------------------------------------


def poisson_deviance(y, mu):
    """Mittlere Poisson-Deviance pro Police: 2/n Σ [y log(y/μ) − (y − μ)]."""
    y = np.asarray(y, float)
    mu = np.asarray(mu, float)
    term = np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / mu), 0.0)
    return 2 * np.mean(term - (y - mu))


def kalibrierung(y, mu, gruppe):
    df = pd.DataFrame({"Gruppe": gruppe, "beobachtet": y, "vorhergesagt": mu})
    t = df.groupby("Gruppe", observed=True)[["beobachtet", "vorhergesagt"]].sum()
    t["beobachtet/vorhergesagt"] = t["beobachtet"] / t["vorhergesagt"]
    return t


# ---------------------------------------------------------------------------
# Negativ-Binomial-GLM (NB2, Log-Link) mit Offset
# ---------------------------------------------------------------------------


def nb_loglik(y, mu, alpha):
    if alpha <= 0:
        return np.sum(y * np.log(mu) - mu - gammaln(y + 1))
    r = 1 / alpha
    return np.sum(gammaln(y + r) - gammaln(r) - gammaln(y + 1) + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))


def fit_nb_glm(X, y, offset, alpha, beta0=None, max_iter=100, tol=1e-10, cov=True):
    """IRLS für festes α. α = 0 ergibt das Poisson-GLM.

    Abbruch, wenn sich die Log-Likelihood relativ um weniger als `tol` ändert.
    """
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    offset = np.asarray(offset, float)
    beta = np.zeros(X.shape[1]) if beta0 is None else beta0.copy()
    if beta0 is None:
        beta[0] = np.log(y.sum() / np.exp(offset).sum())  # erste Spalte = Achsenabschnitt
    ridge = 1e-8 * np.eye(X.shape[1])
    ll_alt = -np.inf
    for _ in range(max_iter):
        eta = X @ beta + offset
        mu = np.exp(eta)
        w = mu / (1 + alpha * mu)
        z = eta - offset + (y - mu) / mu
        XtW = X.T * w
        beta = np.linalg.solve(XtW @ X + ridge, XtW @ z)
        ll = nb_loglik(y, np.exp(X @ beta + offset), alpha)
        if abs(ll - ll_alt) < tol * abs(ll):
            break
        ll_alt = ll
    if not cov:
        return beta, None
    mu = np.exp(X @ beta + offset)
    w = mu / (1 + alpha * mu)
    return beta, np.linalg.pinv((X.T * w) @ X)


def fit_nb(X, y, offset, alpha=None, cov=True):
    """Schätzt β und, wenn alpha=None, auch α per Profil-Likelihood."""
    if alpha is not None:
        beta, cov = fit_nb_glm(X, y, offset, alpha, cov=cov)
        return {"beta": beta, "cov": cov, "alpha": alpha}
    cache = {}

    def neg_ll(log_alpha):
        a = np.exp(log_alpha)
        beta, _ = fit_nb_glm(X, y, offset, a, beta0=cache.get("beta"), cov=False)
        cache["beta"] = beta
        return -nb_loglik(np.asarray(y, float), np.exp(np.asarray(X, float) @ beta + offset), a)

    res = minimize_scalar(neg_ll, bounds=(np.log(1e-4), np.log(20)), method="bounded", options={"xatol": 1e-3})
    alpha = float(np.exp(res.x))
    beta, cov = fit_nb_glm(X, y, offset, alpha, beta0=cache.get("beta"))
    return {"beta": beta, "cov": cov, "alpha": alpha}


def predict(model, X, offset):
    return np.exp(np.asarray(X, float) @ model["beta"] + np.asarray(offset, float))


# ---------------------------------------------------------------------------


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    freq = pd.read_csv(PROCESSED / "freq_clean.csv")
    gid = profil_id(freq)
    test = gruppen_aufteilung(gid.to_numpy(), TEST_ANTEIL, SEED)
    pd.DataFrame({"IDpol": freq["IDpol"], "Profil": gid, "Test": test}).to_csv(PROCESSED / "split.csv", index=False)

    t = (
        freq.assign(Teil=np.where(test, "Test", "Training"))
        .groupby("Teil")
        .agg(Policen=("ClaimNb", "size"), Exposure=("Exposure", "sum"), Schaeden=("ClaimNb", "sum"))
    )
    t["Frequenz"] = t["Schaeden"] / t["Exposure"]
    t["Anteil Policen"] = t["Policen"] / t["Policen"].sum()
    gemeinsam = len(set(gid[test]) & set(gid[~test]))
    lines = [
        "# Teil 3 – Aufteilung in Training und Test (automatisch erzeugt)",
        f"Erzeugt von `src/teil3_grundlagen.py`. Ganze Merkmalsprofile ({len(PROFIL)} Merkmale, siehe T1.5) werden "
        f"zufällig gezogen (Seed {SEED}), Ziel {TEST_ANTEIL:.0%} Test.",
        "## A3.1 Umfang je Teil",
        "| Teil | Policen | Exposure | Schäden | Frequenz | Anteil Policen |",
        "|---|---|---|---|---|---|",
        *[
            f"| {i} | {int(r.Policen):,} | {r.Exposure:,.1f} | {int(r.Schaeden):,} | {r.Frequenz:.4f} | {r['Anteil Policen']:.1%} |"
            for i, r in t.iterrows()
        ],
        f"Profile, die in beiden Teilen vorkommen: {gemeinsam}",
    ]
    (OUT / "aufteilung.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[3:]))


if __name__ == "__main__":
    main()
