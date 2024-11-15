import flet as ft
from sympy.physics.units import second

from middleware.sqlite_handler import DBHandler
from ui.list_item import MyListItem


class MyListWidget(ft.Container):
    def __init__(
        self,
        title,
        list_type,
        filter_update_callback,
        grid_update_callback,
        yt_api=None,
    ):
        super().__init__()

        db_handler = DBHandler()
        self.settings = db_handler.get_settings()
        self.yt_api = yt_api
        self.list_type = list_type

        self.filter_update_callback = filter_update_callback

        self.grid_update_callback = grid_update_callback

        self.list_items = ft.ListView(padding=0)

        self.border = ft.border.all(1, ft.colors.PRIMARY)
        self.border_radius = ft.border_radius.all(8)
        self.padding = ft.padding.all(8)

        self.content = ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Text(title, style=ft.TextStyle(size=18)),
                        ft.Container(expand_loose=True, expand=True),
                        ft.IconButton(
                            icon=ft.icons.ADD_CIRCLE_OUTLINE,
                            icon_color=ft.colors.SECONDARY,
                            on_click=self.show_input_prompt,
                            tooltip=ft.Tooltip(
                                f"Add new {'Channel' if self.list_type == 'channel' else 'Category'}",
                                wait_duration=int(self.settings["app_tooltip_time"]),
                            ),
                        ),
                    ]
                ),
                ft.Divider(),
                self.list_items,
            ],
        )

    def show_input_prompt(self, _):
        if self.page is None:
            print("No page attribute present")
            return

        main_input = ft.TextField(
            width=200,
            autofocus=True,
            focused_border_color=ft.colors.PRIMARY,
            border_color=ft.colors.SECONDARY,
        )
        secondary_input = ft.TextField(
            width=200,
            autofocus=False,
            focused_border_color=ft.colors.PRIMARY,
            border_color=ft.colors.SECONDARY,
        )

        def save_callback(_):
            self.page.close(dialog)
            self.add_item([main_input.value, secondary_input.value])
            self.create_item(main_input.value, secondary_input.value)

        dialog = ft.AlertDialog(
            title=ft.Text(
                f"New {'Feed' if self.list_type == 'feed' else 'Category'}",
            ),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                f"{'Username' if self.list_type == 'feed' else 'LLM Category'}",
                                width=100,
                            ),
                            main_input,
                        ],
                        tight=True,
                    ),
                    ft.Row(
                        [
                            ft.Text(
                                f"{'Display Name' if self.list_type == 'feed' else 'Category Display'}",
                                width=100,
                            ),
                            secondary_input,
                        ],
                        tight=True,
                    ),
                ],
                tight=True,
                width=300,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.page.close(dialog)),
                ft.FilledButton(
                    "Save",
                    on_click=save_callback,
                ),
            ],
            modal=False,
        )

        self.page.open(dialog)

    def create_item(self, data, display):
        # Add item to DB
        db_handler = DBHandler()
        if self.list_type == "feed":
            # channel_id = self.yt_api.get_channel_id(data)
            db_handler.add_feed(data, display)
        elif self.list_type == "category":
            db_handler.add_category(data, display)

    def add_item(self, item):
        # Add item to UI
        self.list_items.controls.append(
            MyListItem(
                data=item,
                tile_type=self.list_type,
                filter_cb=self.filter_update_callback,
                rm_cb=self.remove_item,
                tooltip_time=int(self.settings["app_tooltip_time"]),
            )
        )

        self.list_items.controls.sort(key=lambda i: i.data[1])

        try:
            self.list_items.update()
        except:
            pass

    def remove_item(self, rm_data):
        db_handler = DBHandler()
        # Remove element from UI
        for item in self.list_items.controls:
            if item.data[0] == rm_data:
                self.list_items.controls.remove(item)
        # Remove element from DB
        if self.list_type == "feed":
            db_handler.delete_feed(rm_data)
        elif self.list_type == "category":
            print(f"Removing {rm_data} from db...")
            db_handler.delete_category(rm_data)

        try:
            self.list_items.update()
        except:
            pass

        self.grid_update_callback()

    def update(self):
        super().update()
        self.list_items.height = self.height - 100
