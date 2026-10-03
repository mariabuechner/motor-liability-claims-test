# Teil 3 – Frequenzmodelle (automatisch erzeugt)

Erzeugt von `src/teil3_frequenz.py`. Auswahl nur per Kreuzvalidierung auf dem Training (5 Folds nach Profil); Testdaten nur in F3.5–F3.6.

## F3.1 Kappung (99.5 %-Exposure-Quantil im Training)

| Merkmal | obere Grenze |
|---|---|
| DrivAge | 84 |
| BonusMalus | 118 |
| VehAge | 25 |

## F3.2 Auswahl VehPower (volles GLM, Region 22 einzeln)

1-SE-Regel: gewählt wird die Variante mit den wenigsten Parametern, deren Abstand zur besten höchstens ihrem Standardfehler entspricht.

| Variante | Parameter | CV-Deviance | Abstand zur besten | ± SE Abstand | gewählt |
|---|---|---|---|---|---|
| ohne VehPower | 54 | 0.242408 | 0.000127 | 0.000045 |  |
| VehPower linear | 55 | 0.242281 | 0.000000 | 0.000000 | ✔ |
| VehPower je Wert | 65 | 0.242291 | 0.000010 | 0.000030 |  |

## F3.3 Auswahl Regionsgruppierung (volles GLM)

| Variante | Parameter | CV-Deviance | Abstand zur besten | ± SE Abstand | gewählt |
|---|---|---|---|---|---|
| 22 einzeln | 55 | 0.242281 | 0.000000 | 0.000000 |  |
| Regionen < 1 % zusammen | 48 | 0.242314 | 0.000033 | 0.000009 |  |
| 8 Gruppen nach roher Frequenz | 41 | 0.242321 | 0.000040 | 0.000026 |  |
| 4 Gruppen nach Effekt zusätzlich zu Density | 37 | 0.242364 | 0.000083 | 0.000040 |  |
| 6 Gruppen nach Effekt zusätzlich zu Density | 39 | 0.242313 | 0.000032 | 0.000024 |  |
| 8 Gruppen nach Effekt zusätzlich zu Density | 41 | 0.242290 | 0.000009 | 0.000017 | ✔ |

Zuordnung der gewählten Gruppierung (Training):

| Gruppe | Region |
|---|---|
| Gruppe 1 | Auvergne, Basse-Normandie, Haute-Normandie, Ile-de-France, Lorraine, Midi-Pyrenees |
| Gruppe 2 | Bretagne, Champagne-Ardenne |
| Gruppe 3 | Pays-de-la-Loire |
| Gruppe 4 | Centre |
| Gruppe 5 | Alsace, Aquitaine |
| Gruppe 6 | Bourgogne, Languedoc-Roussillon, Provence-Alpes-Cotes-D'Azur |
| Gruppe 7 | Corse, Franche-Comte, Nord-Pas-de-Calais, Poitou-Charentes |
| Gruppe 8 | Limousin, Picardie, Rhone-Alpes |

## F3.4 Gradient Boosting: Tuning

Lernrate 0.05, Poisson-Verlust, Iterationen per Kreuzvalidierung gewählt.

### Variante a

| max_leaf_nodes | min_samples_leaf | Iterationen | CV-Deviance |
|---|---|---|---|
| 7 | 500 | 749 | 0.239128 |
| 15 | 500 | 345 | 0.239093 |
| 31 | 500 | 96 | 0.238992 |

### Variante b (Exposure als Merkmal)

| max_leaf_nodes | min_samples_leaf | Iterationen | CV-Deviance |
|---|---|---|---|
| 7 | 500 | 943 | 0.234708 |
| 15 | 500 | 382 | 0.234817 |
| 31 | 500 | 157 | 0.234824 |

## F3.5 Vergleich auf den Testdaten

Deviance = mittlere Poisson-Deviance pro Police (kleiner ist besser). „nur volle Jahre“ = Testpolicen mit Exposure ≥ 0.99; das ist die Laufzeit, für die der Tarif gerechnet wird.

| Modell | Deviance Test | Deviance Test, nur volle Jahre | beobachtet/vorhergesagt | beob./vorh., nur volle Jahre | Verbesserung ggü. Nullmodell |
|---|---|---|---|---|---|
| Portfoliofrequenz (Nullmodell) | 0.246761 | 0.333447 | 0.979 | 0.750 | 0.000000 |
| GLM a (ohne Laufzeit) | 0.234052 | 0.305705 | 0.976 | 0.839 | 0.012709 |
| GLM b (mit Laufzeitklassen) | 0.232698 | 0.305270 | 0.979 | 1.025 | 0.014063 |
| GBM a (ohne Laufzeit) | 0.230897 | 0.297126 | 0.980 | 0.849 | 0.015864 |
| GBM b (mit Exposure) | 0.227433 | 0.291856 | 0.982 | 1.019 | 0.019328 |

## F3.6 Kalibrierung auf den Testdaten je Laufzeitklasse (beobachtet / vorhergesagt)

