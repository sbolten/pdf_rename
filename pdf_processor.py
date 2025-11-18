import os
import pathlib
import io
import base64
import sys
import json
import fitz # PyMuPDF
from PIL import Image
from openai import OpenAI
import re
import shutil
import random 
import hashlib

# --- DYNAMIC CONFIGURATION ---
if len(sys.argv) < 6:
    print("Fehler: Unzureichende Argumente. Erwartet: pdf_dir, target_url, model_name, assembled_prompt, category_map_json")
    sys.exit(1)

PDF_DIR = pathlib.Path(sys.argv[1])
TARGET_URL = sys.argv[2]
MODEL_NAME = sys.argv[3]
ASSEMBLED_PROMPT = sys.argv[4]
CATEGORY_MAP_JSON = sys.argv[5]

try:
    CATEGORY_MAP = json.loads(CATEGORY_MAP_JSON)
except json.JSONDecodeError as e:
    print(f"Fehler: Ungültiges JSON für Category Map: {e}")
    sys.exit(1)

MAX_RETRIES = 5 

# Initialisiere den OpenAI-Client für LM Studio
try:
    client = OpenAI(base_url=TARGET_URL, api_key="lm-studio") 
except Exception as e:
    print(f"Fehler bei der Initialisierung des OpenAI-Clients: {e}")
    sys.exit(1)

OUTPUT_BASE_DIR = PDF_DIR
OUTPUT_BASE_DIR.mkdir(exist_ok=True)


# --- HELPER FUNCTIONS (unchanged) ---

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

def analyze_image_with_lm_studio(base64_image: str, prompt: str, original_filename: str) -> str:
    """Sendet die Base64-kodierte Bilddaten und den Prompt an das lokale LLM."""
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
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                    ],
                }
            ],
            max_tokens=150,
            temperature=0.1, 
        )
        llm_output = response.choices[0].message.content.strip()
        sys.stdout.buffer.write(f"\n--- DEBUG: LLM Raw Output for {original_filename} ---\n".encode('utf-8', 'replace'))
        sys.stdout.buffer.write(llm_output.encode('utf-8', 'replace'))
        sys.stdout.buffer.write(b"\n--- END DEBUG: LLM Raw Output ---\n")
        sys.stdout.flush()
        return llm_output
    except Exception as e:
        error_message = f"LLM API Error: {e}"
        sys.stdout.buffer.write(f"\n--- DEBUG: LLM API Error for {original_filename} ---\n".encode('utf-8', 'replace'))
        sys.stdout.buffer.write(error_message.encode('utf-8', 'replace'))
        sys.stdout.buffer.write(b"\n--- END DEBUG: LLM API Error ---\n")
        sys.stdout.flush()
        return error_message

# --- MAIN PROGRAM ---
if not PDF_DIR.is_dir():
    print(f"Fehler: '{PDF_DIR}' ist kein gültiges Verzeichnis.")
    sys.exit(1)

print(f"Starte Dateiumbenennung und -verschiebung mit Modell '{MODEL_NAME}' in: {PDF_DIR}")
print(f"Zielordner werden basierend auf Kategorien erstellt unter: {OUTPUT_BASE_DIR}")

# --- TABLE HEADER ---
COL_WIDTH_ORIGINAL = 40
COL_WIDTH_CHECKSUM = 12
COL_WIDTH_NEWNAME = 40
COL_WIDTH_STATUS = 15
COL_WIDTH_TARGET_FOLDER = 20

header = (
    f"{'Original Filename':<{COL_WIDTH_ORIGINAL}} | "
    f"{'Checksum':<{COL_WIDTH_CHECKSUM}} | "
    f"{'New Filename':<{COL_WIDTH_NEWNAME}} | "
    f"{'Status':<{COL_WIDTH_STATUS}} | "
    f"{'Target Folder':<{COL_WIDTH_TARGET_FOLDER}} | "
    f"{'Error Message'}"
)
print("\n" + header)
print("-" * len(header))

