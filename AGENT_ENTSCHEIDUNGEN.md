# Entscheidungen des Agenten (Testlauf)

> **Hinweis:** Diese Datei gehört **nicht** zur Abgabe der Studierenden. Im Testlauf hat der
> Repo-Inhaber den Agenten ab Teil 3 gebeten, offene fachliche Entscheidungen selbst zu treffen.
> Sie sind hier getrennt von `ENTSCHEIDUNGEN.md` festgehalten, das laut `CLAUDE.md` von den
> Studierenden selbst formuliert wird. Alle Entscheidungen stützen sich ausschliesslich auf
> Analysen in diesem Repo, nicht auf publizierte Auswertungen dieses Datensatzes.

## Bis dahin von den Nutzenden getroffen (Zusammenfassung, Begründung gehört in ENTSCHEIDUNGEN.md)

| Nr. | Entscheidung | Beleg |
|---|---|---|
| 1 | Exposure > 1 entfernt | T1.3, B1.1 |
| 2 | Kurze Exposure behalten | T1.3 |
| 3 | Policen mit vielen Schäden inkl. Cluster behalten | T1.4 |
| 4 | VehAge ≥ 40 und DrivAge = 99 entfernt | T1.3, B1.1 |
| 5 | Junge Fahrer mit BonusMalus 50 behalten | P1.6 |
| 6 | Schadenhöhen unverändert | T1.7, P2.4 |
| 7 | Frequenz = Σ ClaimNb / Σ Exposure | T2.1 |
| 8 | Laufzeiteffekt: Entscheid anhand des Testergebnisses (Variante a vs. b) | T2.6, T2.7, F3.5 |
| 9 | Verteilungsannahme Negativ-Binomial | Streuung 1.79 / α ≈ 0.95 |
| 10 | Metrik Poisson-Deviance | – |
| 11 | Aufteilung nach Merkmalsprofil gruppiert, 80/20 | T1.5, A3.1 |
| 12 | GLM als erklärbares Modell | – |
| 13 | Region zusammenfassen; Density statt Area | M3.6–M3.8, T1.6 |
| 14 | Laufzeit in Variante b als Klassen | T2.2 |

## Agent-Entscheidungen

### A1: Auswahlregel für Modellvarianten
- **Beobachtung:** Viele Varianten unterscheiden sich in der Kreuzvalidierung nur minimal (M3.x, F3.x).
- **Optionen:** (1) immer die beste Variante, (2) einfachste Variante innerhalb von 1 Standardfehler der besten (1-SE-Regel), (3) Bauchgefühl.
- **Entscheidung:** 1-SE-Regel, Standardfehler gepaart über dieselben Folds.
- **Begründung:** Bewertet werden vor allem Nachvollziehbarkeit und Erklärbarkeit. Die Regel bevorzugt einfachere Modelle, solange der Datenbeleg für mehr Komplexität fehlt, und ist vorab festgelegt statt nachträglich gewählt.

### A2: Kodierung der stetigen Merkmale
- **Beobachtung:** M3.1–M3.5, P3.1.
- **Entscheidung:**
  - DrivAge: natürlicher Spline, 8 Freiheitsgrade (klar beste Variante; nur so wird der steile Anstieg bei jungen Fahrern abgebildet).
  - BonusMalus: Spline, 8 Freiheitsgrade, plus Zusatzbaustein nach A5.
  - VehAge: Spline, 4 Freiheitsgrade (beste Variante; 10 Klassen rund 3 SE schlechter).
  - Density: log(x) (gleich gut wie Klassen und Spline, aber nur 1 Parameter und monoton).
- **Begründung:** Wo die Kreuzvalidierung klar unterscheidet, gewinnt die bessere Variante. Wo nicht (Density), gewinnt die einfachste.

