import random
from io import BytesIO
from time import perf_counter

import flet as ft
import requests

from middleware.llm_handler import LLMHandler
from middleware.sqlite_handler import DBHandler
from middleware.yt_api import YoutubeAPI
from ui.config_page import ConfigPage
from ui.list_widget import MyListWidget
from ui.video_tile import VideoTile


class MainPage(ft.Container):
    def __init__(self, page):
        super().__init__()

        # Connectors
        self.db_handler = DBHandler()
        self.yt_api = YoutubeAPI()
        self.llm_handler = LLMHandler()

        # Useful variables
        self.RUNNING_TASK = None
        self.CANCEL_FLAG = False
        self.feed_filters = []
        self.category_filters = []

        # Create the UI elements
        self.page = page

        self.setup_ui()

    def setup_ui(self):
        #
        settings = self.db_handler.get_settings()

        # Grid where all the video tiles will go
        self.video_grid = ft.GridView(child_aspect_ratio=0.75, max_extent=300)

        # Create the side lists for channels and categories
        self.feeds = MyListWidget(
            "Channels", "feed", self.filter_update, self.update_video_grid, self.yt_api
        )
        self.categories = MyListWidget(
            "Categories", "category", self.filter_update, self.update_video_grid
        )

        feed_list = self.db_handler.get_feed_full()
        for username in feed_list:
            self.feeds.add_item(username)

        category_list = self.db_handler.get_categories_full()
        for category in category_list:
            self.categories.add_item(category)

        self.left_side = ft.Column(
            [
                self.feeds,
                self.categories,
            ]
        )

        for video in self.db_handler.get_video_grid_data(
            self.feed_filters, self.category_filters
        ):
            self.video_grid.controls.append(
                VideoTile(data=video, tooltip_time=int(settings["app_tooltip_time"]))
            )

        self.progress_bar = ft.ProgressBar(
            visible=True,
            value=0.0,
            expand_loose=True,
            expand=True,
            color=ft.colors.TRANSPARENT,
        )

        self.progress_text = ft.Text(
            "",
            expand_loose=True,
            expand=True,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self.progress_indicator = ft.Column(
            [
                ft.Container(height=2),
                self.progress_bar,
                self.progress_text,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
            visible=False,
            spacing=0,
            run_spacing=0,
        )

        self.feed_update_progress = ft.ProgressRing(
            width=26,
            height=26,
            top=7,
            left=7,
            stroke_width=2,
            color=ft.colors.YELLOW,
            visible=False,
        )

        self.feed_update_button = ft.IconButton(
            icon=ft.icons.UPDATE,
            on_click=self.update_feeds_click,
            expand_loose=False,
            expand=False,
            tooltip=ft.Tooltip(
                "Fetch new videos from ALL feeds.",
                wait_duration=int(settings["app_tooltip_time"]),
            ),
        )

        self.proc_update_progress = ft.ProgressRing(
            width=26,
            height=26,
            top=7,
            left=7,
            stroke_width=2,
            color=ft.colors.RED,
            visible=False,
        )

        self.proc_update_button = ft.IconButton(
            icon=ft.icons.SMART_TOY,
            on_click=self.process_categories_click,
            expand_loose=False,
            expand=False,
            tooltip=ft.Tooltip(
                "Reprocess categories on ALL videos.",
                wait_duration=int(settings["app_tooltip_time"]),
            ),
        )

        self.top_row = ft.Row(
            [
                ft.IconButton(
                    icon=ft.icons.CLEAR,
                    on_click=self.clear_filters,
                    tooltip=ft.Tooltip(
                        "Clear all filters.",
                        wait_duration=int(settings["app_tooltip_time"]),
                    ),
                ),
                ft.Stack(
                    [
                        self.feed_update_progress,
                        self.feed_update_button,
                    ],
                    width=40,
                    height=40,
                ),
                ft.Stack(
                    [
                        self.proc_update_progress,
                        self.proc_update_button,
                    ],
                    width=40,
                    height=40,
                ),
                ft.Container(
                    self.progress_indicator,
                    expand=True,
                    expand_loose=True,
                ),
                ft.IconButton(
                    icon=ft.icons.SETTINGS,
                    on_click=lambda _: self.page.open(
                        ConfigPage(
                            (
                                self.page.window.width * 0.60
                                if (self.page.window.width > 800)
                                else self.page.window.width
                            ),
                            self.page.window.height,
                        )
                    ),
                    tooltip=ft.Tooltip(
                        "Change Settings.",
                        wait_duration=int(settings["app_tooltip_time"]),
                    ),
                ),
            ],
            tight=True,
        )

        # Set up the rest of the page
        self.main_content = ft.Container(
            ft.Column(
                [
                    self.top_row,
                    ft.Container(
                        self.video_grid,
                        expand=True,
                        expand_loose=True,
                    ),
                ]
            ),
            expand_loose=True,
            expand=True,
        )
        self.full_page_content = ft.Row(
            [self.left_side, self.main_content],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        self.content = self.full_page_content
        self.expand_loose = True
        self.expand = True

    async def update_feeds_click(self, _):
        if self.RUNNING_TASK is not None:
            if self.RUNNING_TASK == "update_feeds":
                print("Pressed again means Stop!")
                self.CANCEL_FLAG = True
                self.RUNNING_TASK = None
                self.feed_update_progress.visible = False
                self.progress_indicator.visible = False
                self.feed_update_button.icon = ft.icons.UPDATE
                self.feed_update_button.tooltip.message = (
                    "Fetch new videos from ALL feeds."
                )
                self.page.update()
                return
            else:
                return

        self.feed_update_progress.visible = True
        self.progress_indicator.visible = True
        self.feed_update_button.icon = ft.icons.STOP
        self.feed_update_button.tooltip.message = "Cancel Feed Update."
        self.update()

        self.RUNNING_TASK = "update_feeds"
        self.CANCEL_FLAG = False

        await self.update_videos(
            self.yt_api, self.video_grid, self.progress_bar, self.progress_text
        )

        self.feed_update_progress.visible = False
        self.progress_indicator.visible = False
        self.feed_update_button.icon = ft.icons.UPDATE
        self.feed_update_button.tooltip.message = "Fetch new videos from ALL feeds."
        self.update()

    async def process_categories_click(self, _):
        if self.RUNNING_TASK is not None:
            if self.RUNNING_TASK == "reproc_categories":
                print("Pressed again means Stop!")
                self.CANCEL_FLAG = True
                self.RUNNING_TASK = None
                self.proc_update_progress.visible = False
                self.progress_indicator.visible = False
                self.proc_update_button.icon = ft.icons.SMART_TOY
                self.proc_update_button.tooltip.message = (
                    "Reprocess categories on ALL videos."
                )
                self.update()
                return
            else:
                return

        self.proc_update_progress.visible = True
        self.progress_indicator.visible = True
        self.proc_update_button.icon = ft.icons.STOP
        self.proc_update_button.tooltip.message = "Cancel category reprocessing."
        self.update()

        self.RUNNING_TASK = "reproc_categories"
        self.CANCEL_FLAG = False

        await self.reprocess_all_categories(
            self.video_grid, self.progress_bar, self.progress_text
        )

        self.proc_update_progress.visible = False
        self.progress_indicator.visible = False
        self.proc_update_button.icon = ft.icons.SMART_TOY
        self.proc_update_button.tooltip.message = "Reprocess categories on ALL videos."
        self.update()

    def update_video_grid(self):
        db = DBHandler()

        all_videos = db.get_video_grid_data(
            self.feed_filters, self.category_filters, limit=100
        )
        settings = db.get_settings()

        new_grid = []

        for video in all_videos:
            new_grid.append(
                VideoTile(data=video, tooltip_time=int(settings["app_tooltip_time"]))
            )

        self.video_grid.controls = new_grid
        self.video_grid.update()

    def filter_update(self, data, type, action):
        if action == "added":
            if type == "feed":
                self.feed_filters.append(data)
            else:
                self.category_filters.append(data)
        if action == "removed":
            if type == "feed":
                self.feed_filters.remove(data)
            else:
                self.category_filters.remove(data)

        self.update_video_grid()

    def clear_filters(self, _):
        self.feed_filters.clear()
        self.category_filters.clear()

        for tile in self.feeds.list_items.controls:
            tile.selected = False
        for tile in self.categories.list_items.controls:
            tile.selected = False

        self.feeds.update()
        self.categories.update()

        self.update_video_grid()

    async def reprocess_all_categories(self, video_grid, progress_bar, progress_text):
        start = perf_counter()
        progress_bar.value = None
        progress_bar.color = ft.colors.RED
        progress_bar.update()

        db_handler = DBHandler()
        print("Clearing video_categories table...")
        db_handler.truncate_video_categories()
        settings = db_handler.get_settings()

        video_grid.controls.clear()
        video_grid.update()
        for video in db_handler.get_video_grid_data(
            self.feed_filters, self.category_filters
        ):
            video_grid.controls.append(
                VideoTile(data=video, tooltip_time=int(settings["app_tooltip_time"]))
            )
        video_grid.update()

        print("Getting list of videos...")
        videos = db_handler.get_full_video_data()
        print("Getting list of categories...")
        current_categories = db_handler.get_categories_full()
        print("Running categorize_video for each video")
        finished = 0

        # Shuffle the videos to give me variety in the output so I can maybe test classification options
        # easier?
        random.shuffle(videos)
        # videos = videos[:limit]

        for video in videos:
            if self.CANCEL_FLAG:
                break
            results = []
            progress_text.value = f"Classifying {video['title']}"
            progress_text.update()
            video_categories = await self.llm_handler.categorize_video(
                video["title"],
                video["transcript"],
                [c[0] for c in current_categories],
            )
            for vc in video_categories:
                for c in current_categories:
                    if c[0] == vc:
                        results.append((video["id"], c[0]))
            db_handler.bulk_add_video_category(results)

            video_grid.controls.clear()
            video_grid.update()
            for video in db_handler.get_video_grid_data(
                self.feed_filters, self.category_filters
            ):
                video_grid.controls.append(
                    VideoTile(
                        data=video, tooltip_time=int(settings["app_tooltip_time"])
                    )
                )
            video_grid.update()

            finished += 1
            print(f"Finished {finished}/{len(videos)}")
            progress_bar.value = finished / len(videos)
            progress_bar.update()

        print("Complete!")
        end = perf_counter()
        print(f"Took {end - start:.2f} seconds to reprocess {len(videos)} videos")

        progress_bar.value = 0.0
        progress_bar.color = ft.colors.TRANSPARENT
        progress_bar.update()

    async def update_videos(self, yt_api, video_grid, progress_bar, progress_text):
        progress_bar.value = None
        progress_bar.color = ft.colors.YELLOW
        progress_bar.update()

        db_handler = DBHandler()
        settings = db_handler.get_settings()
        current_video_ids, current_video_titles = (
            db_handler.get_current_video_ids_and_titles()
        )
        current_categories = db_handler.get_categories_full()
        channels = db_handler.get_channel_usernames()

        finished = 0
        for channel in channels:
            if self.CANCEL_FLAG:
                break

            progress_text.value = f"Finding video ID's for {channel}"
            progress_text.update()
            recent_videos = await yt_api.get_recent_videos(channel)
            for video_id, video_title in recent_videos:
                if video_id in current_video_ids:
                    current_title = db_handler.get_video_title(video_id)
                    if video_title != current_title:
                        db_handler.update_title(video_id, video_title)
                        print(
                            f"{video_id} was renamed: {current_title} -> {video_title}"
                        )
                        continue
                    print(
                        f"{video_id} is already in database with matching title, skipping."
                    )
                    continue

                video = yt_api.get_video_details(video_id)

                if video is None:
                    continue

                try:
                    thumbnail_bytes = BytesIO(
                        requests.get(video["thumbnail"]).content
                    ).getvalue()
                except Exception as e:
                    print(e)
                    print(video.get("thumbnail", "No Thumbnail URL Available??"))
                    thumbnail_bytes = b""

                video_categories = await self.llm_handler.categorize_video(
                    video["title"],
                    video["transcript"],
                    [c[0] for c in current_categories],
                )

                video_category_ids = []
                for vc in video_categories:
                    for c in current_categories:
                        if c[1] == vc:
                            video_category_ids.append(c[0])

                db_handler.add_video(
                    video_id,
                    channel,
                    video["url"],
                    video["title"],
                    video["upload_date"],
                    thumbnail_bytes,
                    video["tags"],
                    video["description"],
                    video["transcript"],
                    video_category_ids,
                )
                print(f'Added {video["title"]} to db')
                video_grid.controls.clear()
                video_grid.update()
                for v in db_handler.get_video_grid_data(
                    self.feed_filters, self.category_filters
                ):
                    video_grid.controls.append(
                        VideoTile(
                            data=v, tooltip_time=int(settings["app_tooltip_time"])
                        )
                    )
                video_grid.update()
            finished += 1
            progress_bar.value = finished / len(channels)
            progress_bar.update()
        print("Update complete")

        progress_bar.value = 0.0
        progress_bar.color = ft.colors.TRANSPARENT
        progress_bar.update()

    def on_resized(self, event: ft.WindowResizeEvent):
        self.left_side.width = 250
        self.left_side.height = event.height
        self.feeds.height = int(event.height * 0.675)
        self.feeds.list_items.height = self.feeds.height - 80
        self.categories.height = int(event.height * 0.3)
        self.categories.list_items.height = self.categories.height - 80
        self.main_content.height = self.feeds.height + self.categories.height + 10
        self.top_row.width = event.width - 250
        self.update()
