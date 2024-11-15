from io import BytesIO
import random

import flet as ft
import requests
from time import perf_counter

from middleware.llm_handler import LLMHandler
from middleware.yt_api import YoutubeAPI
from middleware.sqlite_handler import DBHandler
from ui.config_page import ConfigPage
from ui.list_widget import MyListWidget

from ui.video_tile import VideoTile


RUNNING_TASK = None
CANCEL_FLAG = False


async def reprocess_all_categories(video_grid, progress_bar, progress_text):
    llm_handler = LLMHandler()

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
    for video in db_handler.get_video_grid_data():
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
        if CANCEL_FLAG:
            break
        results = []
        progress_text.value = f"Classifying {video['title']}"
        progress_text.update()
        video_categories = await llm_handler.categorize_video(
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
        for video in db_handler.get_video_grid_data():
            video_grid.controls.append(
                VideoTile(data=video, tooltip_time=int(settings["app_tooltip_time"]))
            )
        video_grid.update()

        finished += 1
        print(f"Finished {finished}/{len(videos)}")
        progress_bar.value = finished / len(videos)
        progress_bar.update()

    print("Complete!")
    end = perf_counter()
    print(f"Took {end-start:.2f} seconds to reprocess {len(videos)} videos")

    progress_bar.value = 0.0
    progress_bar.color = ft.colors.TRANSPARENT
    progress_bar.update()


async def update_videos(yt_api, video_grid, progress_bar, progress_text):
    llm_handler = LLMHandler()

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
        if CANCEL_FLAG:
            break

        progress_text.value = f"Finding video ID's for {channel}"
        progress_text.update()
        recent_videos = await yt_api.get_recent_videos(channel)
        for video_id, video_title in recent_videos:
            if video_id in current_video_ids:
                current_title = db_handler.get_video_title(video_id)
                if video_title != current_title:
                    db_handler.update_title(video_id, video_title)
                    print(f"{video_id} was renamed: {current_title} -> {video_title}")
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

            video_categories = await llm_handler.categorize_video(
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
            for v in db_handler.get_video_grid_data():
                video_grid.controls.append(
                    VideoTile(data=v, tooltip_time=int(settings["app_tooltip_time"]))
                )
            video_grid.update()
        finished += 1
        progress_bar.value = finished / len(channels)
        progress_bar.update()
    print("Update complete")

    progress_bar.value = 0.0
    progress_bar.color = ft.colors.TRANSPARENT
    progress_bar.update()


async def main(page: ft.Page):
    # Connect to db file and youtube api
    db_handler = DBHandler()
    settings = db_handler.get_settings()
    # print(db_handler.get_uncategorized_videos())
    yt_api = YoutubeAPI()

    video_grid = ft.GridView(child_aspect_ratio=0.75, max_extent=300)

    feed_filters = []
    category_filters = []

    # I think this can be optimized when I turn the main page into its own object
    # Right now a majority of the time to re-render the video tile grid is because
    # it's having to set up a new db connection, re-query the full list, and re-generate
    # all 200 tiles. I think there's a lot of caching that could happen
    def update_video_grid():
        db = DBHandler()
        video_grid.controls.clear()
        video_grid.update()
        all_videos = db.get_video_grid_data()
        added = 0
        for video in all_videos:
            if len(feed_filters) > 0 and video["username"] not in feed_filters:
                continue
            if len(category_filters) > 0 and not all(
                [fc in video["categories"] for fc in category_filters]
            ):
                continue
            video_grid.controls.append(
                VideoTile(data=video, tooltip_time=int(settings["app_tooltip_time"]))
            )
            added += 1
            if added == 200:
                break

        video_grid.update()

    def filter_update(data, type, action):
        if action == "added":
            if type == "feed":
                feed_filters.append(data)
            else:
                category_filters.append(data)
        if action == "removed":
            if type == "feed":
                feed_filters.remove(data)
            else:
                category_filters.remove(data)

        update_video_grid()

    def clear_filters(_):
        feed_filters.clear()
        category_filters.clear()

        for tile in feeds.list_items.controls:
            tile.selected = False
        for tile in categories.list_items.controls:
            tile.selected = False

        feeds.update()
        categories.update()

        update_video_grid()

    # Create the side lists
    feeds = MyListWidget("Channels", "feed", filter_update, update_video_grid, yt_api)
    categories = MyListWidget(
        "Categories", "category", filter_update, update_video_grid
    )

    feed_list = db_handler.get_feed_full()
    for username in feed_list:
        feeds.add_item(username)

    category_list = db_handler.get_categories_full()
    for category in category_list:
        categories.add_item(category)

    left_side = ft.Column(
        [
            feeds,
            categories,
        ]
    )

    for video in db_handler.get_video_grid_data()[:200]:
        video_grid.controls.append(
            VideoTile(data=video, tooltip_time=int(settings["app_tooltip_time"]))
        )

    progress_bar = ft.ProgressBar(
        visible=True,
        value=0.0,
        expand_loose=True,
        expand=True,
        color=ft.colors.TRANSPARENT,
    )

    progress_text = ft.Text(
        "",
        expand_loose=True,
        expand=True,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    progress_indicator = ft.Column(
        [
            ft.Container(height=2),
            progress_bar,
            progress_text,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        tight=True,
        visible=False,
        spacing=0,
        run_spacing=0,
    )

    async def update_feeds_click(_):
        global RUNNING_TASK, CANCEL_FLAG
        if RUNNING_TASK is not None:
            if RUNNING_TASK == "update_feeds":
                print("Pressed again means Stop!")
                CANCEL_FLAG = True
                RUNNING_TASK = None
                feed_update_progress.visible = False
                progress_indicator.visible = False
                feed_update_button.icon = ft.icons.UPDATE
                feed_update_button.tooltip.message = "Fetch new videos from ALL feeds."
                page.update()
                return
            else:
                return

        feed_update_progress.visible = True
        progress_indicator.visible = True
        feed_update_button.icon = ft.icons.STOP
        feed_update_button.tooltip.message = "Cancel Feed Update."
        page.update()

        RUNNING_TASK = "update_feeds"
        CANCEL_FLAG = False

        await update_videos(yt_api, video_grid, progress_bar, progress_text)

        feed_update_progress.visible = False
        progress_indicator.visible = False
        feed_update_button.icon = ft.icons.UPDATE
        feed_update_button.tooltip.message = "Fetch new videos from ALL feeds."
        page.update()

    async def process_categories_click(_):
        global RUNNING_TASK, CANCEL_FLAG
        if RUNNING_TASK is not None:
            if RUNNING_TASK == "reproc_categories":
                print("Pressed again means Stop!")
                CANCEL_FLAG = True
                RUNNING_TASK = None
                proc_update_progress.visible = False
                progress_indicator.visible = False
                proc_update_button.icon = ft.icons.SMART_TOY
                proc_update_button.tooltip.message = (
                    "Reprocess categories on ALL videos."
                )
                page.update()
                return
            else:
                return

        proc_update_progress.visible = True
        progress_indicator.visible = True
        proc_update_button.icon = ft.icons.STOP
        proc_update_button.tooltip.message = "Cancel category reprocessing."
        page.update()

        RUNNING_TASK = "reproc_categories"
        CANCEL_FLAG = False

        await reprocess_all_categories(video_grid, progress_bar, progress_text)

        proc_update_progress.visible = False
        progress_indicator.visible = False
        proc_update_button.icon = ft.icons.SMART_TOY
        proc_update_button.tooltip.message = "Reprocess categories on ALL videos."
        page.update()

    feed_update_progress = ft.ProgressRing(
        width=26,
        height=26,
        top=7,
        left=7,
        stroke_width=2,
        color=ft.colors.YELLOW,
        visible=False,
    )

    feed_update_button = ft.IconButton(
        icon=ft.icons.UPDATE,
        on_click=update_feeds_click,
        expand_loose=False,
        expand=False,
        tooltip=ft.Tooltip(
            "Fetch new videos from ALL feeds.",
            wait_duration=int(settings["app_tooltip_time"]),
        ),
    )

    proc_update_progress = ft.ProgressRing(
        width=26,
        height=26,
        top=7,
        left=7,
        stroke_width=2,
        color=ft.colors.RED,
        visible=False,
    )

    proc_update_button = ft.IconButton(
        icon=ft.icons.SMART_TOY,
        on_click=process_categories_click,
        expand_loose=False,
        expand=False,
        tooltip=ft.Tooltip(
            "Reprocess categories on ALL videos.",
            wait_duration=int(settings["app_tooltip_time"]),
        ),
    )

    top_row = ft.Row(
        [
            ft.IconButton(
                icon=ft.icons.CLEAR,
                on_click=clear_filters,
                tooltip=ft.Tooltip(
                    "Clear all filters.",
                    wait_duration=int(settings["app_tooltip_time"]),
                ),
            ),
            ft.Stack(
                [
                    feed_update_progress,
                    feed_update_button,
                ],
                width=40,
                height=40,
            ),
            ft.Stack(
                [
                    proc_update_progress,
                    proc_update_button,
                ],
                width=40,
                height=40,
            ),
            ft.Container(
                progress_indicator,
                expand=True,
                expand_loose=True,
            ),
            ft.IconButton(
                icon=ft.icons.SETTINGS,
                on_click=lambda _: page.open(
                    ConfigPage(
                        (
                            page.window.width * 0.60
                            if (page.window.width > 800)
                            else page.window.width
                        ),
                        page.window.height,
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
    main_content = ft.Container(
        ft.Column(
            [
                top_row,
                ft.Container(
                    video_grid,
                    expand=True,
                    expand_loose=True,
                ),
            ]
        ),
        expand_loose=True,
        expand=True,
    )
    full_page_content = ft.Row(
        [left_side, main_content],
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    full_page_container = ft.Container(
        full_page_content, expand_loose=True, expand=True
    )
    page.add(full_page_container)
    page.update()

    # Set up for page resizing / the first page load where
    # things aren't quite initialized yet
    def on_resized(event: ft.WindowResizeEvent):
        left_side.width = 250
        left_side.height = event.height
        feeds.height = int(event.height * 0.675)
        feeds.list_items.height = feeds.height - 80
        categories.height = int(event.height * 0.3)
        categories.list_items.height = categories.height - 80
        main_content.height = feeds.height + categories.height + 10
        top_row.width = event.width - 250
        page.update()

    page.on_resized = on_resized

    # Development Window Positioning
    width = 925
    height = 1200
    page.window.left = 1375
    page.window.top = 0

    page.window.min_width = 800
    page.window.min_height = 600
    page.window.width = width
    page.window.height = height
    e = ft.WindowResizeEvent(
        ft.ControlEvent(
            target="main",
            name="main",
            data='{"width": %d, "height": %d}'
            % (page.window.width, page.window.height - 30),
            control=page,
            page=page,
        )
    )
    page.on_resized(e)


if __name__ == "__main__":
    ft.app(
        target=main,
        # assets_dir="assets",
    )
