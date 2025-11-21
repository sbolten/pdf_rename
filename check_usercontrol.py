import flet as ft
try:
    print(f"ft.UserControl: {ft.UserControl}")
except AttributeError:
    print("ft.UserControl does not exist")
