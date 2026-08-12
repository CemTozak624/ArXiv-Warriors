"""
improved_pipeline.py – Verbesserte Kaskaden-Pipeline für DIS22
Kaskade: Regex → spaCy → Ollama-LLM
Evaluation gegen manuelle Annotation (Cohen's Kappa)

Verwendung:
    python improved_pipeline.py

Voraussetzungen:
    pip install spacy scikit-learn pandas tqdm ollama
    python -m spacy download en_core_web_sm
    # Ollama: https://ollama.com  → ollama pull llama3.3  (oder anderes Modell)

Eingaben:
    ../SampleData/output/   → 499 Paper-JSONs
    ../annotation/alle_annotiert.csv  → Ground Truth (Spalten: idx, manual)

Ausgabe:
    ../results_improved.csv
"""

import json
import re
import pathlib
import sys
import pandas as pd
from tqdm.auto import tqdm

# ---------------------------------------------------------------------------
# Pfade
# ---------------------------------------------------------------------------
SCRIPT_DIR   = pathlib.Path(__file__).resolve().parent
PROJECT_DIR  = SCRIPT_DIR.parent
OUTPUT_DIR   = PROJECT_DIR / "SampleData" / "output"
ANNOT_PATH   = PROJECT_DIR / "annotation" / "alle_annotiert.csv"
RESULTS_PATH = PROJECT_DIR / "results_improved.csv"

WINDOW_FORWARD = 500   # nur vorwärts ab Referenzposition (nicht ±)

# ---------------------------------------------------------------------------
# spaCy laden (optional – Stufe 2 der Kaskade)
# ---------------------------------------------------------------------------
try:
    import spacy
    try:
        _nlp = spacy.load("en_core_web_md")
        print("spaCy-Modell: en_core_web_md")
    except OSError:
        _nlp = spacy.load("en_core_web_sm")
        print("spaCy-Modell: en_core_web_sm")
    SPACY_OK = True
except Exception as e:
    print(f"spaCy nicht verfügbar ({e}) – Stufe 2 übersprungen")
    _nlp = None
    SPACY_OK = False

# ---------------------------------------------------------------------------
# Ollama laden (optional – Stufe 3 der Kaskade)
# Bevorzugte Modelle: größte zuerst, Fallback auf was verfügbar ist.
# Empfehlung: llama3.3 (70B), qwen2.5:72b, deepseek-r1:32b, llama3.1:8b
# ---------------------------------------------------------------------------
_PREFERRED_MODELS = [
    "llama3.3",        # Meta Llama 3.3 70B – beste freie Option
    "qwen2.5:72b",     # Qwen 2.5 72B – sehr stark für Klassifikation
    "deepseek-r1:32b", # DeepSeek R1 32B – gutes Reasoning
    "llama3.1:70b",    # Llama 3.1 70B
    "llama3.1:8b",     # kleineres Fallback
    "llama3.2",        # noch kleineres Fallback
    "mistral",
]
_ollama_model: str | None = None
OLLAMA_OK = False

try:
    import ollama as _ollama_lib
    _model_list = _ollama_lib.list()
    # API ≥0.4 gibt Pydantic-Objekt zurück
    _available = (
        [m.model for m in _model_list.models]
        if hasattr(_model_list, "models")
        else [m["name"] for m in _model_list.get("models", [])]
    )
    if _available:
        # Bevorzugtes Modell wählen
        for pref in _PREFERRED_MODELS:
            match = next((a for a in _available if a.startswith(pref)), None)
            if match:
                _ollama_model = match
                break
        if not _ollama_model:
            _ollama_model = _available[0]
        OLLAMA_OK = True
        print(f"Ollama verfügbar. Modell: {_ollama_model}")
    else:
        print("Ollama verfügbar aber keine Modelle installiert.")
        print("  → ollama pull llama3.3  (empfohlen)")
except Exception as e:
    print(f"Ollama nicht verfügbar ({type(e).__name__}) – Stufe 3 übersprungen")


