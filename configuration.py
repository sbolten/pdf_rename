import json
import os
import pathlib

class ConfigManager:
    def __init__(self, config_file="config.json"):
        self.config_file = pathlib.Path(config_file)
        self.default_config = {
            "pdf_dir": r"C:/Users/steph/Documents/dev/python_ai/pdf",
            "target_url": "http://127.0.0.1:1234/v1",
            "model_name": "Qwen/Qwen3-V1-8B",
            "prompt_template": (
                "Analysiere dieses Dokument. Der ursprüngliche Dateiname war: "
                f"'{{original_filename}}'. Nutze diesen Namen als zusätzlichen Hinweis. "
                "Deine einzige Aufgabe ist es, ZWEI Informationen durch ein Pipe-Zeichen '|' getrennt auszugeben: "
                "1. Den Dateinamen im Format 'YYYYMMDD_<inhalt>' mit detailliertem Kontext (Namen, Betreff, Firma, Projekt, etc.). "
                "2. Einen Steuermarker. Entscheide basierend auf den Schweizer Kriterien für Privatpersonen mit Stockwerkeigentum (z.B. berufsbedingte Kosten, Kinderbetreuungskosten, Schuldzinsen, Unterhaltskosten für die Liegenschaft, 3a-Vorsorgebeiträge), ob das Dokument für die Steuererklärung relevant ist. Gib 'STEUER_JA' oder 'STEUER_NEIN' aus. "
                "Du darfst NUR diese beiden Informationen, durch das Pipe-Zeichen getrennt, ausgeben, keine Erklärung. "
                "Beispielausgabe: 20240315_Hauswartrechnung_Stockwerkeigentum_Mai|STEUER_JA"
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

    def update_config_from_gui(self, pdf_dir_input, target_url_input, model_name_combobox, prompt_input):
        """Aktualisiert die interne Konfiguration basierend auf den GUI-Widgets."""
        self.config["pdf_dir"] = pdf_dir_input.text()
        self.config["target_url"] = target_url_input.text()
        # Hole den ausgewählten Modellnamen aus der ComboBox
        self.config["model_name"] = model_name_combobox.currentText()
        self.config["prompt_template"] = prompt_input.toPlainText()

    def apply_config_to_gui(self, pdf_dir_input, target_url_input, prompt_input):
        """Wendet die geladene Konfiguration auf die GUI-Widgets an."""
        pdf_dir_input.setText(self.config.get("pdf_dir", self.default_config["pdf_dir"]))
        target_url_input.setText(self.config.get("target_url", self.default_config["target_url"]))
        # model_name_input wird nicht mehr benötigt, da wir eine ComboBox verwenden
        prompt_input.setPlainText(self.config.get("prompt_template", self.default_config["prompt_template"]))
