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
MODEL_NAME = sys.argv[3] if len(sys.argv) > 3 else "qwen/qwen3-vl-4b" # Changed default model name
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

# --- TABELLEN-HEADER ---
# Definiere die Spaltenbreiten für eine bessere Lesbarkeit
COL_WIDTH_ORIGINAL = 40
COL_WIDTH_CHECKSUM = 12
COL_WIDTH_NEWNAME = 40
COL_WIDTH_STATUS = 15
COL_WIDTH_TARGET_FOLDER = 20 # Neue Spalte für den Zielordner

header = (
    f"{'Original Filename':<{COL_WIDTH_ORIGINAL}} | "
    f"{'Checksum':<{COL_WIDTH_CHECKSUM}} | "
    f"{'New Filename':<{COL_WIDTH_NEWNAME}} | "
    f"{'Status':<{COL_WIDTH_STATUS}} | "
    f"{'Target Folder':<{COL_WIDTH_TARGET_FOLDER}} | " # Zielordner in Header
    f"{'Error Message'}"
)
print("\n" + header)
print("-" * len(header)) # Trennlinie

processed_files_count = 0

for pdf_path in PDF_DIR.glob("*.pdf"):
    original_filename = pdf_path.name
    pdf_stem = pdf_path.stem 
    checksum = "N/A" # Default value
    new_filename_stem = ""
    status = "Error"
    error_message = ""
    target_folder_display = "" # Variable für die Anzeige des Zielordners
    
    try:
        checksum = generate_checksum(pdf_path)
    except Exception as e:
        error_message = f"Checksum error: {e}"
        print(f"\n{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {'N/A':<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        continue # Skip to next file if checksum fails

    # [PDF-Öffnen und Bild-Konvertierung (PyMuPDF)]
    doc = None # Initialize doc to None
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            status = "Skipped"
            error_message = "No pages in PDF"
            new_filename_stem = f"SKIPPED_{clean_filename(pdf_stem)}_{checksum}"
            target_folder_display = "N/A"
            print(f"\n{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_stem:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
            continue
            
        page = doc.load_page(0)
        
        zoom = 1.5 
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_data = pix.tobytes(output="jpeg", jpg_quality=85)
        image = Image.open(io.BytesIO(img_data))
        base64_img = pil_image_to_base64(image, img_format="JPEG")
        del image 
    except Exception as e:
        status = "Error"
        error_message = f"Page conversion error: {e}"
        new_filename_stem = f"ERROR_{clean_filename(pdf_stem)}_{checksum}"
        target_folder_display = "N/A"
        print(f"\n{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_stem:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        if doc:
            doc.close()
        continue

    # 1. ERSTELLUNG DES DYNAMISCHEN PROMPTS (mit spezifischen Schweizer Steuerkriterien)
    dynamic_prompt = PROMPT_TEMPLATE.format(original_filename=pdf_stem)

    # 2. Modellabfrage und Parsing
    model_output = analyze_image_with_lm_studio(base64_img, dynamic_prompt)
    
    if model_output.startswith("FEHLER"):
        status = "Error"
        error_message = f"Model API error: {model_output}"
        new_filename_stem = f"MODEL_ERROR_{clean_filename(pdf_stem)}_{checksum}"
        target_folder_display = "N/A"
        print(f"\n{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_stem:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        if doc:
            doc.close()
        continue

    marker = "STEUER_UNBEKANNT"
    name_part = ""
    
    try:
        name_part, marker_part = model_output.split('|', 1)
        new_filename_base = clean_filename(name_part)
        marker = marker_part.strip().upper()
        if marker not in ["STEUER_JA", "STEUER_NEIN"]:
            marker = "STEUER_UNBEKANNT"
            error_message = f"Invalid tax marker '{marker_part}' received."
            # Print error but continue processing with unknown marker
            print(f"\n{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {'N/A':<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
            
    except ValueError:
        error_message = f"Invalid model output format: '{model_output}'"
        new_filename_base = f"INVALID_FORMAT_{clean_filename(pdf_stem)}"
        target_folder_display = "N/A"
        print(f"\n{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_base:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        # Continue processing with fallback name, but log the error
    
    # Validiere Format und erstelle den neuen Dateinamen-Stamm
    if not re.match(r'^\d{8}_.+', new_filename_base):
        error_message = f"Filename format invalid (expected YYYYMMDD_...): '{new_filename_base}'"
        new_filename_base = f"INVALID_DATE_{clean_filename(pdf_stem)}"
        # Continue processing with fallback name, but log the error
        
    final_filename_stem = f"{new_filename_base}_{checksum}"

    # Bestimme den Zielordner und setze den Status
    TARGET_BASE_DIR = OUTPUT_DIR_ANDERE
    status = "Success" # Assume success unless an error occurs during saving
    if marker == "STEUER_JA":
        TARGET_BASE_DIR = OUTPUT_DIR_STEUER
        status = "Success (Tax Relevant)"
    elif marker == "STEUER_UNBEKANNT":
        status = "Success (Unknown Tax)"
    else:
        status = "Success" # Default success
    
    target_folder_display = TARGET_BASE_DIR.name # Get the name of the target folder for display

    # 3. Speichern mit Kollisionsschutz
    current_filename_stem_for_save = final_filename_stem 
    
    saved = False
    for attempt in range(MAX_RETRIES):
        current_filename = f"{current_filename_stem_for_save}.pdf"
        new_path = TARGET_BASE_DIR / current_filename

        if not new_path.exists():
            try:
                shutil.copy2(pdf_path, new_path)
                new_filename_stem = current_filename_stem_for_save # Populate new_filename_stem on success
                saved = True
                break # Erfolgreich gespeichert, Schleife beenden
            except Exception as e:
                error_message = f"File copy error: {e}"
                status = "Error"
                new_filename_stem = f"SAVE_ERROR_{clean_filename(pdf_stem)}_{checksum}"
                target_folder_display = "N/A"
                break # Fehler beim Kopieren, Schleife beenden
        else:
            # Wenn die Datei mit Checksumme bereits existiert, generiere einen neuen Suffix
            rand_suffix = random.randint(100, 999) 
            current_filename_stem_for_save = f"{final_filename_stem}_{rand_suffix}"
            # print(f"  Dateiname '{current_filename}' existiert bereits. Versuche neuen Namen: '{current_filename_stem_for_save}.pdf'") # Optional: Log this
            
            if attempt == MAX_RETRIES - 1:
                error_message = f"Max retries ({MAX_RETRIES}) reached for saving."
                status = "Error"
                new_filename_stem = f"SAVE_MAX_RETRIES_{clean_filename(pdf_stem)}_{checksum}"
                target_folder_display = "N/A"
                break # Maximale Wiederholungen erreicht
        
    if not saved:
        # If not saved after retries, ensure an error status and message are set
        if status != "Error": # Avoid overwriting a specific error message
            status = "Error"
            error_message = "Failed to save file after multiple attempts."
        
        # Use the last attempted filename stem for reporting if saving failed
        if not new_filename_stem: # If it wasn't set by an earlier error
            new_filename_stem = current_filename_stem_for_save

    # --- TABELLENZEILE AUSGABE ---
    # Truncate long filenames if they exceed column width
    display_original = (original_filename[:COL_WIDTH_ORIGINAL-3] + '...') if len(original_filename) > COL_WIDTH_ORIGINAL else original_filename
    display_new_filename = (new_filename_stem[:COL_WIDTH_NEWNAME-3] + '...') if len(new_filename_stem) > COL_WIDTH_NEWNAME else new_filename_stem
    
    row = (
        f"{display_original:<{COL_WIDTH_ORIGINAL}} | "
        f"{checksum:<{COL_WIDTH_CHECKSUM}} | "
        f"{display_new_filename:<{COL_WIDTH_NEWNAME}} | "
        f"{status:<{COL_WIDTH_STATUS}} | "
        f"{target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | " # Zielordner anzeigen
        f"{error_message}"
    )
    print(row)
    
    processed_files_count += 1

    if doc:
        doc.close()

print("-" * len(header)) # Trennlinie am Ende
print(f"\nVerarbeitung abgeschlossen. {processed_files_count} Dateien wurden verarbeitet.")
