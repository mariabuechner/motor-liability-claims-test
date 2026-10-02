"""Erzeugt alle Ergebnisse aus den Rohdaten.

Aufruf:
    python run_pipeline.py
"""

import runpy
from pathlib import Path

SCHRITTE = [
    "src/teil1_datenuebersicht.py",
    "src/teil1_bereinigung.py",
    "src/teil2_visualisierung.py",
    "src/teil3_grundlagen.py",
    "src/teil3_merkmale.py",
]

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    for schritt in SCHRITTE:
        print(f"==> {schritt}")
        runpy.run_path(str(root / schritt), run_name="__main__")
