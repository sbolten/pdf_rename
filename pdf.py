import os
import pathlib
import io
import base64
import sys
import fitz # PyMuPDF (kein Poppler nötig!)
from PIL import Image
from openai import OpenAI
import re
import shutil
import random 

# --- KONFIGURATION ---
# Das Verzeichnis, das die PDFs enthält (als erstes Kommandozeilenargument)
try:
    PDF_DIR = pathlib.Path(sys.argv[1])
except IndexError:
    print("Fehler: Bitte geben Sie den Pfad zu einem Verzeichnis als Argument an.")
    sys.exit(1)

# ZIELVERZEICHNISSE (werden im Arbeitsverzeichnis erstellt)
OUTPUT_DIR_ANDERE = PDF_DIR / "andere"
OUTPUT_DIR_STEUER = PDF_DIR / "steuer_relevant"

# Erstelle beide Zielordner
OUTPUT_DIR_ANDERE.mkdir(exist_ok=True)
OUTPUT_DIR_STEUER.mkdir(exist_ok=True)

# Modell- und API-Einstellungen
LM_STUDIO_URL = "http://127.0.0.1:1234/v1" 
MODEL_NAME = "Qwen/Qwen3-V1-8B" 
MAX_RETRIES = 5 

# Initialisiere den OpenAI-Client für LM Studio
client = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio") 

# --- HILFSFUNKTIONEN ---

def pil_image_to_base64(img: Image.Image, img_format: str = "JPEG") -> str:
    """Konvertiert ein PIL Image-Objekt in einen Base64-String."""
    buffered = io.BytesIO()
    img.save(buffered, format=img_format)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def clean_filename(filename: str) -> str:
    """Ersetzt Sonderzeichen durch Unterstriche und normalisiert."""
    filename = re.sub(r'[^\w\s-]', '_', filename).strip()
    filename = re.sub(r'[-\s]+', '_', filename)
    
    return filename.lower()

def analyze_image_with_lm_studio(base64_image: str, prompt: str) -> str:
    """Sendet die Base64-kodierte Bilddaten und den Prompt an das lokale LLM."""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ],
                }
            ],
            max_tokens=85, # Für detaillierten Namen + Marker
            temperature=0.1, 
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"FEHLER: {e}"

# --- HAUPTPROGRAMM ---
if not PDF_DIR.is_dir():
    print(f"Fehler: '{PDF_DIR}' ist kein gültiges Verzeichnis.")
    sys.exit(1)

print(f"Starte Dateiumbenennung mit Modell '{MODEL_NAME}' in: {PDF_DIR}")
print(f"Zielordner: '{OUTPUT_DIR_ANDERE.name}' und '{OUTPUT_DIR_STEUER.name}'")