# ===========================================================================
# 1. TABELLEN-PARSING
# ===========================================================================

def extract_table_content(table: dict) -> tuple[str, bool]:
    """
    Gibt (all_cells_text, is_complete) zurück.
    is_complete=False wenn nur Headers / keine echten Datenzellen vorhanden.

    Unterstützt zwei Formate:
      - pandas-orient: {"columns": [...], "data": [[...], ...]}
      - briefing-format: {"headers": [...], "data": [[...], ...]}
    """
    content_raw = table.get("content") or "{}"
    try:
        content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
    except (json.JSONDecodeError, TypeError):
        return "", False

    # Header-Zeile ermitteln
    headers = content.get("headers") or content.get("columns") or []

    # Datenzellen ermitteln
    data_rows = content.get("data", [])

    # Vollständigkeitsprüfung: gibt es nicht-leere Datenzellen?
    has_data = len(data_rows) > 0 and any(
        any(str(cell).strip() for cell in row)
        for row in data_rows
    )

    if not has_data:
        # Nur Headers – Parsing unvollständig
        return " ".join(str(h) for h in headers), False

    all_cells = [str(h) for h in headers]
    for row in data_rows:
        all_cells.extend(str(cell) for cell in row)

    return " ".join(all_cells), True


# ===========================================================================
# 2. ZAHLENNORMALISIERUNG & FUZZY-MATCHING
# ===========================================================================

def normalize_number(s: str) -> str:
    """
    '34.7%' → '34.7'
    '34,7'  → '34.7'
    '1,234.5' → '1234.5'
    '≈35'   → '35'
    """
    s = str(s).strip()
    s = re.sub(r"[%±≈~<>≤≥°]", "", s)
    # Tausender-Trennzeichen: 1,234 → 1234
    s = re.sub(r"(\d),(\d{3})", r"\1\2", s)
    # Komma als Dezimaltrenner: 34,7 → 34.7
    s = re.sub(r"(\d),(\d{1,2})$", r"\1.\2", s)
    return s.strip()


def extract_numbers_regex(text: str) -> set[str]:
    """
    Extrahiert und normalisiert alle Zahlen aus Text (Regex-basiert).
    Filtert: Jahreszahlen (2000–2030), kleine Zahlen (≤2), sehr große (>100000).
    """
    if not text:
        return set()
    # Zahlen mit möglichen Kommas/Punkten/Prozent
    raw = re.findall(r"[\d]+(?:[.,]\d+)*(?:\s*%)?", text)
    numbers: set[str] = set()
    for n in raw:
        n_clean = normalize_number(n)
        try:
            val = float(n_clean)
        except ValueError:
            continue
        if 2000 <= val <= 2030:
            continue  # Jahreszahl
        # Nur ganzzahlige 0/1/2 filtern – kleine Dezimalzahlen (0.33, 0.41 etc.)
        # sind wichtige Scores/p-Werte und NICHT filtern!
        if val in (0.0, 1.0, 2.0) and float(n_clean) == int(float(n_clean)):
            continue
        if val > 100_000:
            continue  # zu groß ohne Einheit
        numbers.add(n_clean)
    return numbers


def extract_numbers_spacy(text: str) -> set[str]:
    """
    Extrahiert Zahlen via spaCy CARDINAL-Entities.
    Präziser als Regex – filtert Section-Nummern etc. raus.
    """
    if not text or not SPACY_OK:
        return set()
    doc = _nlp(text[:20_000])
    numbers: set[str] = set()
    for ent in doc.ents:
        if ent.label_ in ("CARDINAL", "PERCENT", "QUANTITY"):
            n = normalize_number(ent.text)
            try:
                val = float(n)
            except ValueError:
                continue
            if 2000 <= val <= 2030:
                continue
            if val in (0.0, 1.0, 2.0) and val == int(val):
                continue
            numbers.add(n)
    return numbers


