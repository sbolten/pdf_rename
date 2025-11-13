import os
import pathlib
import io
import base64
import sys
import fitz # PyMuPDF
from PIL import Image
from openai import OpenAI
import re
import hashlib # Importiere hashlib für Checksummen

# --- KONFIGURATION ---
# Hardcodiertes Standard-PDF-Verzeichnis
DEFAULT_PDF_DIR = pathlib.Path(r"C:\Users\steph\Documents\dev\python_ai\pdf")

# Standardwerte für URL und Modell, falls nicht übergeben
DEFAULT_TARGET_URL = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL_NAME = "qwen/qwen3-vl-4b"

# Holen Sie sich die Argumente, aber verwenden Sie Standardwerte, wenn sie nicht vorhanden sind.
if len(sys.argv) < 2:
    pdf_dir_arg = str(DEFAULT_PDF_DIR)
    print(f"Kein PDF-Verzeichnis angegeben. Verwende hartcodiertes Standardverzeichnis: '{pdf_dir_arg}'")
else:
    pdf_dir_arg = sys.argv[1]

PDF_DIR = pathlib.Path(pdf_dir_arg)
TARGET_URL = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_TARGET_URL
MODEL_NAME = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_MODEL_NAME

# Stellen Sie sicher, dass das Standardverzeichnis existiert, falls es verwendet wird
if PDF_DIR == DEFAULT_PDF_DIR and not PDF_DIR.exists():
    try:
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Standardverzeichnis '{PDF_DIR}' wurde erstellt. Bitte legen Sie Ihre PDFs dort ab.")
    except OSError as e:
        print(f"Fehler beim Erstellen des Standardverzeichnisses '{PDF_DIR}': {e}")
        sys.exit(1)


# Neuer, spezifischer Prompt für dieses Skript
NEW_PROMPT_TEMPLATE = (
    "Analysiere dieses Dokument. Der ursprüngliche Dateiname war: '{original_filename}'. "
    "Deine einzige Aufgabe ist es, einen neuen Dateinamen im Format 'YYYYMMDD_<KATEGORIE>_<inhalt>' auszugeben. "
    "Die KATEGORIE muss aus dieser Liste gewählt werden: 'RECHNUNG', 'ANGEBOT', 'LOHNABRECHNUNG', 'PROTOKOLL', 'BERICHT', 'ANDERES'. "
    "Der Inhalt muss kurz und prägnant sein und alle relevanten Stichworte enthalten. "
    "Gib NUR den neuen Dateinamen aus, ohne weitere Erklärungen oder Formatierungen. "
    "Beispielausgabe: 20240515_RECHNUNG_Rechnung_Musterfirma_Mai"
)

MAX_RETRIES = 3 # Weniger Retries für dieses einfache Skript

# Initialisiere den OpenAI-Client für LM Studio
try:
    client = OpenAI(base_url=TARGET_URL, api_key="lm-studio")
except Exception as e:
    print(f"Fehler bei der Initialisierung des OpenAI-Clients: {e}")
    sys.exit(1)

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
            chunk = f.read(4096)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()[:10]

def analyze_document_with_lm_studio(base64_image: str, prompt: str) -> str:
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
            max_tokens=100, # Erhöhe max_tokens für potenziell längere Dateinamen
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"FEHLER: {e}"

# --- HAUPTPROGRAMM ---
if not PDF_DIR.is_dir():
    print(f"Fehler: '{PDF_DIR}' ist kein gültiges Verzeichnis.")
    sys.exit(1)

print(f"Starte PDF-Verarbeitung (nur Namensgenerierung) in: {PDF_DIR}")
print(f"Verwendetes Modell: '{MODEL_NAME}'")
print(f"Target URL: '{TARGET_URL}'")
print("-" * 80)

processed_files_count = 0

# Durchsuche das Verzeichnis nach PDF-Dateien
pdf_files = list(PDF_DIR.glob("*.pdf"))

if not pdf_files:
    print("Keine PDF-Dateien im angegebenen Verzeichnis gefunden.")
    sys.exit(0)

for pdf_path in pdf_files:
    original_filename = pdf_path.name
    pdf_stem = pdf_path.stem
    new_filename_output = "N/A"
    error_message = ""

    try:
        # [PDF-Öffnen und Bild-Konvertierung (PyMuPDF)]
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            new_filename_output = f"SKIPPED_{clean_filename(pdf_stem)}_NO_PAGES"
            error_message = "No pages in PDF"
        else:
            page = doc.load_page(0)
            zoom = 1.5
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes(output="jpeg", jpg_quality=85)
            image = Image.open(io.BytesIO(img_data))
            base64_img = pil_image_to_base64(image, img_format="JPEG")
            del image

            # Erstellung des dynamischen Prompts
            dynamic_prompt = NEW_PROMPT_TEMPLATE.format(original_filename=pdf_stem)

            # Modellabfrage und Parsing
            model_output = analyze_document_with_lm_studio(base64_img, dynamic_prompt)

            if model_output.startswith("FEHLER"):
                new_filename_output = f"MODEL_ERROR_{clean_filename(pdf_stem)}"
                error_message = f"Model API error: {model_output}"
            else:
                # Validierung und Bereinigung des Namens
                potential_new_name = model_output.strip()
                
                # Überprüfe, ob der Name das erwartete Format hat (YYYYMMDD_KATEGORIE_...)
                if re.match(r'^\d{8}_(RECHNUNG|ANGEBOT|LOHNABRECHNUNG|PROTOKOLL|BERICHT|ANDERES)_', potential_new_name):
                    new_filename_output = potential_new_name
                else:
                    # Wenn das Format nicht stimmt, versuche es mit einer generischen Kategorie und füge die Checksumme hinzu
                    checksum = generate_checksum(pdf_path)
                    cleaned_base = clean_filename(pdf_stem)
                    new_filename_output = f"INVALID_FORMAT_{checksum}_{cleaned_base}"
                    error_message = f"Invalid filename format from model: '{potential_new_name}'. Expected 'YYYYMMDD_CATEGORY_...'."
        
        if doc:
            doc.close()

    except Exception as e:
        new_filename_output = f"PROCESSING_ERROR_{clean_filename(pdf_stem)}"
        error_message = f"General processing error: {e}"

    # Ausgabe des Ergebnisses
    print(f"{original_filename:<40} -> {new_filename_output}")
    if error_message:
        print(f"  Error: {error_message}")

    processed_files_count += 1

print("-" * 80)
print(f"\nVerarbeitung abgeschlossen. {processed_files_count} Dateien wurden analysiert.")