| Exposure-Klasse | GLM a (ohne Laufzeit) | GLM b (mit Laufzeitklassen) | GBM a (ohne Laufzeit) | GBM b (mit Exposure) |
|---|---|---|---|---|
| (0.0, 0.05] | 2.688 | 0.689 | 2.670 | 0.720 |
| (0.05, 0.1] | 1.280 | 0.756 | 1.314 | 0.784 |
| (0.1, 0.25] | 1.466 | 1.027 | 1.469 | 1.019 |
| (0.25, 0.5] | 1.098 | 0.967 | 1.100 | 0.977 |
| (0.5, 0.75] | 0.973 | 0.947 | 0.972 | 0.954 |
| (0.75, 0.99] | 0.959 | 0.992 | 0.952 | 0.997 |
| (0.99, 1.0] | 0.836 | 1.024 | 0.846 | 1.015 |

## F3.7 GLM b: Faktoren der kategorialen Merkmale (exp(β), 95 %-KI)

| Merkmal | Ausprägung | Faktor | KI unten | KI oben |
|---|---|---|---|---|
| VehBrand | B1 (Referenz) | 1.000 | nan | nan |
| VehBrand | B2 | 0.998 | 0.960 | 1.038 |
| VehBrand | B12 | 0.689 | 0.655 | 0.725 |
| VehBrand | B3 | 1.041 | 0.986 | 1.098 |
| VehBrand | B5 | 1.064 | 0.999 | 1.132 |
| VehBrand | B6 | 1.009 | 0.941 | 1.082 |
| VehBrand | B4 | 1.012 | 0.941 | 1.089 |
| VehBrand | B10 | 0.964 | 0.880 | 1.055 |
| VehBrand | B11 | 1.174 | 1.068 | 1.289 |
| VehBrand | B13 | 1.015 | 0.917 | 1.124 |
| VehBrand | B14 | 0.858 | 0.707 | 1.040 |
| VehGas | Regular (Referenz) | 1.000 | nan | nan |
| VehGas | Diesel | 1.136 | 1.104 | 1.170 |
| Region | Gruppe 4 (Referenz) | 1.000 | nan | nan |
| Region | Gruppe 1 | 0.880 | 0.837 | 0.926 |
| Region | Gruppe 6 | 1.009 | 0.963 | 1.058 |
| Region | Gruppe 8 | 1.184 | 1.131 | 1.239 |
| Region | Gruppe 2 | 1.011 | 0.954 | 1.072 |
| Region | Gruppe 7 | 1.022 | 0.963 | 1.084 |
| Region | Gruppe 3 | 0.977 | 0.915 | 1.042 |
| Region | Gruppe 5 | 1.001 | 0.930 | 1.077 |
| ExpKlasse | (0.99, 1.0] (Referenz) | 1.000 | nan | nan |
| ExpKlasse | (0.5, 0.75] | 1.385 | 1.326 | 1.446 |
| ExpKlasse | (0.75, 0.99] | 1.282 | 1.226 | 1.340 |
| ExpKlasse | (0.25, 0.5] | 1.538 | 1.475 | 1.605 |
| ExpKlasse | (0.1, 0.25] | 1.935 | 1.830 | 2.046 |
| ExpKlasse | (0.05, 0.1] | 2.300 | 2.128 | 2.487 |
| ExpKlasse | (0.0, 0.05] | 5.457 | 4.890 | 6.091 |

## F3.8 GLM b: Verläufe der stetigen Merkmale

![glm_b_stetig.png](glm_b_stetig.png)

## F3.9 GLM a: Faktoren der kategorialen Merkmale

| Merkmal | Ausprägung | Faktor | KI unten | KI oben |
|---|---|---|---|---|
| VehBrand | B1 (Referenz) | 1.000 | nan | nan |
| VehBrand | B2 | 0.995 | 0.957 | 1.034 |
| VehBrand | B12 | 0.768 | 0.730 | 0.807 |
| VehBrand | B3 | 1.048 | 0.993 | 1.106 |
| VehBrand | B5 | 1.063 | 0.999 | 1.131 |
| VehBrand | B6 | 1.020 | 0.951 | 1.094 |
| VehBrand | B4 | 1.014 | 0.942 | 1.092 |
| VehBrand | B10 | 0.983 | 0.898 | 1.076 |
| VehBrand | B11 | 1.206 | 1.098 | 1.325 |
| VehBrand | B13 | 1.029 | 0.929 | 1.140 |
| VehBrand | B14 | 0.865 | 0.713 | 1.050 |
| VehGas | Regular (Referenz) | 1.000 | nan | nan |
| VehGas | Diesel | 1.161 | 1.127 | 1.195 |
| Region | Gruppe 4 (Referenz) | 1.000 | nan | nan |
| Region | Gruppe 1 | 0.921 | 0.876 | 0.969 |
| Region | Gruppe 6 | 1.097 | 1.047 | 1.149 |
| Region | Gruppe 8 | 1.214 | 1.159 | 1.270 |
| Region | Gruppe 2 | 0.994 | 0.937 | 1.054 |
| Region | Gruppe 7 | 1.073 | 1.011 | 1.138 |
| Region | Gruppe 3 | 0.987 | 0.925 | 1.054 |
| Region | Gruppe 5 | 1.066 | 0.990 | 1.147 |

![glm_a_stetig.png](glm_a_stetig.png)
