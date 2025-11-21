import flet as ft
try:
    print([c for c in dir(ft.Colors) if "SURFACE" in c])
except Exception as e:
    print(e)
