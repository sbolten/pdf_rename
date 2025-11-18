# PDF Processor

This project contains two GUI applications for processing PDF files, one built with Flet and another with PyQt6.

## Setup

### Dependencies

To run either of the GUI applications, you first need to install the required Python packages. You can do this by running the following command in your terminal:

```bash
pip install -r requirements.txt
```

### Running the Flet GUI

To run the Flet GUI, execute the following command:

```bash
python3 gui_flet.py
```

### Running the PyQt6 GUI

The PyQt6 GUI may require a specific environment variable to be set, especially in environments without a graphical display. To run the PyQt6 GUI, use the following command:

```bash
export QT_QPA_PLATFORM=offscreen
python3 gui.py
```

This will ensure that the application can run without a display, which is necessary in some environments.
