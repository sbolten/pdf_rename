import sys
import os
import pathlib
import subprocess
import threading
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog,
    QTextEdit, QProgressBar, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt, QProcess

class PDFProcessorGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Organizer & Renamer")
        self.setGeometry(100, 100, 800, 700) # Erhöhte Höhe für den neuen Bereich

        self.process = None
        self.total_pdfs = 0
        self.processed_pdfs = 0
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # --- Konfigurationsbereich ---
        config_group_box = QGroupBox("Konfiguration")
        config_layout = QFormLayout()

        self.pdf_dir_label = QLabel("PDF Verzeichnis:")
        self.pdf_dir_input = QLineEdit()
        default_pdf_dir = r"C:/Users/steph/Documents/dev/python_ai/pdf"
        self.pdf_dir_input.setText(default_pdf_dir)
        self.pdf_dir_input.setPlaceholderText("Wählen Sie ein Verzeichnis mit PDF-Dateien")
        self.browse_pdf_dir_button = QPushButton("Durchsuchen...")
        self.browse_pdf_dir_button.clicked.connect(self.browse_directory)
        
        config_layout.addRow(self.pdf_dir_label, self.pdf_dir_input, self.browse_pdf_dir_button)

        self.target_url_label = QLabel("Target URL:")
        self.target_url_input = QLineEdit()
        self.target_url_input.setText("http://127.0.0.1:1234/v1") # Standardwert
        self.target_url_input.setPlaceholderText("URL des LLM-Servers")
        config_layout.addRow(self.target_url_label, self.target_url_input)

        self.model_name_label = QLabel("Modellname:")
        self.model_name_input = QLineEdit()
        self.model_name_input.setText("Qwen/Qwen3-V1-8B") # Standardwert
        self.model_name_input.setPlaceholderText("Name des zu verwendenden LLM-Modells")
        config_layout.addRow(self.model_name_label, self.model_name_input)

        self.prompt_label = QLabel("Prompt Vorlage:")
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Vorlage für den Prompt an das LLM")
        self.prompt_input.setFixedHeight(100) # Feste Höhe für das Textfeld
        # Standard-Prompt (kann angepasst werden)
        self.prompt_input.setText(
            "Analysiere dieses Dokument. Der ursprüngliche Dateiname war: "
            f"'{{original_filename}}'. Nutze diesen Namen als zusätzlichen Hinweis. "
            "Deine einzige Aufgabe ist es, ZWEI Informationen durch ein Pipe-Zeichen '|' getrennt auszugeben: "
            "1. Den Dateinamen im Format 'YYYYMMDD_<inhalt>' mit detailliertem Kontext (Namen, Betreff, Firma, Projekt, etc.). "
            "2. Einen Steuermarker. Entscheide basierend auf den Schweizer Kriterien für Privatpersonen mit Stockwerkeigentum (z.B. berufsbedingte Kosten, Kinderbetreuungskosten, Schuldzinsen, Unterhaltskosten für die Liegenschaft, 3a-Vorsorgebeiträge), ob das Dokument für die Steuererklärung relevant ist. Gib 'STEUER_JA' oder 'STEUER_NEIN' aus. "
            "Du darfst NUR diese beiden Informationen, durch das Pipe-Zeichen getrennt, ausgeben, keine Erklärung. "
            "Beispielausgabe: 20240315_Hauswartrechnung_Stockwerkeigentum_Mai|STEUER_JA"
        )
        config_layout.addRow(self.prompt_label, self.prompt_input)

        config_group_box.setLayout(config_layout)
        main_layout.addWidget(config_group_box)

        # --- Start Button ---
        self.start_button = QPushButton("Verarbeitung starten")
        self.start_button.clicked.connect(self.start_processing)
        # Aktiviert den Start-Button, wenn ein Verzeichnis (auch das Standard) vorhanden ist
        if os.path.isdir(self.pdf_dir_input.text()):
            self.start_button.setEnabled(True)
        else:
            self.start_button.setEnabled(False)
        main_layout.addWidget(self.start_button)

        # --- Fortschrittsanzeige ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False) # Zuerst versteckt
        main_layout.addWidget(self.progress_bar)

        # --- Output Anzeige ---
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText("Hier werden die Verarbeitungsergebnisse angezeigt...")
        main_layout.addWidget(self.output_text)

        self.setLayout(main_layout)

    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Wählen Sie das PDF-Verzeichnis")
        if directory:
            self.pdf_dir_input.setText(directory)
            # Überprüfe, ob das Verzeichnis existiert, bevor der Start-Button aktiviert wird
            if os.path.isdir(directory):
                self.start_button.setEnabled(True)
            else:
                self.start_button.setEnabled(False)

    def start_processing(self):
        pdf_dir = self.pdf_dir_input.text()
        target_url = self.target_url_input.text()
        model_name = self.model_name_input.text()
        prompt_template = self.prompt_input.toPlainText()

        if not pdf_dir or not os.path.isdir(pdf_dir):
            self.output_text.append("<font color='red'>Fehler: Ungültiges PDF-Verzeichnis ausgewählt.</font>")
            return
        if not target_url:
            self.output_text.append("<font color='red'>Fehler: Target URL darf nicht leer sein.</font>")
            return
        if not model_name:
            self.output_text.append("<font color='red'>Fehler: Modellname darf nicht leer sein.</font>")
            return
        if not prompt_template:
            self.output_text.append("<font color='red'>Fehler: Prompt-Vorlage darf nicht leer sein.</font>")
            return

        self.output_text.clear()
        self.output_text.append(f"<font color='blue'>Starte Verarbeitung für Verzeichnis: {pdf_dir}</font>")
        self.output_text.append(f"<font color='blue'>Target URL: {target_url}</font>")
        self.output_text.append(f"<font color='blue'>Modell: {model_name}</font>")

        self.start_button.setEnabled(False)
        self.browse_pdf_dir_button.setEnabled(False)
        self.target_url_input.setEnabled(False)
        self.model_name_input.setEnabled(False)
        self.prompt_input.setEnabled(False)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # Ermittle die Gesamtzahl der PDFs im Verzeichnis
        try:
            pdf_files = list(pathlib.Path(pdf_dir).glob("*.pdf"))
            self.total_pdfs = len(pdf_files)
            if self.total_pdfs == 0:
                self.output_text.append("<font color='orange'>Warnung: Keine PDF-Dateien im ausgewählten Verzeichnis gefunden.</font>")
                self.reset_ui()
                return
            self.progress_bar.setMaximum(self.total_pdfs)
            self.processed_pdfs = 0 # Setze den Zähler zurück
        except Exception as e:
            self.output_text.append(f"<font color='red'>Fehler beim Zählen der PDF-Dateien: {e}</font>")
            self.reset_ui()
            return

        # Führe das pdf.py Skript in einem separaten Prozess aus
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.handle_process_finished)

        # Stelle sicher, dass pdf.py im selben Verzeichnis wie dieses GUI-Skript liegt oder gib den vollen Pfad an
        script_path = os.path.join(os.path.dirname(__file__), "pdf.py")
        if not os.path.exists(script_path):
            self.output_text.append(f"<font color='red'>Fehler: pdf.py Skript nicht gefunden unter {script_path}</font>")
            self.reset_ui()
            return

        # Setze PYTHONUNBUFFERED=1, um die Ausgabe sofort zu erhalten
        os.environ["PYTHONUNBUFFERED"] = "1"

        # Passe das Skript an, um die Konfigurationsparameter zu übergeben
        # Wir übergeben sie als Kommandozeilenargumente
        command = [
            sys.executable,
            script_path,
            pdf_dir,
            target_url,
            model_name,
            prompt_template # Prompt wird als einzelnes Argument übergeben
        ]
        self.process.start(command[0], command[1:])

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace') # Fehlerbehandlung hinzugefügt
        # Füge jede Zeile einzeln hinzu, um die Formatierung zu erhalten
        lines = data.strip().split('\n')
        for line in lines:
            self.output_text.append(line)
            # Aktualisiere den Fortschrittsbalken, wenn eine neue PDF-Verarbeitung beginnt
            if "--- Verarbeite PDF:" in line:
                self.processed_pdfs += 1
                self.progress_bar.setValue(self.processed_pdfs)

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode('utf-8', errors='replace') # Fehlerbehandlung hinzugefügt
        self.output_text.append(f"<font color='red'>{data.strip()}</font>")

    def handle_process_finished(self, exit_code, exit_status):
        if exit_status == QProcess.ExitStatus.NormalExit:
            self.output_text.append("<font color='green'>✅ Verarbeitung abgeschlossen.</font>")
        else:
            self.output_text.append(f"<font color='red'>❌ Verarbeitung mit Fehler beendet. Exit Code: {exit_code}</font>")
        self.reset_ui()

    def reset_ui(self):
        self.start_button.setEnabled(True)
        self.browse_pdf_dir_button.setEnabled(True)
        self.target_url_input.setEnabled(True)
        self.model_name_input.setEnabled(True)
        self.prompt_input.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.total_pdfs = 0
        self.processed_pdfs = 0

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = PDFProcessorGUI()
    gui.show()
    sys.exit(app.exec())
