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
                "Ziel: Analysiere dieses Dokument. Deine einzige und ausschliessliche Aufgabe ist es, ZWEI Informationen durch ein Pipe-Zeichen '|' getrennt auszugeben. Du darfst AUSSCHLIESSLICH diese beiden Informationen ausgeben, ohne jeden weiteren Text oder Kommentar. Jeder weitere Text, Kommentar oder Erklärung führt zur Nichtbeachtung der Antwort.\n\n"
                "1. **Dateiname:** Im Format **'YYYYMMDD_<KATEGORIE>_<inhalt>'**.\n"
                "    * Die **KATEGORIE** muss zwingend aus dieser Liste gewählt werden und das Dokument in die relevanteste Gruppe einordnen:\n"
                "        * **STEUER_FINANZEN:** Kontosalden, Hypotheken, Zinsen, Säule 3a/2, Vermögensausweise.\n"
                "        * **STEUER_EINKOMMEN:** Lohnausweise, Taggelder, Erwerbsersatz.\n"
                "        * **STEUER_LIEGENSCHAFT:** Werterhaltende Unterhaltsrechnungen, STWEG-Abrechnungen, Verwaltungskosten, Versicherungen zur Liegenschaft.\n"
                "        * **STEUER_PERSOENLICH:** Spenden, Berufsverbände, Kranken-/Unfallkosten (Arztrechnungen, Franchisenabrechnungen).\n"
                "        * **PRIVAT_KONSUM:** Rechnungen ohne steuerliche Relevanz, Abonnements, private Ausbildungskosten, wertvermehrende Investitionen (siehe STEUER_NEIN).\n"
                "    * Der Inhalt muss alle relevanten, kurzgefassten Stichworte (Namen, Betreff, Firma, Projekt, Art des Dokuments) enthalten und darf keine Füllwörter oder Redundanzen nutzen.\n\n"
                "2. **Steuermarker:** Entscheide basierend auf den Schweizer Steuerkriterien für Privatpersonen (Kanton Zürich/ZH) mit Stockwerkeigentum, ob die Kosten oder der Sachverhalt für die private Steuererklärung abzugsfähig oder deklarationspflichtig ist.\n"
                "    * **STEUER_JA gilt für:**\n"
                "        * EXPLIZITE FORMULIERUNG: Dokumente, die explizit die Phrase enthalten: 'Diese Bescheinigung bitte für das Ausfüllen Ihrer Steuererklärung aufbewahren' oder 'ZUSAMMENSTELLUNG FÜR IHRE STEUERERKLÄRUNG'.\n"
                "        * Vermögen/Schulden: Alle Jahresend-Bescheinigungen, die Kontosalden, Hypothekarsalden, Zinserträge oder Schuldzinsen belegen. Stichworte: 'Kontosaldo per 31.12.2024', 'Saldo Festhypothek', 'Zinsen', 'Habenzinsen', 'Vermögensausweis'.\n"
                "        * Einkommen & Vorsorge: Lohnausweise (Einkommensdeklaration), Bescheinigungen über Beiträge zur gebundenen Vorsorge (Säule 3a), Rückkaufswerte aus Freier Vorsorge (Säule 3b).\n"
                "        * Liegenschaftsunterhalt (Werterhalt): Rechnungen für laufenden Unterhalt, Reparaturen oder Ersatz. Stichworte: 'Heizkörper kontrolliert', 'Winterschnitt', 'Pflanzenschutz', 'Malerarbeiten (Innen)', 'Unterhalt' (inkl. STWEG-Abrechnungen).\n"
                "        * Persönliche Abzüge: Freiwillige Spenden/Zuwendungen an anerkannte gemeinnützige Organisationen, Beiträge an Berufsverbände, sowie detaillierte Abrechnungen der Krankenversicherung, die Prämien, Franchise, Selbstbehalt und nicht versicherte Kosten ausweisen.\n"
                "    * **STEUER_NEIN gilt für:**\n"
                "        * Investitionen: Wertvermehrende Investitionen/Modernisierungen (z.B. Installation einer Ladestation für E-Mobilität), Amortisationen der Hypothek.\n"
                "        * Konsum/Privat: Allgemeine private Konsumrechnungen, Abonnements oder private Dienstleistungen (z.B. Entsorgungs-Abonnement), sowie private Ausbildungskosten (Schulbestätigungen KME).\n"
                "        * Leere/Irrelevante Dokumente: Dokumente, die keinen Inhalt aufweisen oder deren Natur keinen steuerlichen Bezug hat.\n"
                "3. Gib 'STEUER_JA' oder 'STEUER_NEIN' aus.\n\n"
                "**Beispielausgabe:** `20240503_STEUER_LIEGENSCHAFT_Rechnung_Gobbo_Malerarbeiten_Wohnung|STEUER_JA`"
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
