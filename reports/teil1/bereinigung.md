# Teil 1 – Bereinigungsprotokoll (automatisch erzeugt)

Erzeugt von `src/teil1_bereinigung.py`. Regeln werden der Reihe nach angewendet; „davon neu entfernt“ zählt nur Policen, die nicht schon eine frühere Regel entfernt hat. Mit einer Police werden auch ihre Schadenbeträge aus sev entfernt.

## B1.1 Entfernte Policen je Regel

| Regel | Zeilen (für sich) | davon neu entfernt | Exposure entfernt | Schäden entfernt |
|---|---|---|---|---|
| Exposure > 1 Jahr | 1,224 | 1,224 | 1,363.3 | 54 |
| VehAge ≥ 99 (Platzhalter) | 48 | 48 | 27.9 | 1 |
| VehAge zwischen 40 und 98 | 198 | 198 | 136.1 | 2 |
| DrivAge = 99 (Platzhalter) | 70 | 70 | 49.4 | 4 |

## B1.2 Datenbestand vor und nach der Bereinigung

|  | roh | bereinigt | Veränderung |
|---|---|---|---|
| Policen | 677,991 | 676,451 | -0.23% |
| Exposure (Jahre) | 358,482.8 | 356,906.1 | -0.44% |
| Schäden (ClaimNb) | 26,444 | 26,383 | -0.23% |
| Zeilen sev | 26,444 | 26,383 | -0.23% |
| Schadensumme | 59,909,216.5 | 59,812,483.9 | -0.16% |
