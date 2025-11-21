import flet as ft
try:
    print(f"ft.colors: {ft.colors}")
except AttributeError:
    print("ft.colors does not exist")

try:
    print(f"ft.Colors: {ft.Colors}")
except AttributeError:
    print("ft.Colors does not exist")
