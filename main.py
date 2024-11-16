import flet as ft

from ui.main_page import MainPage


async def main(page: ft.Page):
    # Set up initial window size
    page.window.min_width = 800
    page.window.min_height = 600
    page.window.width = 950
    page.window.height = 800
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

    # Add the main page to the application
    main_page = MainPage(page)
    page.on_resized = main_page.on_resized
    page.add(main_page)
    page.update()

    # Does a bit of a weird thing where I need to send a manual
    # resize event to get things to start in the right spots
    page.on_resized(e)


if __name__ == "__main__":
    ft.app(
        target=main,
    )
