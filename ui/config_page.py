import random

import flet as ft
from rich import print_json

from middleware.sqlite_handler import DBHandler

LABEL_WIDTH = 165


class ConfigRow(ft.Row):
    def __init__(self, label, current_val, lines=1):
        super().__init__()
        self.setting = label
        self.setting_input = ft.TextField(
            border_color=ft.colors.ON_PRIMARY_CONTAINER,
            expand=True,
            expand_loose=True,
            max_lines=lines,
            min_lines=lines,
            value=current_val,
        )
        self.controls = [
            ft.Text(label, width=LABEL_WIDTH),
            self.setting_input,
        ]
        self.tight = True


class ConfigPage(ft.AlertDialog):
    def __init__(self, width, height):
        super().__init__()

        self.db_handler = DBHandler()
        self.settings = self.db_handler.get_settings()

        self.config_controls = []
        put_last = []
        for k, v in sorted(self.settings.items()):
            if "prompt" in k:
                put_last.append((k, v, 12))
            else:
                self.config_controls.append(ConfigRow(k, v, 1))

        for k, v, l in put_last:
            self.config_controls.append(ConfigRow(k, v, l))

        self.title = ft.Text("Settings")
        self.content = ft.Column(
            self.config_controls,
            expand_loose=True,
            expand=True,
            tight=False,
            width=width,
            height=height,
            scroll=ft.ScrollMode.ALWAYS,
        )
        self.actions = [
            ft.TextButton("Cancel", on_click=lambda _: self.page.close(self)),
            ft.FilledButton(
                "Save",
                on_click=self.save_settings,
            ),
        ]

    def save_settings(self, _):
        for setting in self.config_controls:
            key = setting.setting
            value = setting.setting_input.value
            self.db_handler.put_setting(key, value)

        self.page.close(self)