def fuzzy_match(table_nums: set[str], text_nums: set[str], tolerance: float = 0.05) -> int:
    """
    Prüft für jede Tabellenzahl ob eine ähnliche Zahl (±5%) im Text vorkommt.
    Gibt Anzahl gematchter Tabellenzahlen zurück.
    """
    matched = 0
    for tn in table_nums:
        try:
            tv = float(tn)
        except ValueError:
            continue
        for xn in text_nums:
            try:
                xv = float(xn)
                if tv == 0:
                    if xv == 0:
                        matched += 1
                        break
                elif abs(tv - xv) / abs(tv) <= tolerance:
                    matched += 1
                    break
            except ValueError:
                continue
    return matched


# ===========================================================================
# 3. TEXTFENSTER: nur vorwärts (+500 Zeichen ab Referenzposition)
# ===========================================================================

def get_window_forward(full_text: str, reference: str, size: int = WINDOW_FORWARD) -> str:
    """
    Gibt Textfenster zurück: ab Referenzposition vorwärts (+size Zeichen).
    Kein Rückwärtsfenster – Begründung: Werte stehen nach der Referenz.
    """
    ref_pos = full_text.find(reference)
    if ref_pos >= 0:
        return full_text[ref_pos: ref_pos + size]
    # Fallback: ersten 60 Zeichen suchen
    short = reference[:60].strip()
    pos = full_text.find(short)
    if pos >= 0:
        return full_text[pos: pos + size]
    return reference  # Fallback: nur den Referenz-Satz selbst


# ===========================================================================
# 4. STUFE 1 – REGEX-KLASSIFIKATOR
# ===========================================================================

def classify_regex(table: dict, full_text: str) -> tuple[str, str]:
    """
    Stufe 1: Regex-basierte Klassifikation.
    Gibt (label, confidence) zurück.
    confidence='high' → Kaskade stoppt.
    confidence='low'  → weiter zu Stufe 2.
    """
    refs = table.get("references") or []

    # --- Stufe 0: no_refs ---
    if not refs:
        return "no_refs", "high"

    # Textfenster vorwärts zusammenbauen
    window_parts = [get_window_forward(full_text, ref) for ref in refs]
    window_combined = " ".join(window_parts)

    # Referenztext-Metriken
    all_refs_text = " ".join(refs)
    ref_word_count = len(all_refs_text.split())

    # Tabelleninhalt
    table_text, is_complete = extract_table_content(table)

    # Zahlen extrahieren + Overlap
    table_nums = extract_numbers_regex(table_text)
    window_nums = extract_numbers_regex(window_combined)

    if table_nums:
        matched = fuzzy_match(table_nums, window_nums)
        overlap_score = matched / len(table_nums)
    else:
        overlap_score = 0.0

    # -----------------------------------------------------------------------
    # Entscheidungsbaum
    # -----------------------------------------------------------------------

    # 1. Sehr kurze Referenz + kein Overlap → reiner Zeigefinger → only_table
    if ref_word_count < 15 and overlap_score < 0.1:
        return "only_table", "high"

    # 2. Tabelle unvollständig geparst + kurze Refs → unsicher
    if not is_complete and ref_word_count < 25:
        return "only_table", "low"

    # 3. Hoher Overlap + substanzielle Refs → info_in_text
    if overlap_score >= 0.30 and ref_word_count >= 15:
        return "info_in_text", "high"

    # 4. Moderater Overlap + lange Refs → wahrscheinlich info_in_text, aber unsicher
    if overlap_score >= 0.15 and ref_word_count >= 40:
        return "info_in_text", "low"

    # 5. Mittlerer Bereich → partial, unsicher
    if 0.05 <= overlap_score < 0.30:
        return "partial", "low"

    # 6. Kein Overlap, aber substanzielle Refs → könnte partial sein
    if overlap_score < 0.05 and ref_word_count >= 15:
        return "only_table", "low"

    return "partial", "low"


# ===========================================================================
# 5. STUFE 2 – spaCy-KLASSIFIKATOR
# ===========================================================================

