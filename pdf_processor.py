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
# Die Zielordner werden jetzt dynamisch basierend auf den Kategorien erstellt
# Wir definieren hier nur die Basisverzeichnisse, die Unterordner werden bei Bedarf erstellt
OUTPUT_BASE_DIR = PDF_DIR # Die Unterordner werden direkt unter dem PDF_DIR erstellt

# Erstelle die Basisverzeichnisse, falls sie nicht existieren
OUTPUT_BASE_DIR.mkdir(exist_ok=True)


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
    # Use sys.stdout.buffer.write and encode to handle potential Unicode issues
    sys.stdout.buffer.write(b"\n--- DEBUG: LLM Input Prompt ---\n")
    sys.stdout.buffer.write(prompt.encode('utf-8', 'replace'))
    sys.stdout.buffer.write(b"\n--- END DEBUG: LLM Input Prompt ---\n")
    sys.stdout.flush()

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
            max_tokens=150, # Für detaillierten Namen + Marker
            temperature=0.1, 
        )
        
        # Explicitly clear context or resources if the client object allows for it.
        # For the OpenAI Python client, there isn't a direct method to "eject" or "clear context"
        # for a single API call like this. The client is designed to be stateless per call.
        # However, if the underlying LM Studio server maintains context, we might need to
        # ensure the request itself doesn't carry over previous conversation state.
        # The current structure of sending a single user message with the image should
        # inherently prevent cross-conversation context from being maintained by the client.
        # If LM Studio server-side context is the issue, it might require specific server configurations
        # or a different API endpoint if available.
        
        # For now, we rely on the stateless nature of the client call.
        # If issues persist, further investigation into LM Studio's server-side context management
        # would be needed.

        llm_output = response.choices[0].message.content.strip()
        
        sys.stdout.buffer.write(b"\n--- DEBUG: LLM Raw Output ---\n")
        sys.stdout.buffer.write(llm_output.encode('utf-8', 'replace'))
        sys.stdout.buffer.write(b"\n--- END DEBUG: LLM Raw Output ---\n")
        sys.stdout.flush()
        
        return llm_output

    except Exception as e:
        # In case of an error, ensure any potential resources are cleaned up.
        # For the OpenAI client, this is generally handled by Python's garbage collection.
        # If specific cleanup is needed for LM Studio, it would depend on its API.
        error_message = f"FEHLER: {e}"
        sys.stdout.buffer.write(b"\n--- DEBUG: LLM API Error ---\n")
        sys.stdout.buffer.write(error_message.encode('utf-8', 'replace'))
        sys.stdout.buffer.write(b"\n--- END DEBUG: LLM API Error ---\n")
        sys.stdout.flush()
        return error_message

# --- HAUPTPROGRAMM ---
if not PDF_DIR.is_dir():
    print(f"Fehler: '{PDF_DIR}' ist kein gültiges Verzeichnis.")
    sys.exit(1)

