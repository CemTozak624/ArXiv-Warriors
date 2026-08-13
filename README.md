# Tabellen vs. Fließtext in bioRxiv-Preprints

**Gruppe „ArXiv Warriors" · Modul DIS22 – Projekt 2 (Data and Information Science) · TH Köln**
Cem İlhan · Mogens Rosiny · Robin Klinkhammer

---

## Worum geht es?

Leser wissenschaftlicher Arbeiten springen oft nur in die Tabellen und Abbildungen, ziehen
daraus die Kernbotschaft und verlassen das Paper wieder, ohne den Fließtext zu lesen. Das
wirft eine Frage auf: **Funktioniert das überhaupt – sind Tabellen eigenständig genug, um
allein verstanden zu werden? Oder sind sie umgekehrt redundant, weil der Text ihren Inhalt
ohnehin wiederholt?**

### Forschungsfrage

> In welchem Ausmaß überschneiden sich die Informationen in Tabellen mit dem umliegenden
> Fließtext in bioRxiv-Preprints?

## Overlap-Score und Klassifizierung

- Der **Overlap-Score** ist die eigentliche Messung: ein kontinuierlicher Wert (0 =
  eigenständig, 1 = Text wiederholt alles) pro Tabelle.
- Die **Klassifizierung in vier Kategorien** (`info_in_text`, `partial`, `only_table`,
  `no_refs`) übersetzt den Score in eine anschauliche Aussage und diente in der Entwicklung
  als Kontrolle, ob das automatische Verfahren so einordnet wie ein Mensch.

## Zwei Projektphasen

