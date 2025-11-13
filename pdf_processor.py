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
import hashlib # Importiere hashlib für Checksummen

# --- KONFIGURATION ---
# Das Verzeichnis, das die PDFs enthält (als erstes Kommandozeilenargument)
# Die anderen Argumente werden jetzt dynamisch übergeben
if len(sys.argv) < 2:
    print("Fehler: Bitte geben Sie das PDF-Verzeichnis als erstes Argument an.")
    sys.exit(1)

PDF_DIR = pathlib.Path(sys.argv[1])
TARGET_URL = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:1234/v1" # Standardwert, falls nicht übergeben
MODEL_NAME = sys.argv[3] if len(sys.argv) > 3 else "Qwen/Qwen3-V1-8B" # Standardwert
PROMPT_TEMPLATE = sys.argv[4] if len(sys.argv) > 4 else (
    "Analysiere dieses Dokument. Der ursprüngliche Dateiname war: "
    f"'{{original_filename}}'. Nutze diesen Namen als zusätzlichen Hinweis. "
    "Deine einzige Aufgabe ist es, ZWEI Informationen durch ein Pipe-Zeichen '|' getrennt auszugeben: "
    "1. Den Dateinamen im Format 'YYYYMMDD_<inhalt>' mit detailliertem Kontext (Namen, Betreff, Firma, Projekt, etc.). "
    "2. Einen Steuermarker. Entscheide basierend auf den Schweizer Kriterien für Privatpersonen mit Stockwerkeigentum (z.B. berufsbedingte Kosten, Kinderbetreuungskosten, Schuldzinsen, Unterhaltskosten für die Liegenschaft, 3a-Vorsorgebeiträge), ob das Dokument für die Steuererklärung relevant ist. Gib 'STEUER_JA' oder 'STEUER_NEIN' aus. "
    "Du darfst NUR diese beiden Informationen, durch das Pipe-Zeichen getrennt, ausgeben, keine Erklärung. "
    "Beispielausgabe: 20240315_Hauswartrechnung_Stockwerkeigentum_Mai|STEUER_JA"
) # Standardwert

MAX_RETRIES = 5 

# Initialisiere den OpenAI-Client für LM Studio mit den übergebenen Parametern
try:
    client = OpenAI(base_url=TARGET_URL, api_key="lm-studio") 
except Exception as e:
    print(f"Fehler bei der Initialisierung des OpenAI-Clients: {e}")
    sys.exit(1)

# ZIELVERZEICHNISSE (werden im Arbeitsverzeichnis erstellt)
OUTPUT_DIR_ANDERE = PDF_DIR / "andere"
OUTPUT_DIR_STEUER = PDF_DIR / "steuer_relevant"

# Erstelle beide Zielordner
OUTPUT_DIR_ANDERE.mkdir(exist_ok=True)
OUTPUT_DIR_STEUER.mkdir(exist_ok=True)


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

def generate_checksum(file_path: pathlib.Path) -> str:
    """Generiert eine SHA256-Checksumme für eine Datei."""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(4096) # Lies in Chunks, um Speicher zu sparen
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()[:10] # Nimm die ersten 10 Zeichen für eine kürzere Checksumme

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
    
    # Generiere Checksumme vor der Verarbeitung
    try:
        checksum = generate_checksum(pdf_path)
        print(f"  Checksumme: {checksum}")
    except Exception as e:
        print(f"  Fehler beim Generieren der Checksumme für {pdf_path.name}: {e}")
        checksum = "CHECKSUMMENFEHLER" # Fallback

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
    # Verwende die übergebene Prompt-Vorlage
    dynamic_prompt = PROMPT_TEMPLATE.format(original_filename=pdf_stem)

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
        
    # Füge die Checksumme zum neuen Dateinamen hinzu
    final_filename_stem = f"{new_filename_base}_{checksum}"

    # Bestimme den Zielordner
    if marker == "STEUER_JA":
        TARGET_BASE_DIR = OUTPUT_DIR_STEUER
        print(f"  Ergebnis: {final_filename_stem}.pdf (Steuerrelevant)")
    else:
        TARGET_BASE_DIR = OUTPUT_DIR_ANDERE
        print(f"  Ergebnis: {final_filename_stem}.pdf ({marker})")

    # 3. Speichern mit Kollisionsschutz
    current_filename_stem_for_save = final_filename_stem # Verwende den Stem mit Checksumme
    
    for attempt in range(MAX_RETRIES):
        current_filename = f"{current_filename_stem_for_save}.pdf"
        new_path = TARGET_BASE_DIR / current_filename

        if not new_path.exists():
            try:
                shutil.copy2(pdf_path, new_path)
                print(f"  Gespeichert als: {TARGET_BASE_DIR.name}/{current_filename}")
                break # Erfolgreich gespeichert, Schleife beenden
            except Exception as e:
                print(f"  Unerwarteter Fehler beim Kopieren: {e}")
                break # Fehler beim Kopieren, Schleife beenden
        else:
            # Wenn die Datei mit Checksumme bereits existiert, generiere einen neuen Suffix
            rand_suffix = random.randint(100, 999) 
            current_filename_stem_for_save = f"{final_filename_stem}_{rand_suffix}"
            print(f"  Dateiname '{current_filename}' existiert bereits. Versuche neuen Namen: '{current_filename_stem_for_save}.pdf'")
            
            if attempt == MAX_RETRIES - 1:
                print(f"  Maximale Wiederholungsversuche ({MAX_RETRIES}) erreicht. Überspringe Datei.")
                # Hier könnte man auch die Originaldatei mit Checksumme in ein Fehlerverzeichnis kopieren
        
    doc.close()

print(f"\nDateiumbenennungsprozess abgeschlossen.")