def classify_spacy(table: dict, full_text: str, regex_label: str) -> str:
    """
    Stufe 2: spaCy-basierte Klassifikation.
    Nur aufgerufen bei Regex confidence='low'.
    """
    if not SPACY_OK:
        return regex_label

    refs = table.get("references") or []
    all_refs_text = " ".join(refs)
    ref_word_count = len(all_refs_text.split())

    window_parts = [get_window_forward(full_text, ref) for ref in refs]
    window_combined = " ".join(window_parts)

    table_text, _ = extract_table_content(table)

    # spaCy-basierte Zahlenerkennung (präziser)
    table_nums = extract_numbers_spacy(table_text)
    window_nums = extract_numbers_spacy(window_combined)

    if table_nums:
        matched = fuzzy_match(table_nums, window_nums)
        overlap_spacy = matched / len(table_nums)
    else:
        overlap_spacy = 0.0

    # Entscheidung
    if overlap_spacy >= 0.25 and ref_word_count >= 15:
        return "info_in_text"

    if overlap_spacy < 0.05 and ref_word_count < 20:
        return "only_table"

    if ref_word_count >= 20 and overlap_spacy < 0.10:
        return "partial"

    # Fallback: Regex-Label beibehalten
    return regex_label


# ===========================================================================
# 6. STUFE 3 – OLLAMA-LLM-KLASSIFIKATOR
# ===========================================================================

# Prompt fragt direkt nach Label (kein Float!) – das war der Fehler im
# Original-Notebook, das zu κ=0.02 geführt hat (72% der Antworten = "0.8").
_LLM_PROMPT = """\
You are a scientific text analyst classifying how much a table's information appears in the surrounding text.

LABEL DEFINITIONS:
- info_in_text : Concrete numerical values from the table are explicitly repeated in the text (e.g. "the score was 0.41")
- partial      : The text references the table and describes it qualitatively, but rarely or never repeats exact numbers
- only_table   : The text only points to the table ("see Table 1", "(Table 1)") without any description of its content
- no_refs      : No in-text reference to this table at all

---
TABLE CAPTION: {caption}

TABLE CONTENT (excerpt, first rows):
{table_content}

IN-TEXT REFERENCES (sentences that mention this table):
{refs}

TEXT WINDOW (up to 500 chars after the reference):
{window}

---
FEW-SHOT EXAMPLES:

Example A:
  Table content: Method | Score \n Regex | 0.33 \n spaCy | 0.41
  Reference: "As shown in Table 2, spaCy achieved 0.41 and Regex scored 0.33."
  → info_in_text

Example B:
  Table content: Gene | p-value \n BRCA1 | 0.001 \n TP53 | 0.04
  Reference: "Table 3 summarises the differential expression results across all genes."
  → partial

Example C:
  Table content: Sample | Concentration \n A | 5.2 mM \n B | 3.8 mM
  Reference: "See Table 1."
  → only_table

---
Respond with EXACTLY one word — the label that best fits:
info_in_text / partial / only_table / no_refs

Label:"""

_VALID_LABELS = {"info_in_text", "partial", "only_table", "no_refs"}


