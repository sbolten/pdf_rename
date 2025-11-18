import json
import os
import pathlib

class ConfigManager:
    def __init__(self, config_file="config.json"):
        self.config_file = pathlib.Path(config_file)
        self.default_config = {
            "pdf_dir": r"C:/Users/steph/Documents/dev/python_ai/pdf",
            "target_url": "http://127.0.0.1:1234/v1",
            "model_name": "qwen/qwen3-vl-4b",
            "window_geometry": [100, 100, 900, 800],
            "categories": [
                {
                    "name": "STEUER",
                    "directory": "STEUER",
                    "prompt": "Any document relevant for a private tax declaration in Switzerland (Canton of Zurich). This includes official tax forms, income statements, asset statements (year-end bank accounts), mortgage debt, 3a pension contributions, invoices for property maintenance (werterhaltend), professional expenses, donations, or detailed health cost statements.\n**Examples:** `Lohnausweis`, `Vermögensausweis`, `Hypothekarzinsabrechnung`, `Spendenbescheinigung`, `Handwerkerrechnung für Reparatur`.\n**➡️ If it's tax-relevant, always choose this category, even if it's also an invoice or insurance document.**",
                    "active": True
                },
                {
                    "name": "RECHNUNGEN",
                    "directory": "RECHNUNGEN",
                    "prompt": "Any invoice or bill that is **NOT** tax-deductible. This includes general consumption, services, or value-adding investments (wertvermehrend).\n**Examples:** `Handy-Rechnung`, `Bestellung bei Online-Shop`, `Rechnung für eine neue Küche`.",
                    "active": True
                },
                {
                    "name": "VERSICHERUNG",
                    "directory": "VERSICHERUNG",
                    "prompt": "Insurance policies, contracts, or general communication that is **NOT** a tax-relevant annual statement.\n**Examples:** `Versicherungspolice Hausrat`, `Vertragsänderung Autoversicherung`.",
                    "active": True
                },
                {
                    "name": "FINANZEN_ALLGEMEIN",
                    "directory": "FINANZEN_ALLGEMEIN",
                    "prompt": "Financial documents that are neither tax-relevant nor simple invoices.\n**Examples:** `Konto-Zwischenauszug`, `Amortisationsplan`, `Bank-Mitteilung`.",
                    "active": True
                },
                {
                    "name": "OTHER",
                    "directory": "OTHER",
                    "prompt": "Use this for any document that does not fit the other categories.\n**Examples:** `Werbung`, `Einladung`, `Allgemeine Korrespondenz`.",
                    "active": True
                }
            ],
            "base_prompt_template": (
                "# 🤖 AI PDF ORGANIZER - STRICT OUTPUT FORMAT\n\n"
                "## ⚠️ YOUR TASK\n"
                "Your only task is to output a single line of text with two parts separated by a pipe character (`|`). Do not add any explanation or extra text.\n\n"
                "**FORMAT:** `YYYYMMDD_description|CATEGORY_NAME`\n\n"
                "---\n\n"
                "## 📜 RULES\n\n"
                "### 1. FILENAME (`YYYYMMDD_description`)\n"
                "- **Date:** Start with the document's date. If no date is found, use `19700101`.\n"
                "- **Description:** A short, clean description using keywords from the document (e.g., company, subject, person). Use underscores `_` instead of spaces.\n\n"
                "### 2. CATEGORY\n"
                "You **MUST** choose exactly **ONE** category name from the list below. Use the specified hierarchy to decide if multiple categories seem to apply (highest in the list wins).\n\n"
                "---\n\n"
                "## 📋 CATEGORIES (Choose ONE)\n\n"
                "{{category_definitions}}\n\n"
                "---\n\n"
                "## ✅ EXAMPLES OF VALID OUTPUT\n\n"
                "`20240115_ubs_vermoegensausweis_jahresende|STEUER`\n"
                "`20240320_digitec_rechnung_maus|RECHNUNGEN`\n"
                "`20250101_einladung_generalversammlung|OTHER`\n\n"
                "---\n"
                "Original Filename Hint: `{{original_filename}}`"
            )
        }
        self.config = self.load_config()

    def load_config(self):
        """Lädt die Konfiguration aus der JSON-Datei. Gibt Standardwerte zurück, wenn die Datei nicht existiert."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # Füge fehlende Schlüssel mit Standardwerten hinzu
                    for key, value in self.default_config.items():
                        if key not in loaded_config:
                            loaded_config[key] = value
                    
                    # Ensure categories is a list and items have an 'active' key
                    if "categories" not in loaded_config or not isinstance(loaded_config["categories"], list):
                        loaded_config["categories"] = self.default_config["categories"]
                    else:
                        for category in loaded_config["categories"]:
                            if "active" not in category:
                                category["active"] = True # Default to active for old configs
                                
                    return loaded_config
            except (json.JSONDecodeError, IOError) as e:
                print(f"Fehler beim Laden der Konfiguration '{self.config_file}': {e}. Verwende Standardwerte.")
                return self.default_config.copy()
        else:
            print(f"Konfigurationsdatei '{self.config_file}' nicht gefunden. Verwende Standardwerte.")
            return self.default_config.copy()

    def save_config(self, config_data: dict):
        """Speichert die aktuelle Konfiguration in die JSON-Datei."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            print(f"Konfiguration erfolgreich gespeichert in '{self.config_file}'.")
            return True
        except IOError as e:
            print(f"Fehler beim Speichern der Konfiguration '{self.config_file}': {e}")
            return False

    def get_default_config(self):
        """Gibt eine Kopie der Standardkonfiguration zurück."""
        return self.default_config.copy()

    def get_current_config(self):
        """Gibt die aktuell geladene Konfiguration zurück."""
        return self.config.copy()
