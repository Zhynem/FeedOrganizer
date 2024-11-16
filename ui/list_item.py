import flet as ft

from middleware.sqlite_handler import DBHandler


class MyListItem(ft.ListTile):
    def __init__(self, data, tile_type, filter_cb, rm_cb, tooltip_time):
        super().__init__()
        self.content_padding = 0
        self.data = data
        self.rm_cb = rm_cb
        self.tile_type = tile_type
        self.filter_cb = filter_cb
        self.title = ft.Text(data[1])
        self.trailing = ft.IconButton(
            icon=ft.icons.REMOVE_CIRCLE_OUTLINE,
            on_click=self.delete_item,
            tooltip=ft.Tooltip(
                f"Delete {self.data[1]} and all associated items",
                wait_duration=tooltip_time,
            ),
        )
        self.bgcolor = ft.colors.BACKGROUND
        self.selected_tile_color = ft.colors.SECONDARY_CONTAINER
        self.hover_color = ft.colors.SECONDARY_CONTAINER
        self.on_click = self.tile_clicked
        self.selected = False
        self.tooltip = ft.Tooltip(
            f"Filter on {self.data[1]}",
            wait_duration=tooltip_time,
        )

    def tile_clicked(self, _):
        if self.selected:
            print(f"Removing Filter: {self.data[1]}")
            self.selected = False
            self.filter_cb(self.data[0], self.tile_type, "removed")
        else:
            print(f"Adding Filter  : {self.data[1]}")
            self.selected = True
            self.filter_cb(self.data[0], self.tile_type, "added")
        self.update()

    def delete_item(self, _):
        db_handler = DBHandler()
        settings = db_handler.get_settings()

        def confirm_callback(_):
            self.page.close(dialog)
            self.rm_cb(self.data[0])

        confirm_delete = True if settings["app_confirm_delete"] == "True" else False

        if confirm_delete:
            if self.page is None:
                print("No page attribute present")
                return

            dialog = ft.AlertDialog(
                title=ft.Text(
                    f"Really delete {self.data[1]}?",
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: self.page.close(dialog)),
                    ft.FilledButton(
                        "Confirm",
                        on_click=confirm_callback,
                    ),
                ],
                modal=False,
            )
            self.page.open(dialog)
        else:
            self.rm_cb(self.data[0])
