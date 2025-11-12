import sys
import os
import pathlib
import subprocess
import threading
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog,
    QTextEdit, QProgressBar
)
from PyQt6.QtCore import Qt, QProcess

class PDFProcessorGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Organizer & Renamer")
        self.setGeometry(100, 100, 800, 600)

        self.process = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # --- Verzeichnis Auswahl ---
        dir_layout = QHBoxLayout()
        self.dir_label = QLabel("PDF Verzeichnis:")
        self.dir_input = QLineEdit()
        # Setze das Standardverzeichnis hier
        default_pdf_dir = r"C:/Users/steph/Documents/dev/python_ai/pdf"
        self.dir_input.setText(default_pdf_dir)
        self.dir_input.setPlaceholderText("Wählen Sie ein Verzeichnis mit PDF-Dateien")
        self.browse_button = QPushButton("Durchsuchen...")
        self.browse_button.clicked.connect(self.browse_directory)
        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(self.browse_button)
        layout.addLayout(dir_layout)

        # --- Start Button ---
        self.start_button = QPushButton("Verarbeitung starten")
        self.start_button.clicked.connect(self.start_processing)
        # Aktiviert den Start-Button, wenn ein Verzeichnis (auch das Standard) vorhanden ist
        if os.path.isdir(self.dir_input.text()):
            self.start_button.setEnabled(True)
        else:
            self.start_button.setEnabled(False)
        layout.addWidget(self.start_button)

        # --- Fortschrittsanzeige ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False) # Zuerst versteckt
        layout.addWidget(self.progress_bar)

        # --- Output Anzeige ---
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText("Hier werden die Verarbeitungsergebnisse angezeigt...")
        layout.addWidget(self.output_text)

        self.setLayout(layout)

    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Wählen Sie das PDF-Verzeichnis")
        if directory:
            self.dir_input.setText(directory)
            self.start_button.setEnabled(True) # Aktiviert den Start-Button, wenn ein Verzeichnis ausgewählt wurde

    def start_processing(self):
        pdf_dir = self.dir_input.text()
        if not pdf_dir or not os.path.isdir(pdf_dir):
            self.output_text.append("<font color='red'>Fehler: Ungültiges Verzeichnis ausgewählt.</font>")
            return

        self.output_text.clear()
        self.output_text.append(f"<font color='blue'>Starte Verarbeitung für Verzeichnis: {pdf_dir}</font>")
        self.start_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

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

        self.process.start(sys.executable, [script_path, pdf_dir])

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace') # Fehlerbehandlung hinzugefügt
        # Füge jede Zeile einzeln hinzu, um die Formatierung zu erhalten
        lines = data.strip().split('\n')
        for line in lines:
            self.output_text.append(line)
            # Einfache Fortschrittsanzeige basierend auf Zeilenumbrüchen
            # Dies ist eine grobe Schätzung und kann verbessert werden
            if "--- Verarbeite PDF:" in line:
                self.progress_bar.setValue(self.progress_bar.value() + 1) # Erhöhe den Fortschritt für jede neue PDF-Verarbeitung

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
        self.browse_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = PDFProcessorGUI()
    gui.show()
    sys.exit(app.exec())