processed_files_count = 0
for pdf_path in PDF_DIR.glob("*.pdf"):
    original_filename = pdf_path.name
    pdf_stem = pdf_path.stem 
    checksum = "N/A"
    new_filename_stem = ""
    status = "Error"
    error_message = ""
    target_folder_display = ""
    doc = None
    model_output = ""
    name_part = ""
    category_name = ""
    new_filename_base = ""

    print(f"\nProcessing file: {original_filename}...")
    sys.stdout.flush()

    # 1. Generate Checksum
    try:
        checksum = generate_checksum(pdf_path)
    except Exception as e:
        error_message = f"Checksum error: {e}"
        # (Error printing and continue)
        continue

    # 2. PDF Conversion
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            # (Handle empty pdf and continue)
            doc.close()
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
        # (Handle conversion error and continue)
        if doc: doc.close()
        continue

    # 3. LLM Call
    dynamic_prompt = ASSEMBLED_PROMPT.format(original_filename=pdf_stem)
    model_output = analyze_image_with_lm_studio(base64_img, dynamic_prompt, original_filename)
    
    if model_output.startswith("LLM API Error:"):
        # (Handle LLM error and continue)
        if doc: doc.close()
        continue

    # 4. Parse LLM output
    try:
        parts = model_output.split('|', 1)
        if len(parts) == 2:
            name_part = parts[0].strip()
            category_name = parts[1].strip() # Keep original case for map lookup
            
            new_filename_base = clean_filename(name_part)
            
            # Validate the category against the map keys
            if category_name not in CATEGORY_MAP:
                warning_msg = f"Model returned invalid category: '{category_name}'. Defaulting to 'OTHER'."
                print(f"  Warning for {original_filename}: {warning_msg}")
                category_name = 'OTHER' # Fallback
        else:
            raise ValueError("Output does not contain the expected '|' separator.")
    except ValueError as ve:
        # (Handle parsing error and continue)
        if doc: doc.close()
        continue

    # 5. Validate filename format
    if not re.match(r'^\d{8}_.+', new_filename_base):
        # (Handle format error and continue)
        if doc: doc.close()
        continue

    final_filename_stem = f"{new_filename_base}_{checksum}"

    # 6. Determine target folder from CATEGORY_MAP
    # Fallback to 'OTHER' directory if for some reason the category is not in the map
    target_dir_name = CATEGORY_MAP.get(category_name, CATEGORY_MAP.get('OTHER', 'OTHER'))
    TARGET_SUB_DIR = pathlib.Path(target_dir_name)
    TARGET_FULL_DIR = OUTPUT_BASE_DIR / TARGET_SUB_DIR
    
    try:
        TARGET_FULL_DIR.mkdir(parents=True, exist_ok=True)
        target_folder_display = TARGET_SUB_DIR.name
    except OSError as e:
        # (Handle directory creation error and continue)
        if doc: doc.close()
        continue

    # 7. Set status
    status = f"Success ({category_name})"

    # 8. Save with collision protection
    # (This logic remains the same)
    current_filename_stem_for_save = final_filename_stem
    saved = False
    for attempt in range(MAX_RETRIES):
        current_filename = f"{current_filename_stem_for_save}.pdf"
        new_path = TARGET_FULL_DIR / current_filename
        if not new_path.exists():
            try:
                shutil.copy2(pdf_path, new_path)
                new_filename_stem = current_filename_stem_for_save
                saved = True
                break
            except Exception as e:
                error_message = f"File copy error: {e}"
                status = "Error"
                break
        else:
            rand_suffix = random.randint(100, 999) 
            current_filename_stem_for_save = f"{final_filename_stem}_{rand_suffix}"
            if attempt == MAX_RETRIES - 1:
                error_message = f"Max retries ({MAX_RETRIES}) reached for saving."
                status = "Error"
    
    # --- Print table row ---
    # (This logic remains the same)
    display_original = (original_filename[:COL_WIDTH_ORIGINAL-3] + '...') if len(original_filename) > COL_WIDTH_ORIGINAL else original_filename
    display_new_filename = (new_filename_stem[:COL_WIDTH_NEWNAME-3] + '...') if len(new_filename_stem) > COL_WIDTH_NEWNAME else new_filename_stem
    row = (
        f"{display_original:<{COL_WIDTH_ORIGINAL}} | "
        f"{checksum:<{COL_WIDTH_CHECKSUM}} | "
        f"{display_new_filename:<{COL_WIDTH_NEWNAME}} | "
        f"{status:<{COL_WIDTH_STATUS}} | "
        f"{target_folder_display:<{COL_WIDTH_TARGET_FOLDER}} | "
        f"{error_message}"
    )
    print(row)
    
    processed_files_count += 1
    if doc:
        doc.close()

print("-" * len(header))
print(f"\nVerarbeitung abgeschlossen. {processed_files_count} Dateien wurden analysiert.")