print(f"Starte Dateiumbenennung und -verschiebung mit Modell '{MODEL_NAME}' in: {PDF_DIR}")
print(f"Zielordner werden basierend auf Kategorien erstellt unter: {OUTPUT_BASE_DIR}")

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
    # --- VARIABLEN-RESET FÜR JEDE DATEI ---
    original_filename = pdf_path.name
    pdf_stem = pdf_path.stem 
    checksum = "N/A" # Default value
    new_filename_stem = ""
    status = "Error" # Default status
    error_message = ""
    target_folder_display = "" # Variable für die Anzeige des Zielordners
    doc = None # Initialize doc to None for each file
    # --- ENDE VARIABLEN-RESET ---

    print(f"\n--- Processing file: {original_filename} ---")

    try:
        checksum = generate_checksum(pdf_path)
    except Exception as e:
        error_message = f"Checksum error: {e}"
        # Print the row with default/error values
        print(f"\n{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {'N/A':<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        continue # Skip to next file if checksum fails

    # [PDF-Öffnen und Bild-Konvertierung (PyMuPDF)]
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            status = "Skipped"
            error_message = "No pages in PDF"
            new_filename_stem = f"SKIPPED_{clean_filename(pdf_stem)}_{checksum}"
            target_folder_display = "N/A"
            print(f"\n{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_stem:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
            doc.close() # Close the document before continuing
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
    
    # --- RESET VARIABLEN VOR MODELL-OUTPUT-VERARBEITUNG ---
    name_part = ""
    categories = [] # Liste für alle identifizierten Kategorien
    new_filename_base = "" # Reset for this file
    # --- ENDE RESET VARIABLEN ---

    if model_output.startswith("FEHLER"):
        status = "Error"
        error_message = f"Model API error: {model_output}"
        new_filename_stem = f"MODEL_ERROR_{clean_filename(pdf_stem)}_{checksum}"
        target_folder_display = "N/A"
        print(f"\n{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_stem:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        if doc:
            doc.close()
        continue

    try:
        # Versuche, die Ausgabe zu parsen
        parts = model_output.split('|', 1)
        if len(parts) == 2:
            name_part = parts[0]
            categories_part = parts[1]
            
            new_filename_base = clean_filename(name_part)
            
            # Parse die Kategorien
            raw_categories = categories_part.split('#')
            valid_categories = []
            for cat in raw_categories:
                cat_upper = cat.strip().upper()
                # Liste der erlaubten Kategorien aus dem Prompt
                allowed_cats = ['STEUER', 'RECHNUNGEN', 'FINANZEN_ALLGEMEIN', 'VERSICHERUNG', 'OTHER']
                if cat_upper in allowed_cats:
                    valid_categories.append(cat_upper)
                else:
                    # Wenn eine Kategorie ungültig ist, behandle sie als Fehler oder ignoriere sie
                    # Hier entscheiden wir uns, sie zu ignorieren und ggf. 'OTHER' zu verwenden, falls keine gültigen gefunden werden
                    pass 
            
            if not valid_categories: # Wenn keine gültigen Kategorien gefunden wurden
                valid_categories.append('OTHER')
                error_message = f"Model returned invalid categories: '{categories_part}'. Defaulting to 'OTHER'."
            
            categories = valid_categories # Setze die gültigen Kategorien
        else:
            # Wenn die Ausgabe nicht das erwartete Format hat (kein '|' gefunden)
            raise ValueError("Output does not contain the expected '|' separator.")

    except ValueError as ve:
        # Fehlerbehandlung für ungültiges Format oder fehlenden Separator
        error_message = f"Invalid model output format or missing separator: '{model_output}'. Details: {ve}"
        new_filename_base = f"INVALID_FORMAT_{clean_filename(pdf_stem)}" # Fallback-Dateiname
        categories = ['OTHER'] # Fallback-Kategorie
        status = "Error" # Markiere als Fehler, da das Format nicht stimmt
        # Print error but continue processing with fallback name
        print(f"\n{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {'N/A':<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        if doc:
            doc.close()
        continue # Fahre mit der nächsten Datei fort, da die Verarbeitung hier fehlschlug
    
    # Validiere Format und erstelle den neuen Dateinamen-Stamm
    if not re.match(r'^\d{8}_.+', new_filename_base):
        # Wenn der generierte Dateiname nicht dem YYYYMMDD_ Format entspricht
        error_message = f"Filename format invalid (expected YYYYMMDD_...): '{new_filename_base}'"
        new_filename_base = f"INVALID_DATE_{clean_filename(pdf_stem)}" # Fallback-Dateiname
        # Continue processing with fallback name, but log the error
        
    final_filename_stem = f"{new_filename_base}_{checksum}"

    # Bestimme den Zielordner basierend auf den Kategorien
    # Wenn mehrere Kategorien vorhanden sind, wird die erste als Hauptordner verwendet.
    # Dies kann angepasst werden, falls eine komplexere Logik gewünscht ist.
    primary_category = categories[0] if categories else 'OTHER'
    # Ensure the category name is uppercase for directory creation
    primary_category_upper = primary_category.upper() 
    TARGET_SUB_DIR = pathlib.Path(primary_category_upper)
    TARGET_FULL_DIR = OUTPUT_BASE_DIR / TARGET_SUB_DIR
    
    # Erstelle den Zielordner, falls er nicht existiert
    try:
        TARGET_FULL_DIR.mkdir(parents=True, exist_ok=True)
        target_folder_display = TARGET_SUB_DIR.name # Nur der Name des Unterordners für die Anzeige
    except OSError as e:
        error_message = f"Could not create target directory '{TARGET_FULL_DIR}': {e}"
        status = "Error"
        new_filename_stem = f"DIR_ERROR_{clean_filename(pdf_stem)}_{checksum}"
        target_folder_display = "N/A"
        print(f"\n{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_stem:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        if doc:
            doc.close()
        continue

    # Setze den Status basierend auf den Kategorien
    if "STEUER" in categories:
        status = "Success (Tax Relevant)"
    elif "OTHER" in categories:
        status = "Success (Other)"
    else:
        status = "Success" # Default success for other categories

    # 3. Speichern mit Kollisionsschutz
    current_filename_stem_for_save = final_filename_stem 
    
    saved = False
    for attempt in range(MAX_RETRIES):
        current_filename = f"{current_filename_stem_for_save}.pdf"
        new_path = TARGET_FULL_DIR / current_filename

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
print(f"\nVerarbeitung abgeschlossen. {processed_files_count} Dateien wurden analysiert.")
