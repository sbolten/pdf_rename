import json
import os
import pathlib

class ConfigManager:
    def __init__(self, config_file="config.json"):
        self.config_file = pathlib.Path(config_file)
        self.default_config = {
            "pdf_dir": r"C:/Users/steph/Documents/dev/python_ai/pdf",
            "target_url": "http://127.0.0.1:1234/v1",
            "model_name": "qwen/qwen3-vl-4b", # Changed default model name
            "prompt_template": (
                "# 🤖 DOKUMENTEN-KLASSIFIZIERER: AUSGABEREGELN\n\n"
                "## ⚠️ ZWINGENDE AUSGABEANWEISUNG\n\n"
                "**DEINE EINZIGE UND AUSSCHLIESSLICHE AUFGABE IST ES, ZWEI INFORMATIONEN DURCH EIN PIPE-ZEICHEN ('|') GETRENNT AUSZUGEBEN.**\n\n"
                "DAS ZWINGENDE OUTPUT-FORMAT LAUTET:\n"
                "`DATEINAME|KATEGORIE1#KATEGORIE2#...`\n\n"
                "DU DARFST AUSSCHLIESSLICH DIESE BEIDEN INFORMATIONEN AUSGEBEN, OHNE JEDEN WEITEREN TEXT ODER KOMMENTAR. KEINE ERKLÄRUNGEN, KEINE BEGRÜSSUNGEN, NUR OUTPUT!\n\n"
                "---\n\n"
                "## 📝 REGELN\n\n"
                "### 1. DATEINAME FORMAT\n"
                "Das Format lautet: `YYYYMMDD_<inhalt>`\n"
                "* **INHALT:** Muss alle relevanten, kurzgefassten Stichworte (Namen, Betreff, Firma, Projekt, Art des Dokuments) enthalten. **Keine Füllwörter oder Redundanzen.**\n\n"
                "### 2. KATEGORIEN\n"
                "* Du darfst **EIN ODER MEHRERE** logische Kategorien wählen.\n"
                "* Mehrere Kategorien werden mit dem Zeichen **'#'** getrennt (z. B. `STEUER#VERSICHERUNG`).\n"
                "* Die Wahl jeder Kategorie muss **ZWINGEND** aus der Liste unten erfolgen.\n"
                "* Wenn keine Kategorie zutrifft, wähle **'OTHER'** als einzige Kategorie.\n\n"
                "---\n\n"
                "## 📋 VERFÜGBARE KATEGORIEN UND KRITERIEN\n\n"
                "### 1. **STEUER**\n"
                "Wähle STEUER, wenn das Dokument für die private Steuererklärung relevant ist (abzugsfähige Kosten oder deklarationspflichtiges Einkommen/Vermögen). (Basis: Kanton Zürich/ZH, Stockwerkeigentum).\n\n"
                "* **EXPLIZITE FORMULIERUNG:** Dokumente, die explizit die Phrase enthalten: „Diese Bescheinigung bitte für das Ausfüllen Ihrer Steuererklärung aufbewahren“ oder „ZUSAMMENSTELLUNG FÜR IHRE STEUERERKLÄRUNG“.\n"
                "* **Vermögen/Schulden:** Jahresend-Bescheinigungen (Kontosalden, Hypothekarsalden, Zinserträge, Schuldzinsen). *Stichworte: „Kontosaldo“, „Zinsen“, „Vermögensausweis“.*\n"
                "* **Einkommen & Vorsorge:** Lohnausweise, Beiträge zur gebundenen Vorsorge (Säule 3a), Rückkaufswerte (Säule 3b).\n"
                "* **Liegenschaftsunterhalt (Werterhalt):** Rechnungen für laufenden Unterhalt, Reparaturen (inkl. STWEG-Abrechnungen).\n"
                "* **Persönliche Abzüge:** Spenden, Beiträge an Berufsverbände, detaillierte Krankenversicherungs-Abrechnungen (Prämien, Franchise, Selbstbehalt).\n\n"
                "### 2. **RECHNUNGEN**\n"
                "* **KRITERIEN:** Zahlungsaufforderung oder Beleg für Konsum, der **keinen Steuervorteil** bietet. Allgemeine Konsumrechnungen, private Abonnements. **Wertvermehrende** Investitionen/Modernisierungen der Liegenschaft.\n\n"
                "### 3. **FINANZEN_ALLGEMEIN**\n"
                "* **KRITERIEN:** Finanzieller Bezug, aber **keine Steuerrelevanz** und **keine Konsumrechnung**. Amortisationspläne, nicht steuerrelevante Kontostände (z. B. Zwischenauszüge).\n\n"
                "### 4. **VERSICHERUNG**\n"
                "* **KRITERIEN:** Verträge, Policen oder allgemeine Korrespondenz zu Versicherungen, die **nicht** direkt eine steuerlich abzugsfähige Prämie betreffen. (Hausrat, Haftpflicht, Gebäude, Vertragsänderungen).\n\n"
                "### 5. **OTHER**\n"
                "* **KRITERIEN:** Dokumente ohne monetären Wert, steuerliche Relevanz oder klaren Bezug zu den anderen Kategorien (Fallengruppe). Einladungen, allgemeine Mails, leere oder irrelevante Dokumente.\n\n"
                "---\n\n"
                "## 💡 BEISPIELE (Zwingendes Output-Format)\n"
                "20240115_Bank_Vermögensausweis_Jahresende|STEUER\n"
                "20240320_Fitness_Abo_Rechnung|RECHNUNGEN\n"
                "20240228_Krankenversicherung_Jahresabrechnung|VERSICHERUNG#STEUER\n"
                "20240405_Bank_Amortisationsplan|FINANZEN_ALLGEMEIN#STEUER"
            ),
            # Neuer Prompt für zusätzliche Informationen
            "additional_prompt_template": (
                "Zusätzlich zu den oben genannten Regeln, beachte bitte folgende Punkte:\n"
                "* **Dokumenteninhalt:** Extrahiere relevante Details wie Namen, Daten, Beträge und spezifische Posten.\n"
                "* **Kontext:** Berücksichtige den ursprünglichen Dateinamen '{{original_filename}}' als zusätzlichen Hinweis auf den Inhalt.\n"
                "* **Sprache:** Die Ausgabe sollte auf Deutsch erfolgen, es sei denn, der Inhalt des Dokuments legt etwas anderes nahe."
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

    def update_config_from_gui(self, pdf_dir_input, target_url_input, model_name_combobox, prompt_input, additional_prompt_input):
        """Aktualisiert die interne Konfiguration basierend auf den GUI-Widgets."""
        self.config["pdf_dir"] = pdf_dir_input.text()
        self.config["target_url"] = target_url_input.text()
        # Hole den ausgewählten Modellnamen aus der ComboBox
        self.config["model_name"] = model_name_combobox.currentText()
        self.config["prompt_template"] = prompt_input.toPlainText()
        # Aktualisiere den zusätzlichen Prompt
        self.config["additional_prompt_template"] = additional_prompt_input.toPlainText()

    def apply_config_to_gui(self, pdf_dir_input, target_url_input, prompt_input, additional_prompt_input):
        """Wendet die geladene Konfiguration auf die GUI-Widgets an."""
        pdf_dir_input.setText(self.config.get("pdf_dir", self.default_config["pdf_dir"]))
        target_url_input.setText(self.config.get("target_url", self.default_config["target_url"]))
        # model_name_input wird nicht mehr benötigt, da wir eine ComboBox verwenden
        prompt_input.setPlainText(self.config.get("prompt_template", self.default_config["prompt_template"]))
        # Wende den zusätzlichen Prompt an
        additional_prompt_input.setPlainText(self.config.get("additional_prompt_template", self.default_config["additional_prompt_template"]))