def classify_llm(table: dict, full_text: str, prev_label: str) -> str:
    """
    Stufe 3: Ollama-LLM-Klassifikation.
    Fragt direkt nach einem Label (nicht Float!) – vermeidet Halluzinations-Problem.
    Gibt prev_label zurück wenn Ollama nicht verfügbar oder Antwort ungültig.
    """
    if not OLLAMA_OK or not _ollama_model:
        return prev_label

    refs = table.get("references") or []
    caption = table.get("caption") or table.get("name") or ""
    table_text, _ = extract_table_content(table)

    # Textfenster: bestes (längstes) Referenz-Fenster
    windows = [get_window_forward(full_text, ref) for ref in refs]
    best_window = max(windows, key=len) if windows else ""

    # Tabelle auf lesbare Zeilen kürzen (max 6 Zeilen für den Prompt)
    try:
        content = json.loads(table.get("content") or "{}")
        headers = content.get("headers") or content.get("columns") or []
        data_rows = content.get("data", [])[:6]
        header_line = " | ".join(str(h) for h in headers)
        data_lines = "\n".join(" | ".join(str(c) for c in row) for row in data_rows)
        table_repr = (header_line + "\n" + data_lines).strip()
    except Exception:
        table_repr = table_text[:400]

    prompt = _LLM_PROMPT.format(
        caption=caption[:200],
        table_content=table_repr[:600],
        refs=(" ".join(refs))[:500],
        window=best_window[:500],
    )

    try:
        response = _ollama_lib.chat(
            model=_ollama_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.0},   # deterministisch
        )
        raw = response["message"]["content"].strip().lower()

        # Antwort parsen: erstes gültiges Label aus der Antwort extrahieren
        for label in _VALID_LABELS:
            if label in raw:
                return label

        # Fallback: Antwort enthält keines der Labels
        return prev_label

    except Exception as e:
        # Ollama-Fehler (Timeout, Modell nicht geladen etc.) → Fallback
        return prev_label


# ===========================================================================
# 7. HAUPT-KASKADE
# ===========================================================================

def classify_table_cascade(table: dict, full_text: str) -> tuple[str, str]:
    """
    Vollständige Kaskade: Regex → spaCy → Ollama-LLM
    Gibt (label, method_used) zurück.

    LLM wird nur für echte Grenzfälle aufgerufen (partial ↔ info_in_text),
    um Laufzeit zu sparen. no_refs und only_table mit hoher Konfidenz
    werden nie ans LLM weitergegeben.
    """
    # Stufe 1: Regex
    regex_label, confidence = classify_regex(table, full_text)

    if confidence == "high":
        return regex_label, "regex"

    # Stufe 2: spaCy (präzisere Zahlenerkennung)
    after_spacy = classify_spacy(table, full_text, regex_label) if SPACY_OK else regex_label
    method = "spacy" if SPACY_OK else "regex_only"

    # Stufe 3: LLM – nur für ambige Fälle (partial / info_in_text)
    # no_refs und only_table werden hier nicht mehr ans LLM gegeben
    if OLLAMA_OK and after_spacy in ("partial", "info_in_text"):
        final = classify_llm(table, full_text, after_spacy)
        return final, "llm"

    return after_spacy, method


# ===========================================================================
# 8. PIPELINE ÜBER ALLE PAPERS
# ===========================================================================

def run_pipeline(output_dir: pathlib.Path) -> pd.DataFrame:
    """
    Läuft die Kaskade über alle JSON-Dateien in output_dir.
    """
    json_files = sorted(output_dir.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"Keine JSON-Dateien in {output_dir}")

    print(f"Verarbeite {len(json_files)} Dateien aus {output_dir}")

    rows = []
    table_global_idx = 0  # globaler Index für Matching mit Annotation

    for fpath in tqdm(json_files, desc="Pipeline"):
        try:
            with open(fpath, encoding="utf-8") as f:
                doc = json.load(f)
        except Exception:
            continue

        full_text = doc.get("text", "")
        doi = doc.get("doi", fpath.stem)

        for i, table in enumerate(doc.get("tables", [])):
            label, method = classify_table_cascade(table, full_text)
            _, is_complete = extract_table_content(table)
            refs = table.get("references") or []

            rows.append({
                "idx":             table_global_idx,
                "file":            fpath.name,
                "doi":             doi,
                "table_idx":       i,
                "predicted_label": label,
                "method_used":     method,
                "table_complete":  is_complete,
                "ref_count":       len(refs),
                "caption":         (table.get("caption") or "")[:80],
            })
            table_global_idx += 1

    return pd.DataFrame(rows)


# ===========================================================================
# 9. EVALUATION GEGEN GROUND TRUTH
# ===========================================================================