### A3: Kappung an den Rändern
- **Beobachtung:** P3.1: Splines und lineare Terme liefern an dünn besetzten Rändern unplausible Faktoren (z. B. BonusMalus linear Faktor 60 bei 230).
- **Optionen:** keine Kappung, Kappung bei 99.9 % oder 99.5 % der Exposure.
- **Entscheidung:** Kappung von DrivAge, BonusMalus und VehAge beim 99.5 %-Exposure-Quantil des Trainings (Werte in F3.1).
- **Begründung:** Dahinter stehen jeweils nur rund 0.5 % der Exposure. Der Tarif soll am Rand stabil und erklärbar bleiben. Die Kappung betrifft die Güte praktisch nicht.

### A4: VehPower und Regionsgruppierung
- **Beobachtung:** F3.2, F3.3.
- **Entscheidung:** nach 1-SE-Regel im vollen GLM (Ergebnis siehe F3.2/F3.3). Neu geprüft wurde eine Regionsgruppierung nach dem Effekt *zusätzlich zu Density*, weil die rohe Regionsfrequenz Density-Unterschiede mitenthält (M3.6 vs. M3.7).
- **Begründung:** VehPower ist einzeln schwach (M3.4), im vollen Modell aber messbar. Die Gruppierung nach dem bereinigten Effekt ist inhaltlich sauberer und erfüllt die Vorgabe der Nutzenden, Regionen zusammenzufassen.

### A5: Zusatzbaustein BonusMalus
- **Beobachtung:** Häufige BonusMalus-Werte haben eine tiefere Frequenz als die seltenen Werte dazwischen (P2.2). Ein Gradient Boosting ohne Wechselwirkungen war deutlich besser als das GLM. Eine Diagnose ergab, dass fast der ganze Unterschied von diesem Muster kommt.
- **Optionen:** nur Spline; Indikator „seltener Wert“; häufige Werte je eigene Kategorie, Rest „selten“; jeder Wert eigene Kategorie (F3.3b).
- **Entscheidung:** nach 1-SE-Regel (F3.3b).
- **Begründung:** Grösste Verbesserung im ganzen GLM. Die Ursache des Musters ist aus den Daten nicht ableitbar. Das muss in der Präsentation als Limitation genannt werden.

### A6: Flexibles Vergleichsmodell
- **Optionen:** Gradient Boosting, Random Forest, neuronales Netz.
- **Entscheidung:** Gradient Boosting (`HistGradientBoostingRegressor`, Poisson-Verlust, Exposure als Gewicht). Baumtiefe und Anzahl Iterationen werden per gruppierter Kreuzvalidierung gewählt (F3.4).
- **Begründung:** Der Poisson-Verlust ist konsistent mit der Metrik. Das Modell ist in scikit-learn verfügbar, kein neues Paket nötig, und findet Verläufe und Wechselwirkungen selbst. Ein Negativ-Binomial-Verlust ist dort nicht verfügbar. Für den *Erwartungswert*, der für die Prämie zählt, ist das unerheblich.

### A7: Variante a oder b (Laufzeit)
- **Beobachtung:** F3.5, F3.6.
- **Entscheidung:** Variante b, mit Laufzeitklassen. Prämie für 1 Jahr = Referenzklasse.
- **Begründung:** siehe Ergebnis in F3.5/F3.6: bessere Test-Deviance. Vor allem ist b für volle Jahre kalibriert, während a die Frequenz eines Jahresvertrags deutlich überschätzt.

### A8: Erklärbares Modell für den Tarif
- **Entscheidung:** GLM b ist das Tarifmodell. Das Gradient Boosting dient als Benchmark.
- **Begründung:** Die Bewertung gewichtet Erklärbarkeit höher als Modellgüte. Das GLM liefert pro Merkmal einen multiplikativen Faktor, den das Dashboard direkt als Preisbegründung zeigen kann. Der verbleibende Vorsprung des Gradient Boosting stammt aus Wechselwirkungen und ist als Limitation zu dokumentieren.
