import flet as ft
from flet import Control
import os
import json
import pathlib
import requests
import subprocess
import sys
import threading
from configuration import ConfigManager

class CategoryControl(Control):
    """A Flet control for a single category's configuration."""
    def __init__(self, name="", directory="", prompt="", active=True, on_remove=None):
        super().__init__()
        self.category_name = name
        self.on_remove = on_remove
        
        self.active_checkbox = ft.Checkbox(label="Aktiv", value=active)
        self.remove_button = ft.IconButton(icon=ft.Icons.DELETE, on_click=self.remove_clicked, tooltip="Kategorie entfernen")
        self.name_input = ft.TextField(label="Name", value=name, hint_text="Name der Kategorie (z.B. STEUER)")
        self.directory_input = ft.TextField(label="Verzeichnis", value=directory, placeholder_text="Zielverzeichnis (z.B. Steuerunterlagen)")
        self.prompt_input = ft.TextField(label="Prompt", value=prompt, multiline=True, min_lines=3, placeholder_text="Prompt-Kriterien für diese Kategorie...")

        # Make the 'OTHER' category non-removable and always active
        if name.upper() == 'OTHER':
            self.active_checkbox.value = True
            self.active_checkbox.disabled = True
            self.remove_button.disabled = True
            self.name_input.read_only = True

    def remove_clicked(self, e):
        if self.on_remove:
            self.on_remove(self)

    def build(self):
        return ft.Container(
            padding=15,
            border=ft.border.all(1, ft.colors.OUTLINE),
            border_radius=8,
            content=ft.Column(
                controls=[
                    ft.Row([self.active_checkbox, ft.Container(expand=True), self.remove_button]),
                    self.name_input,
                    self.directory_input,
                    self.prompt_input,
                ]
            )
        )