def evaluate(predictions_df: pd.DataFrame, annot_path: pathlib.Path) -> float | None:
    """
    Vergleicht Predictions mit manueller Annotation.
    Erwartet CSV mit Spalten 'idx' und 'manual'.
    """
    try:
        from sklearn.metrics import cohen_kappa_score, classification_report
    except ImportError:
        print("scikit-learn nicht installiert: pip install scikit-learn")
        return None

    if not annot_path.exists():
        print(f"\nKeine Annotationsdatei gefunden unter:\n  {annot_path}")
        print("Bitte lege die Datei dort ab und führe das Skript erneut aus.")
        return None

    gt = pd.read_csv(annot_path)

    # Spaltenprüfung
    if "idx" not in gt.columns or "manual" not in gt.columns:
        print(f"Annotation-CSV hat falsche Spalten: {list(gt.columns)}")
        print("Erwartet: 'idx' und 'manual'")
        return None

    merged = predictions_df.merge(gt[["idx", "manual"]], on="idx", how="inner")

    if len(merged) == 0:
        print("FEHLER: Kein Überschneidung zwischen Predictions (idx) und Ground Truth.")
        print(f"  Predictions idx range: {predictions_df['idx'].min()}–{predictions_df['idx'].max()}")
        print(f"  Ground Truth idx range: {gt['idx'].min()}–{gt['idx'].max()}")
        return None

    y_true = merged["manual"]
    y_pred = merged["predicted_label"]

    kappa = cohen_kappa_score(y_true, y_pred)
    accuracy = (y_true == y_pred).mean()

    print("\n" + "=" * 60)
    print("EVALUATION ERGEBNISSE")
    print("=" * 60)
    print(f"Cohen's Kappa : κ = {kappa:.3f}")
    print(f"Accuracy      : {accuracy:.1%}  ({len(merged)} Tabellen)")
    print()

    print("Label-Verteilung (True vs Predicted):")
    dist = pd.DataFrame({
        "True":      y_true.value_counts(),
        "Predicted": y_pred.value_counts(),
    }).fillna(0).astype(int)
    print(dist.to_string())
    print()

    print("Classification Report:")
    print(classification_report(y_true, y_pred, zero_division=0))

    print("Verwendete Methode (Stufe der Kaskade):")
    print(merged["method_used"].value_counts().to_string())

    # Fehleranalyse: häufigste Verwechslungen
    print("\nTop-5 Verwechslungen:")
    confusion = merged.groupby(["manual", "predicted_label"]).size().reset_index(name="n")
    wrong = confusion[confusion["manual"] != confusion["predicted_label"]].nlargest(5, "n")
    print(wrong.to_string(index=False))

    return kappa


# ===========================================================================
# 10. MAIN
# ===========================================================================

def main():
    if not OUTPUT_DIR.exists():
        print(f"FEHLER: output-Verzeichnis nicht gefunden:\n  {OUTPUT_DIR}")
        sys.exit(1)

    # Pipeline ausführen
    df = run_pipeline(OUTPUT_DIR)
    print(f"\nVerarbeitete Tabellen gesamt: {len(df)}")

    print("\nLabel-Verteilung (Predictions):")
    print(df["predicted_label"].value_counts().to_string())

    print("\nMethoden-Verteilung:")
    print(df["method_used"].value_counts().to_string())

    # Ergebnisse speichern
    df.to_csv(RESULTS_PATH, index=False)
    print(f"\nErgebnisse gespeichert: {RESULTS_PATH}")

    # Evaluation (nur wenn Annotation vorhanden)
    kappa = evaluate(df, ANNOT_PATH)

    if kappa is not None:
        print(f"\nFazit: κ = {kappa:.3f}")
        if kappa < 0.2:
            print("  → Schwache Übereinstimmung")
        elif kappa < 0.4:
            print("  → Geringe Übereinstimmung")
        elif kappa < 0.6:
            print("  → Moderate Übereinstimmung ✓")
        elif kappa < 0.8:
            print("  → Gute Übereinstimmung ✓✓")
        else:
            print("  → Sehr gute Übereinstimmung ✓✓✓")


if __name__ == "__main__":
    main()