for pdf_path in PDF_DIR.glob("*.pdf"):
    pdf_stem = pdf_path.stem 
    print(f"\n--- Verarbeite PDF: {pdf_path.name} ---")
    
    # [PDF-Öffnen und Bild-Konvertierung (PyMuPDF)]
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  Fehler beim Öffnen von {pdf_path.name}: {e}")
        continue
    
    if doc.page_count == 0:
        print(f"  {pdf_path.name} hat keine Seiten.")
        doc.close()
        continue
        
    page = doc.load_page(0)
    
    try:
        zoom = 1.5 
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_data = pix.tobytes(output="jpeg", jpg_quality=85)
        image = Image.open(io.BytesIO(img_data))
        base64_img = pil_image_to_base64(image, img_format="JPEG")
        del image 
    except Exception as e:
        print(f"  Fehler bei der Konvertierung der Seite: {e}")
        doc.close()
        continue

    # 1. ERSTELLUNG DES DYNAMISCHEN PROMPTS (mit spezifischen Schweizer Steuerkriterien)
    dynamic_prompt = (
        "Analysiere dieses Dokument. Der ursprüngliche Dateiname war: "
        f"'{pdf_stem}'. Nutze diesen Namen als zusätzlichen Hinweis. "
        "Deine einzige Aufgabe ist es, ZWEI Informationen durch ein Pipe-Zeichen '|' getrennt auszugeben: "
        "1. Den Dateinamen im Format 'YYYYMMDD_<inhalt>' mit detailliertem Kontext (Namen, Betreff, Firma, Projekt, etc.). "
        "2. Einen Steuermarker. Entscheide basierend auf den Schweizer Kriterien für Privatpersonen mit Stockwerkeigentum (z.B. berufsbedingte Kosten, Kinderbetreuungskosten, Schuldzinsen, Unterhaltskosten für die Liegenschaft, 3a-Vorsorgebeiträge), ob das Dokument für die Steuererklärung relevant ist. Gib 'STEUER_JA' oder 'STEUER_NEIN' aus. "
        "Du darfst NUR diese beiden Informationen, durch das Pipe-Zeichen getrennt, ausgeben, keine Erklärung. "
        "Beispielausgabe: 20240315_Hauswartrechnung_Stockwerkeigentum_Mai|STEUER_JA"
    )

    # 2. Modellabfrage und Parsing
    print("  Frage Modell nach Dateiname und Steuerrelevanz...")
    model_output = analyze_image_with_lm_studio(base64_img, dynamic_prompt)
    
    if model_output.startswith("FEHLER"):
        print(f"  Fehler: Modellfehler oder Verbindungsfehler: {model_output}")
        doc.close()
        continue

    marker = "STEUER_UNBEKANNT"
    new_filename_base = "" 
    
    try:
        name_part, marker_part = model_output.split('|', 1)
        new_filename_base = clean_filename(name_part)
        marker = marker_part.strip().upper()
        if marker not in ["STEUER_JA", "STEUER_NEIN"]:
            marker = "STEUER_UNBEKANNT"
            print(f"  Ungültiger Steuermarker '{marker_part}' erhalten. Verwende STEUER_UNBEKANNT.")

    except ValueError:
        print(f"  Ungültiges Format vom Modell zurückgegeben: '{model_output}'. Verwende Fallback-Namen.")
        new_filename_base = f"UNGEPRUEFT_{clean_filename(pdf_path.stem)}"
    
    # Validiere Format
    if not re.match(r'^\d{8}_.+', new_filename_base):
        print(f"  Datum-Format ungültig. Verwende Fallback-Namen.")
        new_filename_base = f"UNGUELTIG_{clean_filename(pdf_path.stem)}"
        
    # Bestimme den Zielordner
    if marker == "STEUER_JA":
        TARGET_BASE_DIR = OUTPUT_DIR_STEUER
        print(f"  Ergebnis: {new_filename_base}.pdf (Steuerrelevant)")
    else:
        TARGET_BASE_DIR = OUTPUT_DIR_ANDERE
        print(f"  Ergebnis: {new_filename_base}.pdf ({marker})")

    # 3. Speichern mit Kollisionsschutz
    final_filename_stem = new_filename_base
    final_save_successful = False
    
    for attempt in range(MAX_RETRIES):
        current_filename = f"{final_filename_stem}.pdf"
        new_path = TARGET_BASE_DIR / current_filename

        if not new_path.exists():
            try:
                shutil.copy2(pdf_path, new_path)
                print(f"  Gespeichert als: {TARGET_BASE_DIR.name}/{current_filename}")
                final_save_successful = True
                break
            except Exception as e:
                print(f"  Unerwarteter Fehler beim Kopieren: {e}")
                break
        else:
            rand_suffix = random.randint(100, 999) 
            final_filename_stem = f"{new_filename_base}_{rand_suffix}"
            print(f"  Dateiname '{current_filename}' existiert bereits. Versuche neuen Namen: '{final_filename_stem}.pdf'")
            
            if attempt == MAX_RETRIES - 1:
                print(f"  Maximale Wiederholungsversuche ({MAX_RETRIES}) erreicht. Überspringe Datei.")

    if not final_save_successful:
        print(f"  Speichern für {pdf_path.name} fehlgeschlagen nach {MAX_RETRIES} Versuchen.")
        
    doc.close()

print(f"\nDateiumbenennungsprozess abgeschlossen.")