def main(page: ft.Page):
    page.title = "PDF Organizer & Renamer (Flet)"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_width = 950
    page.window_height = 850

    config_manager = ConfigManager()
    
    # --- UI Controls ---
    pdf_dir_input = ft.TextField(label="PDF Verzeichnis", expand=True)
    target_url_input = ft.TextField(label="Target URL")
    model_name_combobox = ft.Dropdown(label="Modellname")
    base_prompt_input = ft.TextField(label="Base Prompt Vorlage", multiline=True, min_lines=5)
    
    categories_column = ft.Column(spacing=10)
    
    output_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Original Filename")),
            ft.DataColumn(ft.Text("Checksum")),
            ft.DataColumn(ft.Text("New Filename")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("Target Folder")),
            ft.DataColumn(ft.Text("Error Message")),
        ],
        rows=[],
        expand=True,
    )
    
    progress_bar = ft.ProgressBar(value=0, visible=False)
    status_info_label = ft.Text("Status: Idle", style=ft.TextThemeStyle.BODY_LARGE)
    
    # --- Functions ---

    def pick_pdf_directory(e):
        def on_result(result: ft.FilePickerResultEvent):
            if result.path:
                pdf_dir_input.value = result.path
                page.update()
        
        file_picker = ft.FilePicker(on_result=on_result)
        page.overlay.append(file_picker)
        page.update()
        file_picker.get_directory_path(dialog_title="Wählen Sie das PDF-Verzeichnis")

    def fetch_lm_studio_models(e):
        lm_studio_url = target_url_input.value.strip()
        if not lm_studio_url:
            show_snackbar("Bitte geben Sie zuerst die LM Studio Target URL an.", ft.colors.RED)
            return

        if not lm_studio_url.endswith('/v1'):
            lm_studio_url = lm_studio_url.rstrip('/') + '/v1'
            target_url_input.value = lm_studio_url
        
        models_url = f"{lm_studio_url}/models"
        show_snackbar(f"Versuche, Modelle von {models_url} abzurufen...", ft.colors.BLUE)

        try:
            response = requests.get(models_url, timeout=10)
            response.raise_for_status()
            models_data = response.json()
            
            available_models = [model['id'] for model in models_data.get('data', [])]
            if not available_models:
                show_snackbar("Keine Modelle in der Antwort von LM Studio gefunden.", ft.colors.ORANGE)
                return

            model_name_combobox.options = [ft.dropdown.Option(model) for model in available_models]
            show_snackbar(f"{len(available_models)} Modelle von LM Studio geladen.", ft.colors.GREEN)
            page.update()

        except requests.exceptions.RequestException as err:
            show_snackbar(f"Fehler beim Abrufen der Modelle: {err}", ft.colors.RED)
        except Exception as err:
            show_snackbar(f"Ein unerwarteter Fehler ist aufgetreten: {err}", ft.colors.RED)

    def remove_category_widget(widget_to_remove):
        categories_column.controls.remove(widget_to_remove)
        page.update()

    def add_category_widget(e=None, name="", directory="", prompt="", active=True):
        new_category = CategoryControl(name, directory, prompt, active, on_remove=remove_category_widget)
        categories_column.controls.append(new_category)
        page.update()

    def read_config_from_gui():
        return {
            "pdf_dir": pdf_dir_input.value,
            "target_url": target_url_input.value,
            "model_name": model_name_combobox.value,
            "base_prompt_template": base_prompt_input.value,
            "categories": [
                {
                    "name": cat.name_input.value,
                    "directory": cat.directory_input.value,
                    "prompt": cat.prompt_input.value,
                    "active": cat.active_checkbox.value
                } for cat in categories_column.controls if isinstance(cat, CategoryControl) 
            ]
        }

    def apply_config_to_gui(config):
        pdf_dir_input.value = config.get("pdf_dir", "")
        target_url_input.value = config.get("target_url", "")
        base_prompt_input.value = config.get("base_prompt_template", "")
        
        model_name = config.get("model_name", "")
        if model_name:
            # Check if the model is already in the options, if not, add it.
            if not any(opt.key == model_name for opt in model_name_combobox.options):
                 model_name_combobox.options.append(ft.dropdown.Option(model_name))
            model_name_combobox.value = model_name

        categories_column.controls.clear()
        for category in config.get("categories", []):
            add_category_widget(
                name=category.get("name", ""),
                directory=category.get("directory", ""),
                prompt=category.get("prompt", ""),
                active=category.get("active", True)
            )
        page.update()

    def save_config(e):
        config = read_config_from_gui()
        if config_manager.save_config(config):
            show_snackbar("Konfiguration erfolgreich gespeichert.", ft.colors.GREEN)
        else:
            show_snackbar("Fehler beim Speichern der Konfiguration.", ft.colors.RED)

    def load_config(e):
        config_manager.load_config()
        apply_config_to_gui(config_manager.get_current_config())
        show_snackbar("Konfiguration geladen.", ft.colors.BLUE)

    def reset_config(e):
        default_config = config_manager.get_default_config()
        apply_config_to_gui(default_config)
        show_snackbar("Konfiguration auf Standardwerte zurückgesetzt.", ft.colors.BLUE)

    def show_snackbar(message, color):
        page.snack_bar = ft.SnackBar(content=ft.Text(message), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    def set_ui_enabled(enabled: bool):
        for ctrl in [
            pdf_dir_input, target_url_input, model_name_combobox, base_prompt_input,
            save_config_button, load_config_button, reset_config_button, start_button,
            add_category_button, fetch_models_button, browse_pdf_dir_button
        ]:
            ctrl.disabled = not enabled
        
        for cat_ctrl in categories_column.controls:
            cat_ctrl.disabled = not enabled
        
        cancel_button.disabled = enabled
        page.update()

    def start_processing(e):
        config = read_config_from_gui()
        pdf_dir = config.get("pdf_dir")
        
        if not pdf_dir or not os.path.isdir(pdf_dir):
            show_snackbar("Fehler: Bitte wählen Sie ein gültiges PDF-Verzeichnis aus.", ft.colors.RED)
            return

        # Further validation as in the original GUI
        # ...

        set_ui_enabled(False)
        output_table.rows.clear()
        progress_bar.value = 0
        progress_bar.visible = True
        status_info_label.value = "Status: Processing..."
        page.update()

        # Run processing in a separate thread to avoid blocking the UI
        thread = threading.Thread(target=run_processing_thread, args=(config,))
        thread.start()

    def run_processing_thread(config):
        try:
            pdf_dir = config.get("pdf_dir")
            target_url = config.get("target_url")
            model_name = config.get("model_name")
            all_categories = config.get("categories", [])
            base_template = config.get("base_prompt_template")

            valid_active_categories = [
                cat for cat in all_categories 
                if cat.get("active", False) and cat.get("name", "").strip() and cat.get("directory", "").strip()
            ]
            
            category_definitions = [f"### {i+1}. {cat['name']}\n{cat['prompt']}" for i, cat in enumerate(valid_active_categories)]
            assembled_prompt = base_template.replace("{{category_definitions}}", "\n\n".join(category_definitions))
            category_map = {cat['name']: cat['directory'] for cat in valid_active_categories}
            category_map_json = json.dumps(category_map)

            script_path = os.path.join(os.path.dirname(__file__), "pdf_processor.py")
            command = [
                sys.executable, script_path, pdf_dir, target_url, model_name,
                assembled_prompt, category_map_json
            ]

            pdf_files = list(pathlib.Path(pdf_dir).glob("*.pdf"))
            total_pdfs = len(pdf_files)
            processed_pdfs = 0

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            # Read stdout line by line
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                
                line = line.strip()
                if "Original Filename" in line or not line:
                    continue
                
                parts = line.split('|')
                if len(parts) == 6:
                    output_table.rows.append(
                        ft.DataRow(cells=[ft.DataCell(ft.Text(p.strip())) for p in parts])
                    )
                    processed_pdfs += 1
                    if total_pdfs > 0:
                        progress_bar.value = processed_pdfs / total_pdfs
                    page.update()

            # Handle stderr
            stderr_output = process.stderr.read()
            if stderr_output:
                # In a real app, you'd want to display this error more gracefully
                print(f"Error from script: {stderr_output}")

            process.wait()
            status_info_label.value = "Status: Processing Complete"
            show_snackbar("✅ Verarbeitung abgeschlossen.", ft.colors.GREEN)

        except Exception as ex:
            status_info_label.value = "Status: Error"
            show_snackbar(f"❌ Fehler bei der Verarbeitung: {ex}", ft.colors.RED)
        finally:
            progress_bar.visible = False
            set_ui_enabled(True)


    # --- Buttons ---
    browse_pdf_dir_button = ft.ElevatedButton("Durchsuchen...", on_click=pick_pdf_directory)
    fetch_models_button = ft.ElevatedButton("Modelle laden", on_click=fetch_lm_studio_models)
    save_config_button = ft.ElevatedButton("Konfiguration speichern", on_click=save_config)
    load_config_button = ft.ElevatedButton("Konfiguration laden", on_click=load_config)
    reset_config_button = ft.ElevatedButton("Auf Standard zurücksetzen", on_click=reset_config)
    add_category_button = ft.ElevatedButton("Neue Kategorie hinzufügen", on_click=add_category_widget)
    start_button = ft.ElevatedButton("Verarbeitung starten", on_click=start_processing, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)
    cancel_button = ft.ElevatedButton("Verarbeitung abbrechen", disabled=True) # Note: Cancel logic is complex with subprocess and not implemented here for brevity.

    # --- Initial Config Load ---
    load_config(None)

    # --- Layout ---
    page.add(
        ft.AppBar(title=ft.Text("PDF Organizer & Renamer"), bgcolor=ft.colors.SURFACE_VARIANT),
        ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="Konfiguration",
                    icon=ft.icons.SETTINGS,
                    content=ft.Container(
                        padding=20,
                        content=ft.Column(
                            spacing=15,
                            controls=[
                                ft.Text("Allgemeine Konfiguration", style=ft.TextThemeStyle.HEADLINE_SMALL),
                                ft.Row([pdf_dir_input, browse_pdf_dir_button]),
                                target_url_input,
                                ft.Row([model_name_combobox, fetch_models_button]),
                                ft.Text("Base Prompt Vorlage", style=ft.TextThemeStyle.HEADLINE_SMALL),
                                base_prompt_input,
                                ft.ExpansionPanelList(
                                    expand_icon_color=ft.colors.BLUE_GREY_500,
                                    elevation=4,
                                    divider_color=ft.colors.OUTLINE,
                                    controls=[
                                        ft.ExpansionPanel(
                                            header=ft.ListTile(title=ft.Text("Dynamische Kategorien")),
                                            content=ft.Container(
                                                padding=10,
                                                content=ft.Column([
                                                    categories_column,
                                                    add_category_button
                                                ])
                                            )
                                        )
                                    ]
                                ),
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    controls=[save_config_button, load_config_button, reset_config_button]
                                ),
                            ]
                        )
                    )
                ),
                ft.Tab(
                    text="Verarbeitung",
                    icon=ft.icons.PLAY_ARROW,
                    content=ft.Container(
                        padding=20,
                        content=ft.Column(
                            spacing=15,
                            controls=[
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    controls=[start_button, cancel_button]
                                ),
                                progress_bar,
                                ft.Divider(),
                                ft.Row([
                                    status_info_label,
                                ]),
                                ft.Column([output_table], scroll=ft.ScrollMode.ALWAYS, expand=True)
                            ]
                        )
                    )
                ),
            ],
            expand=1,
        )
    )

if __name__ == "__main__":
    ft.app(target=main, port=8001)
