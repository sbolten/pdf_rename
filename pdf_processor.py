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

def analyze_image_with_lm_studio(base64_image: str, prompt: str, original_filename: str) -> str:
    """Sendet die Base64-kodierte Bilddaten und den Prompt an das lokale LLM."""
    # Print only the filename and the LLM output for debugging
    # Ensure debug output is clearly associated with the current file
    sys.stdout.buffer.write(f"\n--- DEBUG: Initiating LLM call for: {original_filename} ---\n".encode('utf-8', 'replace'))
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
        
        llm_output = response.choices[0].message.content.strip()
        
        # Log LLM output clearly associated with the file
        sys.stdout.buffer.write(f"\n--- DEBUG: LLM Raw Output for {original_filename} ---\n".encode('utf-8', 'replace'))
        sys.stdout.buffer.write(llm_output.encode('utf-8', 'replace'))
        sys.stdout.buffer.write(b"\n--- END DEBUG: LLM Raw Output ---\n")
        sys.stdout.flush()
        
        return llm_output

    except Exception as e:
        error_message = f"LLM API Error: {e}"
        # Log LLM errors clearly associated with the file
        sys.stdout.buffer.write(f"\n--- DEBUG: LLM API Error for {original_filename} ---\n".encode('utf-8', 'replace'))
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

