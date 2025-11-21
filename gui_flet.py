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
import pdf_processor

class CategoryControl(ft.Container):
    """A Flet control for a single category's configuration."""
    def __init__(self, name="", directory="", prompt="", active=True, on_remove=None):
        super().__init__()
        self.category_name = name
        self.on_remove = on_remove
        
        self.active_checkbox = ft.Checkbox(label="Aktiv", value=active, scale=0.9)
        self.remove_button = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE, 
            selected_icon=ft.Icons.DELETE,
            on_click=self.remove_clicked, 
            tooltip="Kategorie entfernen", 
            icon_size=20,
            icon_color=ft.Colors.ERROR
        )
        self.name_input = ft.TextField(label="Name", value=name, hint_text="Name (z.B. STEUER)", dense=True, text_size=13, expand=True, border=ft.InputBorder.UNDERLINE)
        self.directory_input = ft.TextField(label="Verzeichnis", value=directory, hint_text="Zielverzeichnis", dense=True, text_size=13, expand=True, border=ft.InputBorder.UNDERLINE)
        self.prompt_input = ft.TextField(label="Prompt", value=prompt, multiline=True, min_lines=2, max_lines=5, hint_text="Prompt-Kriterien...", text_size=13, border=ft.InputBorder.OUTLINE)

        # Make the 'OTHER' category non-removable and always active
        if name.upper() == 'OTHER':
            self.active_checkbox.value = True
            self.active_checkbox.disabled = True
            self.remove_button.disabled = True
            self.name_input.read_only = True

        self.padding = 15
        self.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGHEST
        self.border_radius = 10
        self.content = ft.Column(
            spacing=10,
            controls=[
                ft.Row([
                    self.active_checkbox, 
                    ft.Container(content=ft.Text(name, weight=ft.FontWeight.BOLD, size=14), padding=ft.padding.only(left=10)),
                    ft.Container(expand=True), 
                    self.remove_button
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([self.name_input, self.directory_input], spacing=15),
                self.prompt_input,
            ]
        )

    def remove_clicked(self, e):
        if self.on_remove:
            self.on_remove(self)

def main(page: ft.Page):
    page.title = "PDF Organizer & Renamer"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    page.window_width = 1000
    page.window_height = 900

    config_manager = ConfigManager()
    
    # --- UI Controls ---
    pdf_dir_input = ft.TextField(label="PDF Verzeichnis", expand=True, dense=True, text_size=14, border=ft.InputBorder.OUTLINE)
    target_url_input = ft.TextField(label="Target URL", expand=True, dense=True, text_size=14, border=ft.InputBorder.OUTLINE)
    model_name_combobox = ft.Dropdown(label="Modellname", expand=True, dense=True, text_size=14, border=ft.InputBorder.OUTLINE)
    base_prompt_input = ft.TextField(label="Base Prompt Vorlage", multiline=True, min_lines=5, text_size=14, border=ft.InputBorder.OUTLINE)
    
    categories_column = ft.Column(spacing=15)
    
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
            show_snackbar("Bitte geben Sie zuerst die LM Studio Target URL an.", ft.Colors.RED)
            return

        if not lm_studio_url.endswith('/v1'):
            lm_studio_url = lm_studio_url.rstrip('/') + '/v1'
            target_url_input.value = lm_studio_url
        
        models_url = f"{lm_studio_url}/models"
        show_snackbar(f"Versuche, Modelle von {models_url} abzurufen...", ft.Colors.BLUE)

        try:
            response = requests.get(models_url, timeout=10)
            response.raise_for_status()
            models_data = response.json()
            
            available_models = [model['id'] for model in models_data.get('data', [])]
            if not available_models:
                show_snackbar("Keine Modelle in der Antwort von LM Studio gefunden.", ft.Colors.ORANGE)
                return

            model_name_combobox.options = [ft.dropdown.Option(model) for model in available_models]
            show_snackbar(f"{len(available_models)} Modelle von LM Studio geladen.", ft.Colors.GREEN)
            page.update()

        except requests.exceptions.RequestException as err:
            show_snackbar(f"Fehler beim Abrufen der Modelle: {err}", ft.Colors.RED)
        except Exception as err:
            show_snackbar(f"Ein unerwarteter Fehler ist aufgetreten: {err}", ft.Colors.RED)

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
            show_snackbar("Konfiguration erfolgreich gespeichert.", ft.Colors.GREEN)
        else:
            show_snackbar("Fehler beim Speichern der Konfiguration.", ft.Colors.RED)

    def load_config(e):
        config_manager.load_config()
        apply_config_to_gui(config_manager.get_current_config())
        show_snackbar("Konfiguration geladen.", ft.Colors.BLUE)

    def reset_config(e):
        default_config = config_manager.get_default_config()
        apply_config_to_gui(default_config)
        show_snackbar("Konfiguration auf Standardwerte zurückgesetzt.", ft.Colors.BLUE)

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
            show_snackbar("Fehler: Bitte wählen Sie ein gültiges PDF-Verzeichnis aus.", ft.Colors.RED)
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

            pdf_files = list(pathlib.Path(pdf_dir).glob("*.pdf"))
            total_pdfs = len(pdf_files)
            processed_pdfs_count = [0] # Mutable list to track count in inner function

            def progress_callback(data):
                output_table.rows.append(
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(data.get('original_filename', ''))),
                        ft.DataCell(ft.Text(data.get('checksum', ''))),
                        ft.DataCell(ft.Text(data.get('new_filename', ''))),
                        ft.DataCell(ft.Text(data.get('status', ''))),
                        ft.DataCell(ft.Text(data.get('target_folder', ''))),
                        ft.DataCell(ft.Text(data.get('error_message', ''))),
                    ])
                )
                processed_pdfs_count[0] += 1
                if total_pdfs > 0:
                    progress_bar.value = processed_pdfs_count[0] / total_pdfs
                page.update()

            pdf_processor.process_pdfs(
                pdf_dir,
                target_url,
                model_name,
                assembled_prompt,
                category_map_json,
                progress_callback=progress_callback
            )

            status_info_label.value = "Status: Processing Complete"
            show_snackbar("✅ Verarbeitung abgeschlossen.", ft.Colors.GREEN)

        except Exception as ex:
            status_info_label.value = "Status: Error"
            show_snackbar(f"❌ Fehler bei der Verarbeitung: {ex}", ft.Colors.RED)
        finally:
            progress_bar.visible = False
            set_ui_enabled(True)
            page.update()


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
        ft.AppBar(title=ft.Text("PDF Organizer & Renamer"), bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST),
        ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="Konfiguration",
                    icon=ft.Icons.SETTINGS,
                    content=ft.Container(
                        padding=20,
                        content=ft.Column(
                            scroll=ft.ScrollMode.AUTO,
                            spacing=20,
                            controls=[
                                ft.Card(
                                    content=ft.Container(
                                        padding=20,
                                        content=ft.Column([
                                            ft.Text("Allgemeine Einstellungen", style=ft.TextThemeStyle.TITLE_LARGE, weight=ft.FontWeight.BOLD),
                                            ft.Divider(),
                                            ft.Row([pdf_dir_input, browse_pdf_dir_button], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                            ft.Row([target_url_input, model_name_combobox, fetch_models_button], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                        ], spacing=15)
                                    )
                                ),
                                ft.Card(
                                    content=ft.Container(
                                        padding=20,
                                        content=ft.Column([
                                            ft.Text("Prompt Engineering", style=ft.TextThemeStyle.TITLE_LARGE, weight=ft.FontWeight.BOLD),
                                            ft.Divider(),
                                            base_prompt_input,
                                        ], spacing=15)
                                    )
                                ),
                                ft.Card(
                                    content=ft.Container(
                                        padding=20,
                                        content=ft.Column([
                                            ft.Row([
                                                ft.Text("Kategorien", style=ft.TextThemeStyle.TITLE_LARGE, weight=ft.FontWeight.BOLD),
                                                add_category_button
                                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                            ft.Divider(),
                                            categories_column
                                        ], spacing=15)
                                    )
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
                    icon=ft.Icons.PLAY_ARROW,
                    content=ft.Container(
                        padding=20,
                        content=ft.Column(
                            scroll=ft.ScrollMode.AUTO,
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
    ft.app(target=main)
