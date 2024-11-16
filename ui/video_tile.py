import flet as ft
import base64
import pyperclip
from datetime import datetime

from middleware.llm_handler import LLMHandler
from middleware.sqlite_handler import DBHandler


class VideoTile(ft.Container):
    def __init__(self, data, tooltip_time):
        super().__init__()
        self.border = ft.border.all(1, ft.colors.PRIMARY)
        self.border_radius = ft.border_radius.all(8)
        self.padding = ft.padding.all(8)
        self.bgcolor = ft.colors.SECONDARY_CONTAINER
        self.data = data
        self.expand = True
        self.expand_loose = True
        self.text_style = ft.TextStyle(color=ft.colors.ON_SECONDARY_CONTAINER, size=13)
        self.chip_style = ft.TextStyle(color=ft.colors.ON_SECONDARY_CONTAINER, size=12)

        self.category_chips = ft.Row(
            [
                ft.Chip(
                    label=ft.Text(category, style=self.chip_style),
                    disabled_color=ft.colors.PRIMARY_CONTAINER,
                    padding=0,
                )
                for category in sorted(data["categories"], key=lambda x: x.lower())
            ],
            tight=True,
            scroll=ft.ScrollMode.AUTO,
        )

        self.classify_spinner = ft.ProgressRing(
            width=32,
            height=32,
            top=68,
            right=0,
            visible=False,
            color=ft.colors.YELLOW,
        )

        self.content = ft.Stack(
            [
                ft.Column(
                    [
                        ft.Image(
                            src_base64=base64.b64encode(data["thumbnail"]).decode(
                                "utf-8"
                            ),
                        ),
                        ft.Text(
                            data["display_name"],
                            style=self.text_style,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            datetime.fromisoformat(
                                data["upload_date"].replace("Z", "+00:00")
                            ).strftime("%B %d, %Y"),
                            style=self.text_style,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            data["title"] + "\n",
                            style=self.text_style,
                            expand=True,
                            max_lines=2,
                            # max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        self.category_chips,
                    ]
                ),
                ft.IconButton(
                    icon=ft.icons.COPY,
                    top=0,
                    right=0,
                    bgcolor=ft.colors.BLACK45,
                    icon_size=14,
                    # padding=0,
                    # splash_radius=4,
                    width=32,
                    height=32,
                    on_click=lambda _: pyperclip.copy(
                        f"[{data['title']}]({data['url']})"
                    ),
                    tooltip=ft.Tooltip(
                        "Copy video link to clipboard.",
                        wait_duration=tooltip_time,
                    ),
                ),
                ft.IconButton(
                    icon=ft.icons.OPEN_IN_BROWSER,
                    top=34,
                    right=0,
                    bgcolor=ft.colors.BLACK45,
                    icon_size=14,
                    width=32,
                    height=32,
                    on_click=lambda _: self.page.launch_url(data["url"]),
                    tooltip=ft.Tooltip(
                        "Open video in browser.",
                        wait_duration=tooltip_time,
                    ),
                ),
                ft.IconButton(
                    icon=ft.icons.SMART_TOY,
                    top=68,
                    right=0,
                    bgcolor=ft.colors.BLACK45,
                    icon_size=14,
                    # padding=0,
                    # splash_radius=4,
                    width=32,
                    height=32,
                    on_click=self.reclassify_video,
                    tooltip=ft.Tooltip(
                        "Re-categorize this video.",
                        wait_duration=tooltip_time,
                    ),
                ),
                self.classify_spinner,
            ]
        )

    async def reclassify_video(self, _):
        # First clear all visible categories for the video
        self.classify_spinner.visible = True
        self.classify_spinner.update()
        self.data["categories"].clear()
        self.category_chips.controls.clear()
        self.update()

        # Drop all the category associations from the database
        db_handler = DBHandler()
        db_handler.delete_video_categories(self.data["id"])

        # Get the available categories
        categories = db_handler.get_categories_full()
        llm_categories = [c[0] for c in categories]

        # Call classify
        transcript = db_handler.get_video_transcript(self.data["id"])
        llm_handler = LLMHandler()
        new_categories = await llm_handler.categorize_video(
            self.data["title"], transcript, llm_categories
        )

        new_cat_list = [(self.data["id"], c) for c in new_categories]

        # Save the new categories
        db_handler.bulk_add_video_category(
            new_cat_list,
        )

        # Add the chips back to the UI
        for llm_category in new_categories:
            display_category = ""
            for c in categories:
                if c[0] == llm_category:
                    display_category = c[1]
            self.category_chips.controls.append(
                ft.Chip(
                    label=ft.Text(display_category, style=self.chip_style),
                    disabled_color=ft.colors.PRIMARY_CONTAINER,
                    padding=0,
                )
            )

        # Update UI
        self.classify_spinner.visible = False
        self.classify_spinner.update()
        self.update()