# Iterate through each PDF file in the directory
for pdf_path in PDF_DIR.glob("*.pdf"):
    # --- VARIABLEN-RESET FÜR JEDE DATEI ---
    # These variables are reset for each file to ensure isolation
    original_filename = pdf_path.name
    pdf_stem = pdf_path.stem 
    checksum = "N/A" # Default value
    new_filename_stem = ""
    status = "Error" # Default status
    error_message = ""
    target_folder_display = "" # Variable for displaying the target folder
    doc = None # Initialize doc to None for each file
    model_output = "" # Initialize model_output for each file
    name_part = ""
    categories = [] # List for all identified categories
    new_filename_base = "" # Reset for this file
    # --- ENDE VARIABLEN-RESET ---

    # Print the start of processing for the current file
    # This helps in tracking which file is being processed, especially if errors occur
    print(f"\nProcessing file: {original_filename}...")
    sys.stdout.flush()

    # 1. Generate Checksum
    try:
        checksum = generate_checksum(pdf_path)
    except Exception as e:
        error_message = f"Checksum error: {e}"
        status = "Error"
        new_filename_stem = f"CHECKSUM_ERR_{clean_filename(pdf_stem)}"
        target_folder_display = "N/A"
        # Print the row with default/error values and continue to the next file
        print(f"{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_stem:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        continue # Skip to next file if checksum fails

    # 2. PDF-Öffnen und Bild-Konvertierung (PyMuPDF)
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            status = "Skipped"
            error_message = "No pages in PDF"
            new_filename_stem = f"SKIPPED_{clean_filename(pdf_stem)}"
            target_folder_display = "N/A"
            print(f"{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_stem:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
            doc.close() # Close the document before continuing
            continue
            
        page = doc.load_page(0)
        
        zoom = 1.5 
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_data = pix.tobytes(output="jpeg", jpg_quality=85)
        image = Image.open(io.BytesIO(img_data))
        base64_img = pil_image_to_base64(image, img_format="JPEG")
        del image # Free up memory
        
    except Exception as e:
        status = "Error"
        error_message = f"Page conversion error: {e}"
        new_filename_stem = f"PAGE_ERR_{clean_filename(pdf_stem)}"
        target_folder_display = "N/A"
        print(f"{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_stem:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        if doc:
            doc.close()
        continue

    # 3. Modellabfrage und Parsing
    # Construct the dynamic prompt for the current file
    dynamic_prompt = PROMPT_TEMPLATE.format(original_filename=pdf_stem)
    
    # Call the LLM analysis function for the current file
    model_output = analyze_image_with_lm_studio(base64_img, dynamic_prompt, original_filename)
    
    # Check if the LLM call resulted in an error
    if model_output.startswith("LLM API Error:"):
        status = "Error"
        error_message = model_output # Use the full error message from the function
        new_filename_stem = f"LLM_ERR_{clean_filename(pdf_stem)}"
        target_folder_display = "N/A"
        print(f"{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_stem:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        if doc:
            doc.close()
        continue # Move to the next file

    # 4. Parse the LLM output
    try:
        parts = model_output.split('|', 1)
        if len(parts) == 2:
            name_part = parts[0]
            categories_part = parts[1]
            
            new_filename_base = clean_filename(name_part)
            
            # Parse the categories
            raw_categories = categories_part.split('#')
            valid_categories = []
            for cat in raw_categories:
                cat_upper = cat.strip().upper()
                # List of allowed categories from the prompt
                allowed_cats = ['STEUER', 'RECHNUNGEN', 'FINANZEN_ALLGEMEIN', 'VERSICHERUNG', 'OTHER']
                if cat_upper in allowed_cats:
                    valid_categories.append(cat_upper)
                else:
                    # If a category is invalid, we ignore it. If no valid categories are found, we default to 'OTHER'.
                    pass 
            
            if not valid_categories: # If no valid categories were found
                valid_categories.append('OTHER')
                # Log this as a warning or informational message, not necessarily a file error
                warning_msg = f"Model returned invalid categories: '{categories_part}'. Defaulting to 'OTHER'."
                print(f"  Warning for {original_filename}: {warning_msg}")
                # We don't set an error_message for the file row here, as it's not a critical failure.
            
            categories = valid_categories # Set the valid categories
        else:
            # If the output does not have the expected format (no '|' found)
            raise ValueError("Output does not contain the expected '|' separator.")

    except ValueError as ve:
        # Error handling for invalid format or missing separator
        error_message = f"Invalid model output format: '{model_output}'. Details: {ve}"
        new_filename_base = f"INVALID_FORMAT_{clean_filename(pdf_stem)}" # Fallback filename
        categories = ['OTHER'] # Fallback category
        status = "Error" # Mark as error because format is wrong
        # Print error for the file row and continue to the next file
        print(f"{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {'N/A':<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        if doc:
            doc.close()
        continue # Proceed to the next file as processing failed here

    # 5. Validate format and create the new filename stem
    if not re.match(r'^\d{8}_.+', new_filename_base):
        # If the generated filename does not match the YYYYMMDD_ format
        error_message = f"Filename format invalid (expected YYYYMMDD_...): '{new_filename_base}'"
        new_filename_base = f"INVALID_DATE_{clean_filename(pdf_stem)}" # Fallback filename
        status = "Error" # Mark as error if date format is wrong
        # Print error for the file row and continue to the next file
        print(f"{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {'N/A':<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        if doc:
            doc.close()
        continue # Proceed to the next file

    final_filename_stem = f"{new_filename_base}_{checksum}"

    # 6. Determine the target folder based on categories
    # If multiple categories exist, use the first one as the primary folder.
    primary_category = categories[0] if categories else 'OTHER'
    primary_category_upper = primary_category.upper() 
    TARGET_SUB_DIR = pathlib.Path(primary_category_upper)
    TARGET_FULL_DIR = OUTPUT_BASE_DIR / TARGET_SUB_DIR
    
    # Create the target directory if it doesn't exist
    try:
        TARGET_FULL_DIR.mkdir(parents=True, exist_ok=True)
        target_folder_display = TARGET_SUB_DIR.name # Only the subdirectory name for display
    except OSError as e:
        error_message = f"Could not create target directory '{TARGET_FULL_DIR}': {e}"
        status = "Error"
        new_filename_stem = f"DIR_ERR_{clean_filename(pdf_stem)}"
        target_folder_display = "N/A"
        print(f"{original_filename:<{COL_WIDTH_ORIGINAL}} | {checksum:<{COL_WIDTH_CHECKSUM}} | {new_filename_stem:<{COL_WIDTH_NEWNAME}} | {status:<{COL_WIDTH_STATUS}} | {target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | {error_message}")
        if doc:
            doc.close()
        continue

    # 7. Set the status based on categories
    if "STEUER" in categories:
        status = "Success (Tax)"
    elif "OTHER" in categories:
        status = "Success (Other)"
    else:
        status = "Success" # Default success for other categories

    # 8. Save with collision protection
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
                break # Successfully saved, exit loop
            except Exception as e:
                error_message = f"File copy error: {e}"
                status = "Error"
                new_filename_stem = f"SAVE_ERR_{clean_filename(pdf_stem)}"
                target_folder_display = "N/A"
                break # Error during copy, exit loop
        else:
            # If file with checksum already exists, generate a new suffix
            rand_suffix = random.randint(100, 999) 
            current_filename_stem_for_save = f"{final_filename_stem}_{rand_suffix}"
            # Optional: Log this attempt
            # print(f"  Filename '{current_filename}' already exists. Trying new name: '{current_filename_stem_for_save}.pdf'") 
            
            if attempt == MAX_RETRIES - 1:
                error_message = f"Max retries ({MAX_RETRIES}) reached for saving."
                status = "Error"
                new_filename_stem = f"SAVE_MAX_RETRIES_{clean_filename(pdf_stem)}"
                target_folder_display = "N/A"
                break # Max retries reached

    if not saved:
        # If not saved after retries, ensure an error status and message are set
        if status != "Error": # Avoid overwriting a specific error message
            status = "Error"
            error_message = "Failed to save file after multiple attempts."
        
        # Use the last attempted filename stem for reporting if saving failed
        if not new_filename_stem: # If it wasn't set by an earlier error
            new_filename_stem = current_filename_stem_for_save

    # --- TABELLENZEILE AUSGABE ---
    # Truncate long filenames if they exceed column width for display
    display_original = (original_filename[:COL_WIDTH_ORIGINAL-3] + '...') if len(original_filename) > COL_WIDTH_ORIGINAL else original_filename
    display_new_filename = (new_filename_stem[:COL_WIDTH_NEWNAME-3] + '...') if len(new_filename_stem) > COL_WIDTH_NEWNAME else new_filename_stem
    
    row = (
        f"{display_original:<{COL_WIDTH_ORIGINAL}} | "
        f"{checksum:<{COL_WIDTH_CHECKSUM}} | "
        f"{display_new_filename:<{COL_WIDTH_NEWNAME}} | "
        f"{status:<{COL_WIDTH_STATUS}} | "
        f"{target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | " # Display target folder
        f"{error_message}"
    )
    print(row)
    
    processed_files_count += 1

    if doc:
        doc.close() # Ensure the document is closed after processing

print("-" * len(header)) # Trennlinie am Ende
print(f"\nVerarbeitung abgeschlossen. {processed_files_count} Dateien wurden analysiert.")
