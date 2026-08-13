# Daten

## Überblick

Grundlage sind **bioRxiv-Preprints**, deren Tabellen in strukturiertes Format (JSON/XML)
geparst wurden. Jede Datei entspricht einem Dokument und enthält den Volltext (`doi`, `title`,
Fließtext) sowie die geparsten Tabellen (Zellinhalte, Caption, Zeilen/Spalten).

- **Testset (Entwicklung):** 499 Dokumente, davon 386 Tabellen von Hand annotiert.
- **Echte Daten (finale Auswertung):** 3.810 Dokumente mit insgesamt 10.131 geparsten Tabellen.

Der **Volldatensatz** ist wegen seiner Größe nicht Teil dieses Repositories; er wurde von den
Dozierenden bereitgestellt.

> **Bezug des Volldatensatzes:** Der Volldatensatz (`team4_parsedTables.zip`) wurde von den
> Dozierenden über einen internen, zugangsbeschränkten Sciebo-Ordner bereitgestellt und ist
> nicht öffentlich verlinkbar; er ist daher nicht Teil dieses Repositories.
>
> Nach dem Erhalt entpacken nach `data/full/` (Ordner wird von `.gitignore` ausgeschlossen).
> Die Notebooks erwarten die JSON-Dateien standardmäßig in diesem Ordner – ggf. den
> `DATA_DIR`-Pfad im Notebook anpassen.

Ohne den Volldatensatz lässt sich die Annotationsauswertung direkt auf der mitgelieferten
Datei [`annotation/alle_annotiert.csv`](annotation/alle_annotiert.csv) nachvollziehen.

## Ground Truth: `annotation/alle_annotiert.csv`

386 von Hand annotierte Tabellen. Wichtige Spalten:

| Spalte | Bedeutung |
|---|---|
| `manual_label` | **Menschliche Ground Truth** (4 Kategorien) – dies ist das Zielsignal für das Modell |
| `category` | automatisch/heuristisch aus dem Overlap-Score abgeleitete Kategorie (zum Vergleich) |
| `overlap_ratio` | kontinuierlicher Overlap-Score der Tabelle (0–1) |
| `n_refs` | Anzahl der Textstellen, die auf die Tabelle verweisen |
| `n_table_nums` / `n_overlap` | Zahlen in der Tabelle bzw. davon im Text wiedergefunden |
| `caption`, `title`, `doi` | Metadaten zur Tabelle bzw. zum Dokument |

**Wichtig:** `manual_label` (händisch) und `category` (Heuristik) stimmen nur zu ~61 %
überein. Genau diese Lücke motiviert ein aufwändigeres Verfahren als eine einzelne Schwelle –
in der finalen Auswertung die größenabhängige, zweistufige Kaskade (Regex → spaCy).

### Die vier Kategorien

| Kategorie | Bedeutung | Beispiel |
|---|---|---|
| `info_in_text` | Tabellenzahlen werden im Text explizit wiederholt | „Die Genauigkeit lag bei 92,3 %." |
| `partial` | Tabelle wird qualitativ erwähnt, Zahlen aber nicht wiederholt | „…wie in Tabelle 2 gezeigt, steigt die Leistung deutlich." |
| `only_table` | Text verweist nur auf die Tabelle, ohne Inhalt | „Ergebnisse siehe Tabelle 1." |
| `no_refs` | Tabelle wird im Text gar nicht erwähnt | (kein Verweis vorhanden) |