1. **Entwicklung** auf einem Testset (499 Dokumente, davon **386 handannotierte Tabellen** als
   Ground Truth). Hier wurden die drei Mess-Methoden erprobt und mehrere Klassifikationsansätze
   getestet – bis hin zu einem Random Forest (Cohen's κ = 0,426 in ehrlicher Kreuzvalidierung).
   Ergebnis der Phase: 386 Beispiele sind zu wenig für ein stabiles Modell, und ML verführte
   wiederholt zu Overfitting.
2. **Finale Auswertung** auf den echten Daten (**3.810 Dokumente, 10.131 Tabellen**). Die
   finale Methode ist bewusst **kein Machine-Learning-Modell**, sondern eine transparente,
   **regelbasierte Kaskade (Regex → spaCy)** mit größenabhängigen Schwellenwerten. Das LLM und
   der Random Forest wurden verworfen; bewertet wird über die Konsistenz der
   Kategorienverteilung zwischen Trainings- und Testteil auf **Dokument-Ebene** (< 2 pp
   Abweichung je Klasse).

Die drei Mess-Methoden (steigende Komplexität):

- **Regex** (Baseline): Zahlenabgleich zwischen Tabelle und Textfenster.
- **spaCy** (NER + Dependency Parsing): Zahlen im Satzkontext, Jahreszahlen gefiltert.
- **LLM** (Llama 3.2 via Ollama): semantische Umschreibungen – **verworfen** (~72 % der Scores
  kollabierten auf 0,8 → Halluzination; auf den echten Daten nur Timeouts).

## Wichtigste Ergebnisse (finale Auswertung, 10.131 Tabellen)

| Kategorie | Anteil |
|---|---|
| `only_table` (nur Verweis, kein Inhalt) | 37,7 % |
| `info_in_text` (Zahlen im Text wiederholt) | 31,3 % |
| `no_refs` (gar nicht erwähnt) | 15,8 % |
| `partial` (qualitativ erwähnt) | 15,2 % |

**Rund 53 %** der Tabellen (`only_table` + `no_refs`) werden im Text inhaltlich nicht
wiedergegeben, **31 %** vollständig gespiegelt. Tabellen sind damit überwiegend eigenständige
Informationsträger. Regex und spaCy liefern nahezu identische mittlere Overlap-Scores
(≈ 0,16 bzw. ≈ 0,15), was für die Robustheit der Messung spricht.

> **Vollständige Ergebnisse, Abbildungen und Interpretation** finden sich im **Projektbericht**
> und in der **Abschlusspräsentation** (separat abgegeben, nicht Teil dieses Repos). Dieses
> Repository enthält bewusst nur den **Code** zur Reproduktion – die obige Tabelle ist eine
> Kurzfassung der Kernergebnisse.

## Repo-Struktur

Der Code ist bewusst in **zwei Ordner** getrennt, damit die finale Abgabe sofort erkennbar ist:

```
ArXiv-Warriors/
├── final/                              # ← DIE ABGABE: nur die finale Pipeline
│   └── 05_pipeline_final_kaskade.ipynb #   Regelbasierte Kaskade (Regex → spaCy), LLM aus
│
├── archive/                           # ← Entwicklungsweg in Reihenfolge (alle Vorversionen)
│   ├── 00_erstercode_prototyp.ipynb   #   1. Erster Versuch / Prototyp (Forschungsfrage)
│   ├── 01_regex.ipynb                 #   2. Methode A – Regex-Overlap (Baseline)
│   ├── 02_spacy.ipynb                 #   3. Methode B – spaCy NER + Dependency
│   ├── 03_llm_ollama.ipynb            #   4. Methode C – LLM via Ollama (verworfen)
│   ├── 04_visualisierung.ipynb        #   5. Methodenvergleich & Verteilungen
│   ├── improved_pipeline.ipynb        #   6. Integrierte Pipeline v1 (Kaskade + Cohen's κ)
│   ├── optimized_pipeline.ipynb       #   7. Pipeline v2 mit Random Forest (verworfen)
│   └── pipeline.py                     #   Skript-Version von improved_pipeline
│
├── data/
│   ├── annotation/alle_annotiert.csv  # 386 handannotierte Tabellen (Ground Truth)
│   └── README.md                      # Datenbeschreibung + Bezug des Volldatensatzes
├── requirements.txt
└── README.md
```

Chronologie der Entwicklung: **erster Versuch (nummerierte Notebooks) → Annotation
(`data/annotation/`) → `improved_pipeline` → `optimized_pipeline` (Random Forest) → finale
Kaskade in `final/`.**

> **Hinweis zum Umfang:** Dieses Repo ist bewusst schlank und auf den **Code** fokussiert.
> Ausführliche Ergebnisse, Grafiken und die Interpretation liegen im **Projektbericht** und in
> der **Abschlusspräsentation** (separat abgegeben). Wer die Ergebnisse ansehen möchte, schaut
> dort – GitHub dient hier primär der Nachvollziehbarkeit des Codes.

> **Wichtig – finale Version:** `final/05_pipeline_final_kaskade.ipynb` ist die tatsächlich
> abgegebene Pipeline (regelbasierte Kaskade, **ohne** Random Forest, LLM deaktiviert). Alles
> unter `archive/` dokumentiert nur den Entwicklungsweg (erste Versuche, ML-Ansätze) – **nicht**
> die finale Auswertung.

## Installation & Ausführung

```bash
# 1. Repository klonen
git clone https://github.com/CemTozak624/ArXiv-Warriors.git
cd ArXiv-Warriors

# 2. Abhängigkeiten installieren (virtuelle Umgebung empfohlen)
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. spaCy-Sprachmodell laden
python -m spacy download en_core_web_sm

# 4. Finale Auswertung reproduzieren:  final/05_pipeline_final_kaskade.ipynb ausführen
#    Entwicklungsweg nachvollziehen:   Notebooks in archive/ (00 -> optimized)
jupyter lab
```

Der Volldatensatz ist nicht Teil des Repos (Größe); er wurde von den Dozierenden über einen
internen, zugangsbeschränkten Sciebo-Ordner bereitgestellt – siehe
[`data/README.md`](data/README.md) für den Bezugsweg. Als reproduzierbare Datengrundlage
liegen im Repo die 386 handannotierten Tabellen unter
[`data/annotation/alle_annotiert.csv`](data/annotation/alle_annotiert.csv).

## Limitationen

- **Kein Inter-Annotator-Agreement:** Die 386 Tabellen wurden im Team aufgeteilt und jeweils
  von einer Person annotiert, nicht überlappend – die Übereinstimmung zwischen den Annotatoren
  (natürliche Obergrenze für die Modellgüte) bleibt offen.
- **Keine vollständige Ground Truth auf den echten Daten:** Die finale Kaskade wird über
  Train/Test-Konsistenz belegt, nicht über eine direkte Übereinstimmung mit menschlichen
  Urteilen auf allen 10.131 Tabellen.
- **Verschiebung `info_in_text`:** Der finale Anteil (31,3 %) liegt über der handannotierten
  Stichprobe (12,4 %); die größenabhängigen Schwellen stufen große Tabellen tendenziell
  großzügig ein. Die Anteile sind als Größenordnung zu lesen.
- **Seltene Klasse `no_refs`** ist in der Stichprobe mit nur 3 Beispielen kaum belegt.

## Autoren & Beitrag

Hauptverantwortung je Bereich (H); die vollständige Beitragsmatrix mit Haupt- und
Mitarbeit steht im Projektbericht (Kap. 6).

| Teammitglied | Hauptverantwortung |
|---|---|
| Cem İlhan Tozak | Einleitung, Motivation & Related Work · Mess-Methoden (Regex, spaCy, LLM) · Bericht-Redaktion & Code-Repository |
| Mogens Rosiny | Datengrundlage & Datenaufbereitung · finale Kaskade & Evaluation · Visualisierung & Methodenvergleich |
| Robin Klinkhammer | Manuelle Annotation (Ground Truth) · finale Kaskade & Evaluation · Diskussion, Fazit & Limitationen |

## Lizenz

MIT – siehe [LICENSE](LICENSE).
