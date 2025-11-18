import sys
import os
import pathlib
import json
import requests
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QFileDialog, QGroupBox, QFormLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QScrollArea, QFrame, QMainWindow, QPushButton, QLabel,

    QLineEdit, QTextEdit, QComboBox, QCheckBox, QProgressBar
)
from PyQt6.QtCore import Qt, QProcess, QPoint
from PyQt6.QtGui import QIcon

from configuration import ConfigManager

class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        self.setFixedHeight(40)
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(0)

        self.title = QLabel("PDF Organizer & Renamer")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet("color: #000000; font-size: 16px; font-weight: bold;")

        self.minimize_button = QPushButton("-")
        self.maximize_button = QPushButton("[]")
        self.close_button = QPushButton("X")

        for btn, text in [(self.minimize_button, "_"), (self.maximize_button, "[]"), (self.close_button, "X")]:
            btn.setFixedSize(40, 40)
            btn.setStyleSheet("""
                QPushButton {{ 
                    border: none;
                    background-color: transparent;
                    font-size: 16px;
                    color: #000000;
                }}
                QPushButton:hover {{ 
                    background-color: #d0d0d0;
                }}
                QPushButton:pressed {{ 
                    background-color: #a0a0a0;
                }}
            """)
        
        self.close_button.setStyleSheet("""
            QPushButton {{ 
                border: none;
                background-color: transparent;
                font-size: 16px;
                color: #000000;
            }}
            QPushButton:hover {{ 
                background-color: #e81123;
                color: #ffffff;
            }}
            QPushButton:pressed {{ 
                background-color: #a00000;
                color: #ffffff;
            }}
        """)


        layout.addWidget(self.title)
        layout.addStretch()
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

        self.setLayout(layout)

        self.minimize_button.clicked.connect(self.parent.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximize_restore)
        self.close_button.clicked.connect(self.parent.close)

    def toggle_maximize_restore(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()

    def mousePressEvent(self, event):
        self.parent.oldPos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        delta = QPoint(event.globalPosition().toPoint() - self.parent.oldPos)
        self.parent.move(self.parent.x() + delta.x(), self.parent.y() + delta.y())
        self.parent.oldPos = event.globalPosition().toPoint()

class CategoryWidget(QWidget):
    """A widget to hold the configuration for a single category."""
    def __init__(self, name="", directory="", prompt="", active=True, parent=None):
        super().__init__(parent)
        self.init_ui(name, directory, prompt, active)

    def init_ui(self, name, directory, prompt, active):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        group_box = QGroupBox("Kategorie")
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setContentsMargins(15, 15, 15, 15)

        # Action buttons layout
        action_layout = QHBoxLayout()
        self.active_checkbox = QCheckBox("Aktiv", self)
        self.active_checkbox.setChecked(active)
        self.remove_button = QPushButton("Entfernen", self)
        action_layout.addWidget(self.active_checkbox)
        action_layout.addStretch()
        action_layout.addWidget(self.remove_button)

        form_layout.addRow(action_layout)
        
        self.name_input = QLineEdit(name, self)
        self.name_input.setPlaceholderText("Name der Kategorie (z.B. STEUER)")
        form_layout.addRow("Name:", self.name_input)

        self.directory_input = QLineEdit(directory, self)
        self.directory_input.setPlaceholderText("Zielverzeichnis (z.B. Steuerunterlagen)")
        form_layout.addRow("Verzeichnis:", self.directory_input)

        self.prompt_input = QTextEdit(prompt, self)
        self.prompt_input.setPlaceholderText("Prompt-Kriterien für diese Kategorie...")
        self.prompt_input.setFixedHeight(80)
        form_layout.addRow("Prompt:", self.prompt_input)

        group_box.setLayout(form_layout)
        layout.addWidget(group_box)
        self.setLayout(layout)

        # Make the 'OTHER' category non-removable and always active
        if name.upper() == 'OTHER':
            self.active_checkbox.setChecked(True)
            self.active_checkbox.setEnabled(False)
            self.remove_button.setEnabled(False)
            self.name_input.setReadOnly(True)

class MainContentWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.total_pdfs = 0
        self.processed_pdfs = 0
        
        self.config_manager = ConfigManager()
        
        self.init_ui()
        self.load_initial_config()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # --- Top Container for all configuration ---
        config_container = QWidget()
        top_layout = QVBoxLayout(config_container)
        top_layout.setSpacing(15)

        # --- Top-level configuration ---
        config_group_box = QGroupBox("Allgemeine Konfiguration")
        config_layout = QFormLayout()
        config_layout.setSpacing(10)
        config_layout.setContentsMargins(15, 15, 15, 15)
        
        pdf_dir_row_layout = QHBoxLayout()
        self.pdf_dir_input = QLineEdit(self)
        self.browse_pdf_dir_button = QPushButton("Durchsuchen...", self)
        self.browse_pdf_dir_button.clicked.connect(self.browse_directory)
        pdf_dir_row_layout.addWidget(self.pdf_dir_input)
        pdf_dir_row_layout.addWidget(self.browse_pdf_dir_button)
        config_layout.addRow("PDF Verzeichnis:", pdf_dir_row_layout)

        self.target_url_input = QLineEdit(self)
        config_layout.addRow("Target URL:", self.target_url_input)

        model_row_layout = QHBoxLayout()
        self.model_name_combobox = QComboBox(self)
        self.fetch_models_button = QPushButton("Modelle laden", self)
        self.fetch_models_button.clicked.connect(self.fetch_lm_studio_models)
        model_row_layout.addWidget(self.model_name_combobox)
        model_row_layout.addWidget(self.fetch_models_button)
        config_layout.addRow("Modellname:", model_row_layout)
        
        config_group_box.setLayout(config_layout)
        top_layout.addWidget(config_group_box)

        # --- Base Prompt Template Section ---
        base_prompt_group_box = QGroupBox("Base Prompt Vorlage")
        base_prompt_layout = QVBoxLayout()
        base_prompt_layout.setContentsMargins(15, 15, 15, 15)
        self.base_prompt_input = QTextEdit(self)
        self.base_prompt_input.setPlaceholderText("Die Basis-Vorlage für den Prompt...")
        base_prompt_layout.addWidget(self.base_prompt_input)
        base_prompt_group_box.setLayout(base_prompt_layout)
        top_layout.addWidget(base_prompt_group_box)

        # --- Dynamic Categories Section (Accordion Style) ---
        self.toggle_categories_button = QPushButton("Dynamische Kategorien ▼", self)
        self.toggle_categories_button.setObjectName("toggle_categories_button")
        self.toggle_categories_button.clicked.connect(self.toggle_categories_section)
        top_layout.addWidget(self.toggle_categories_button)

        self.categories_container = QWidget(self)
        categories_content_layout = QVBoxLayout(self.categories_container)
        categories_content_layout.setContentsMargins(0, 0, 0, 0)
        categories_content_layout.setSpacing(10)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_content_widget = QWidget(self)
        self.categories_layout = QVBoxLayout(scroll_content_widget)
        self.categories_layout.setSpacing(10)
        scroll_area.setWidget(scroll_content_widget)
        self.add_category_button = QPushButton("Neue Kategorie hinzufügen", self)
        self.add_category_button.clicked.connect(lambda: self.add_category_widget())
        categories_content_layout.addWidget(scroll_area)
        categories_content_layout.addWidget(self.add_category_button)
        top_layout.addWidget(self.categories_container)
        self.categories_container.setVisible(False)

        # --- Buttons and Progress Bar ---
        config_buttons_layout = QHBoxLayout()
        config_buttons_layout.setSpacing(10)
        self.save_config_button = QPushButton("Konfiguration speichern", self)
        self.save_config_button.clicked.connect(self.save_current_config)
        self.load_config_button = QPushButton("Konfiguration laden", self)
        self.load_config_button.clicked.connect(self.load_config_from_file)
        self.reset_config_button = QPushButton("Auf Standard zurücksetzen", self)
        self.reset_config_button.clicked.connect(self.reset_config_to_default)
        config_buttons_layout.addWidget(self.save_config_button)
        config_buttons_layout.addWidget(self.load_config_button)
        config_buttons_layout.addWidget(self.reset_config_button)
        top_layout.addLayout(config_buttons_layout)

        action_buttons_layout = QHBoxLayout()
        action_buttons_layout.setSpacing(10)
        self.start_button = QPushButton("Verarbeitung starten", self)
        self.start_button.clicked.connect(self.start_processing)
        self.cancel_button = QPushButton("Verarbeitung abbrechen", self)
        self.cancel_button.clicked.connect(self.cancel_processing)
        self.cancel_button.setEnabled(False)
        action_buttons_layout.addWidget(self.start_button)
        action_buttons_layout.addWidget(self.cancel_button)
        top_layout.addLayout(action_buttons_layout)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        top_layout.addWidget(self.progress_bar)
        
        top_layout.addStretch() # Pushes content up

        # --- Bottom Container for Results ---
        results_splitter = QSplitter(Qt.Orientation.Vertical)
        self.info_group_box = QGroupBox("Verarbeitungsinformationen")
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(15, 15, 15, 15)
        info_layout.setSpacing(10)
        self.model_info_label = QLabel("Modell: N/A", self)
        self.target_url_info_label = QLabel("Target URL: N/A", self)
        self.status_info_label = QLabel("Status: Idle", self)
        info_layout.addWidget(self.model_info_label)
        info_layout.addWidget(self.target_url_info_label)
        info_layout.addWidget(self.status_info_label)
        self.info_group_box.setLayout(info_layout)

        self.results_group_box = QGroupBox("Verarbeitungsergebnisse")
        results_layout = QVBoxLayout()
        results_layout.setContentsMargins(15, 15, 15, 15)
        self.output_table = QTableWidget(self)
        self.output_table.setColumnCount(6)
        self.output_table.setHorizontalHeaderLabels(["Original Filename", "Checksum", "New Filename", "Status", "Target Folder", "Error Message"])
        results_layout.addWidget(self.output_table)
        self.results_group_box.setLayout(results_layout)

        results_splitter.addWidget(self.results_group_box)
        results_splitter.addWidget(self.info_group_box)

        # --- Add containers to main splitter ---
        main_splitter.addWidget(config_container)
        main_splitter.addWidget(results_splitter)
        main_splitter.setSizes([500, 300]) # Initial size distribution
        results_splitter.setSizes([200, 100])

        main_layout.addWidget(main_splitter)

    def get_window_geometry(self):
        """Gets the main window geometry."""
        # The main window is the top-level window
        main_window = self.window()
        if main_window:
            geom = main_window.geometry()
            return [geom.x(), geom.y(), geom.width(), geom.height()]
        return None

    def toggle_categories_section(self):
        """Expands or collapses the dynamic categories section."""
        is_visible = self.categories_container.isVisible()
        self.categories_container.setVisible(not is_visible)
        if is_visible:
            self.toggle_categories_button.setText("Dynamische Kategorien ▼")
        else:
            self.toggle_categories_button.setText("Dynamische Kategorien ▲")

    def add_category_widget(self, name="", directory="", prompt="", active=True):
        """Adds a new category widget to the layout."""
        category_widget = CategoryWidget(name, directory, prompt, active)
        category_widget.remove_button.clicked.connect(lambda: self.remove_category_widget(category_widget))
        self.categories_layout.addWidget(category_widget)

    def remove_category_widget(self, widget):
        """Removes a category widget from the layout."""
        self.categories_layout.removeWidget(widget)
        widget.deleteLater()

    def _read_config_from_gui(self):
        """Reads the entire configuration from the UI fields."""
        config = {
            "pdf_dir": self.pdf_dir_input.text(),
            "target_url": self.target_url_input.text(),
            "model_name": self.model_name_combobox.currentText(),
            "categories": [],
            "base_prompt_template": self.base_prompt_input.toPlainText()
        }
        for i in range(self.categories_layout.count()):
            widget = self.categories_layout.itemAt(i).widget()
            if isinstance(widget, CategoryWidget):
                config["categories"].append({
                    "name": widget.name_input.text(),
                    "directory": widget.directory_input.text(),
                    "prompt": widget.prompt_input.toPlainText(),
                    "active": widget.active_checkbox.isChecked()
                })
        return config

    def _apply_config_to_gui(self, config):
        """Applies a configuration dictionary to the GUI."""
        self.pdf_dir_input.setText(config.get("pdf_dir", ""))
        self.target_url_input.setText(config.get("target_url", ""))
        self.base_prompt_input.setPlainText(config.get("base_prompt_template", ""))
        
        model_name = config.get("model_name", "")
        if model_name:
            if self.model_name_combobox.findText(model_name) == -1:
                self.model_name_combobox.addItem(model_name)
            self.model_name_combobox.setCurrentText(model_name)

        while self.categories_layout.count() > 0:
            widget = self.categories_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        
        for category in config.get("categories", []):
            self.add_category_widget(
                name=category.get("name", ""),
                directory=category.get("directory", ""),
                prompt=category.get("prompt", ""),
                active=category.get("active", True)
            )
        
        self.update_info_labels()
        if os.path.isdir(self.pdf_dir_input.text()):
            self.start_button.setEnabled(True)
        else:
            self.start_button.setEnabled(False)

    def load_initial_config(self):
        """Loads the configuration on application start."""
        self.config_manager.load_config()
        self._apply_config_to_gui(self.config_manager.get_current_config())
        
        # Apply window geometry from config
        geometry = self.config_manager.get_current_config().get("window_geometry")
        if isinstance(geometry, list) and len(geometry) == 4:
            self.window().setGeometry(geometry[0], geometry[1], geometry[2], geometry[3])

        if self.target_url_input.text():
            self.fetch_lm_studio_models()

    def save_current_config(self):
        """Saves the current GUI state to the config file."""
        current_config = self._read_config_from_gui()
        
        # Get window geometry and add it to the config
        geom = self.get_window_geometry()
        if geom:
            current_config["window_geometry"] = geom

        if self.config_manager.save_config(current_config):
            self.add_log_message("<font color='green'>Konfiguration erfolgreich gespeichert.</font>")
        else:
            self.add_log_message("<font color='red'>Fehler beim Speichern der Konfiguration.</font>")

    def load_config_from_file(self):
        """Loads the configuration from the file and applies it to the GUI."""
        self.config_manager.load_config()
        self._apply_config_to_gui(self.config_manager.get_current_config())
        self.add_log_message("<font color='blue'>Konfiguration geladen.</font>")

    def reset_config_to_default(self):
        """Resets the GUI to the default configuration."""
        default_config = self.config_manager.get_default_config()
        self._apply_config_to_gui(default_config)
        self.add_log_message("<font color='blue'>Konfiguration auf Standardwerte zurückgesetzt.</font>")

    def start_processing(self):
        """Starts the PDF processing script."""
        current_config = self._read_config_from_gui()
        
        pdf_dir = current_config.get("pdf_dir")
        target_url = current_config.get("target_url")
        model_name = current_config.get("model_name")
        all_categories = current_config.get("categories", [])
        base_template = current_config.get("base_prompt_template")

        if not all([pdf_dir, target_url, model_name, base_template]):
            self.add_log_message("<font color='red'>Fehler: Bitte füllen Sie die allgemeinen Konfigurationsfelder und die Base Prompt Vorlage aus.</font>")
            return

        valid_active_categories = [
            cat for cat in all_categories 
            if cat.get("active", False) and cat.get("name", "").strip() and cat.get("directory", "").strip()
        ]

        if not valid_active_categories:
            self.add_log_message("<font color='red'>Fehler: Es muss mindestens eine aktive Kategorie mit ausgefülltem Namen und Verzeichnis vorhanden sein.</font>")
            return
        
        category_definitions = [f"### {i+1}. {cat['name']}\n{cat['prompt']}" for i, cat in enumerate(valid_active_categories)]
        assembled_prompt = base_template.replace("{{category_definitions}}", "\n\n".join(category_definitions))
        category_map = {cat['name']: cat['directory'] for cat in valid_active_categories}
        category_map_json = json.dumps(category_map)

        self.output_table.clearContents()
        self.output_table.setRowCount(0)
        self.add_log_message(f"<font color='blue'>Starte Verarbeitung für Verzeichnis: {pdf_dir}</font>")
        self.set_ui_enabled(False)

        try:
            pdf_files = list(pathlib.Path(pdf_dir).glob("*.pdf"))
            self.total_pdfs = len(pdf_files)
            if self.total_pdfs == 0:
                self.add_log_message("<font color='orange'>Warnung: Keine PDF-Dateien im ausgewählten Verzeichnis gefunden.</font>")
                self.set_ui_enabled(True)
                return
            self.progress_bar.setMaximum(self.total_pdfs)
            self.processed_pdfs = 0
        except Exception as e:
            self.add_log_message(f"<font color='red'>Fehler beim Zählen der PDF-Dateien: {e}</font>")
            self.set_ui_enabled(True)
            return
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.handle_process_finished)

        script_path = os.path.join(os.path.dirname(__file__), "pdf_processor.py")
        os.environ["PYTHONUNBUFFERED"] = "1"

        command = [
            sys.executable, script_path, pdf_dir, target_url, model_name,
            assembled_prompt, category_map_json
        ]
        self.process.start(command[0], command[1:])

    def set_ui_enabled(self, enabled):
        """Enables or disables UI elements during processing."""
        self.start_button.setEnabled(enabled)
        self.cancel_button.setEnabled(not enabled)
        self.browse_pdf_dir_button.setEnabled(enabled)
        self.target_url_input.setEnabled(enabled)
        self.model_name_combobox.setEnabled(enabled)
        self.fetch_models_button.setEnabled(enabled)
        self.save_config_button.setEnabled(enabled)
        self.load_config_button.setEnabled(enabled)
        self.reset_config_button.setEnabled(enabled)
        self.add_category_button.setEnabled(enabled)
        self.toggle_categories_button.setEnabled(enabled)
        
        for i in range(self.categories_layout.count()):
            widget = self.categories_layout.itemAt(i).widget()
            if isinstance(widget, CategoryWidget):
                widget.setEnabled(enabled)

    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Wählen Sie das PDF-Verzeichnis")
        if directory:
            self.pdf_dir_input.setText(directory)
            if os.path.isdir(directory):
                self.start_button.setEnabled(True)
            else:
                self.start_button.setEnabled(False)

    def handle_process_finished(self, exit_code, exit_status):
        if exit_status == QProcess.ExitStatus.NormalExit:
            self.add_log_message("<font color='green'>✅ Verarbeitung abgeschlossen.</font>")
            self.status_info_label.setText("Status: Processing Complete")
        else:
            self.add_log_message(f"<font color='red'>❌ Verarbeitung mit Fehler beendet. Exit Code: {exit_code}</font>")
            self.status_info_label.setText(f"Status: Error (Exit Code: {exit_code})")
        self.set_ui_enabled(True)

    def update_info_labels(self):
        self.model_info_label.setText(f"Modell: {self.model_name_combobox.currentText() or 'N/A'}")
        self.target_url_info_label.setText(f"Target URL: {self.target_url_input.text()}")
        if self.process is None: self.status_info_label.setText("Status: Idle")
        elif self.process.state() == QProcess.ProcessState.Running: self.status_info_label.setText("Status: Processing...")
        else: self.status_info_label.setText("Status: Processing Complete")

    def add_log_message(self, message):
        print(message)

    def fetch_lm_studio_models(self):
        """Fetches the list of available models from the LM Studio API."""
        lm_studio_url = self.target_url_input.text().strip()
        if not lm_studio_url:
            self.add_log_message("<font color='red'>Bitte geben Sie zuerst die LM Studio Target URL an.</font>")
            return

        if not lm_studio_url.endswith('/v1'):
            lm_studio_url = lm_studio_url.rstrip('/') + '/v1'
            self.target_url_input.setText(lm_studio_url)

        models_url = f"{lm_studio_url}/models"
        self.add_log_message(f"Versuche, Modelle von {models_url} abzurufen...")

        try:
            response = requests.get(models_url, timeout=10)
            response.raise_for_status()
            models_data = response.json()
            
            if 'data' not in models_data:
                self.add_log_message("<font color='orange'>Keine Modelle gefunden oder unerwartetes Format von LM Studio.</font>")
                return

            available_models = [model['id'] for model in models_data.get('data', [])]
            
            if not available_models:
                self.add_log_message("<font color='orange'>Keine Modelle in der Antwort von LM Studio gefunden.</font>")
                return

            current_model = self.model_name_combobox.currentText()
            self.model_name_combobox.clear()
            self.model_name_combobox.addItems(available_models)
            self.add_log_message(f"<font color='green'>{len(available_models)} Modelle von LM Studio geladen.</font>")

            index = self.model_name_combobox.findText(current_model)
            if index != -1:
                self.model_name_combobox.setCurrentIndex(index)
            elif available_models:
                self.model_name_combobox.setCurrentIndex(0)

        except requests.exceptions.Timeout:
            self.add_log_message(f"<font color='red'>Fehler: Zeitüberschreitung beim Abrufen der Modelle von {models_url}.</font>")
        except requests.exceptions.RequestException as e:
            self.add_log_message(f"<font color='red'>Fehler beim Abrufen der Modelle von LM Studio: {e}</font>")
        except Exception as e:
            self.add_log_message(f"<font color='red'>Ein unerwarteter Fehler ist aufgetreten: {e}</font>")

    def cancel_processing(self):
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.terminate()

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace')
        lines = data.strip().split('\n')
        for line in lines:
            if "Original Filename" in line: continue
            parts = line.split('|')
            if len(parts) == 6:
                row_position = self.output_table.rowCount()
                self.output_table.insertRow(row_position)
                for i, part in enumerate(parts):
                    self.output_table.setItem(row_position, i, QTableWidgetItem(part.strip()))

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode('utf-8', errors='replace')
        self.add_log_message(f"<font color='red'>{data.strip()}</font>")

class PDFProcessorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Organizer & Renamer")
        
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        self.mainContent = MainContentWidget(self)

        self.layout.addWidget(self.title_bar)
        self.layout.addWidget(self.mainContent)

        self.setGeometry(100, 100, 900, 800)
        self.load_initial_config()
        self.oldPos = self.pos()

    def load_initial_config(self):
        self.mainContent.load_initial_config()

    def closeEvent(self, event):
        self.mainContent.save_current_config()
        super().closeEvent(event)

    def mousePressEvent(self, event):
        self.oldPos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        delta = QPoint(event.globalPosition().toPoint() - self.oldPos)
        self.move(self.x() + delta.x(), self.y() + delta.y())
        self.oldPos = event.globalPosition().toPoint()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Apply stylesheet
    with open("style.qss", "r") as f:
        app.setStyleSheet(f.read())

    gui = PDFProcessorGUI()
    gui.show()
    sys.exit(app.exec())
