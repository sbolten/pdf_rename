import flet as ft
try:
    print(f"ft.icons: {ft.icons}")
except AttributeError:
    print("ft.icons does not exist")

try:
    print(f"ft.Icons: {ft.Icons}")
except AttributeError:
    print("ft.Icons does not exist")

try:
    print(f"ft.dropdown: {ft.dropdown}")
except AttributeError:
    print("ft.dropdown does not exist")

try:
    print(f"ft.border: {ft.border}")
except AttributeError:
    print("ft.border does not exist")
