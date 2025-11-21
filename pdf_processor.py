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
# Moved to process_pdfs function arguments

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

def analyze_image_with_lm_studio(client, model_name, base64_image: str, prompt: str, original_filename: str) -> str:
    """Sendet die Base64-kodierte Bilddaten und den Prompt an das lokale LLM."""
    # sys.stdout.buffer.write(f"\n--- DEBUG: Initiating LLM call for: {original_filename} ---\n".encode('utf-8', 'replace'))
    # sys.stdout.flush()
    try:
        response = client.chat.completions.create(
            model=model_name,
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
        # sys.stdout.buffer.write(f"\n--- DEBUG: LLM Raw Output for {original_filename} ---\n".encode('utf-8', 'replace'))
        # sys.stdout.buffer.write(llm_output.encode('utf-8', 'replace'))
        # sys.stdout.buffer.write(b"\n--- END DEBUG: LLM Raw Output ---\n")
        # sys.stdout.flush()
        return llm_output
    except Exception as e:
        error_message = f"LLM API Error: {e}"
        # sys.stdout.buffer.write(f"\n--- DEBUG: LLM API Error for {original_filename} ---\n".encode('utf-8', 'replace'))
        # sys.stdout.buffer.write(error_message.encode('utf-8', 'replace'))
        # sys.stdout.buffer.write(b"\n--- END DEBUG: LLM API Error ---\n")
        # sys.stdout.flush()
        return error_message

def process_pdfs(pdf_dir_str, target_url, model_name, assembled_prompt, category_map_json, progress_callback=None):
    """
    Main processing function.
    progress_callback(data): data is a dict with keys:
        'original_filename', 'checksum', 'new_filename', 'status', 'target_folder', 'error_message'
    """
    PDF_DIR = pathlib.Path(pdf_dir_str)
    
    try:
        CATEGORY_MAP = json.loads(category_map_json)
    except json.JSONDecodeError as e:
        print(f"Fehler: Ungültiges JSON für Category Map: {e}")
        return

    MAX_RETRIES = 5 

    # Initialisiere den OpenAI-Client für LM Studio
    try:
        client = OpenAI(base_url=target_url, api_key="lm-studio") 
    except Exception as e:
        print(f"Fehler bei der Initialisierung des OpenAI-Clients: {e}")
        return

    OUTPUT_BASE_DIR = PDF_DIR
    OUTPUT_BASE_DIR.mkdir(exist_ok=True)

    if not PDF_DIR.is_dir():
        print(f"Fehler: '{PDF_DIR}' ist kein gültiges Verzeichnis.")
        return

    print(f"Starte Dateiumbenennung und -verschiebung mit Modell '{model_name}' in: {PDF_DIR}")
    print(f"Zielordner werden basierend auf Kategorien erstellt unter: {OUTPUT_BASE_DIR}")

    processed_files_count = 0
    pdf_files = list(PDF_DIR.glob("*.pdf"))
    total_files = len(pdf_files)

    for pdf_path in pdf_files:
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
        
        # 1. Generate Checksum
        try:
            checksum = generate_checksum(pdf_path)
        except Exception as e:
            error_message = f"Checksum error: {e}"
            if progress_callback:
                progress_callback({
                    "original_filename": original_filename,
                    "checksum": checksum,
                    "new_filename": "",
                    "status": "Error",
                    "target_folder": "",
                    "error_message": error_message
                })
            continue

        # 2. PDF Conversion
        try:
            doc = fitz.open(pdf_path)
            if doc.page_count == 0:
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
            if doc: doc.close()
            error_message = f"PDF conversion error: {e}"
            if progress_callback:
                progress_callback({
                    "original_filename": original_filename,
                    "checksum": checksum,
                    "new_filename": "",
                    "status": "Error",
                    "target_folder": "",
                    "error_message": error_message
                })
            continue

        # 3. LLM Call
        dynamic_prompt = assembled_prompt.format(original_filename=pdf_stem)
        model_output = analyze_image_with_lm_studio(client, model_name, base64_img, dynamic_prompt, original_filename)
        
        if model_output.startswith("LLM API Error:"):
            if doc: doc.close()
            error_message = model_output
            if progress_callback:
                progress_callback({
                    "original_filename": original_filename,
                    "checksum": checksum,
                    "new_filename": "",
                    "status": "Error",
                    "target_folder": "",
                    "error_message": error_message
                })
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
            if doc: doc.close()
            error_message = f"Parsing error: {ve}"
            if progress_callback:
                progress_callback({
                    "original_filename": original_filename,
                    "checksum": checksum,
                    "new_filename": "",
                    "status": "Error",
                    "target_folder": "",
                    "error_message": error_message
                })
            continue

        # 5. Validate filename format
        if not re.match(r'^\d{8}_.+', new_filename_base):
            if doc: doc.close()
            error_message = "Invalid filename format (expected YYYYMMDD_...)"
            if progress_callback:
                progress_callback({
                    "original_filename": original_filename,
                    "checksum": checksum,
                    "new_filename": new_filename_base,
                    "status": "Error",
                    "target_folder": "",
                    "error_message": error_message
                })
            continue

        final_filename_stem = f"{new_filename_base}_{checksum}"

        # 6. Determine target folder from CATEGORY_MAP
        target_dir_name = CATEGORY_MAP.get(category_name, CATEGORY_MAP.get('OTHER', 'OTHER'))
        TARGET_SUB_DIR = pathlib.Path(target_dir_name)
        TARGET_FULL_DIR = OUTPUT_BASE_DIR / TARGET_SUB_DIR
        
        try:
            TARGET_FULL_DIR.mkdir(parents=True, exist_ok=True)
            target_folder_display = TARGET_SUB_DIR.name
        except OSError as e:
            if doc: doc.close()
            error_message = f"Dir creation error: {e}"
            if progress_callback:
                progress_callback({
                    "original_filename": original_filename,
                    "checksum": checksum,
                    "new_filename": final_filename_stem,
                    "status": "Error",
                    "target_folder": "",
                    "error_message": error_message
                })
            continue

        # 7. Set status
        status = f"Success ({category_name})"

        # 8. Save with collision protection
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
        
        processed_files_count += 1
        if doc:
            doc.close()

        if progress_callback:
            progress_callback({
                "original_filename": original_filename,
                "checksum": checksum,
                "new_filename": new_filename_stem if saved else "",
                "status": status,
                "target_folder": target_folder_display,
                "error_message": error_message
            })

    print(f"\nVerarbeitung abgeschlossen. {processed_files_count} Dateien wurden analysiert.")

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("Fehler: Unzureichende Argumente. Erwartet: pdf_dir, target_url, model_name, assembled_prompt, category_map_json")
        sys.exit(1)

    def cli_callback(data):
        # Simple CLI output formatting
        print(f"{data['original_filename']} -> {data['status']} | {data['error_message']}")

    process_pdfs(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
        sys.argv[4],
        sys.argv[5],
        progress_callback=cli_callback
    )
