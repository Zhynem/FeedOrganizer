import json
from googleapiclient.discovery import build
import html
from langchain_community.document_loaders import YoutubeLoader
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from middleware.sqlite_handler import DBHandler


class YoutubeAPI:
    def __init__(self):
        db_handler = DBHandler()
        self.API_KEY = db_handler.get_settings()["yt_api_key"]

        self.youtube = build("youtube", "v3", developerKey=self.API_KEY)

        self.pm = async_playwright()
        self.p = None
        self.browser = None
        self.browser_context = None

    async def get_recent_videos(self, username):
        # Set up the URL to the channels video page
        url = f"https://www.youtube.com/@{username}/videos"

        if self.browser_context is None:
            print("Creating reusable headless browser")
            self.p = await self.pm.start()
            self.browser = await self.p.chromium.launch(headless=True)
            print("Setting up browser context")
            self.browser_context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15"
            )

        # Get the page
        print("Getting page")
        page = await self.browser_context.new_page()
        print("Getting URL")
        await page.goto(url)

        # There is a div with `id="contents"` that contains all the videos
        # Wait for that to appear
        print("Waiting for contents to render")
        await page.wait_for_selector("#contents")

        # Return the fully rendered HTML and close the headless browser
        print("Retrieving fully rendered html")
        rendered_html = await page.content()

        # Parse the rendered HTML to find all the video IDs to return them
        soup = BeautifulSoup(rendered_html, "html.parser")

        await page.close()

        rich_items = soup.find_all("a", id="video-title-link")
        video_ids = []
        for item in rich_items:
            # Comes in the format `href="watch?v=VideoID"` as of Nov. 12, 2024.
            # I imagine this is subject to change at the whims of YouTube
            video_id = item.get("href").split("v=")[-1]
            video_title = html.unescape(item.get("title"))
            video_ids.append((video_id, video_title))

        return video_ids

    def get_transcript(self, url):
        # Max of 3 retries to get transcript
        for _ in range(3):
            try:
                transcript = YoutubeLoader.from_youtube_url(
                    url,
                    add_video_info=False,
                    language=["en", "en_auto"],
                    translation="en",
                ).load()
                if len(transcript) == 0:
                    return ""

                ft = transcript[0].page_content
                if len(ft) == 0:
                    return ""

                return ft
            except:
                continue

    def get_video_details(self, video_id):
        request = self.youtube.videos().list(part="snippet,contentDetails", id=video_id)
        response = request.execute()

        if len(response["items"]) == 0:
            print("Error: No video data available!!")
            return None

        if len(response["items"]) > 1:
            print(
                "Error: Too much video data returned? How is there more than one video with the same id?!?"
            )
            return None

        vid_data = None
        try:
            for item in response["items"]:
                if item["kind"] == "youtube#video":
                    video_id = item["id"]
                    duration = item["contentDetails"]["duration"]

                    # # Try and filter out any shorts (they can be up to 3 minutes long)
                    # if isodate.parse_duration(duration).seconds < 180:
                    #     print("Video too short, returning None")
                    #     return None

                    video_title = html.unescape(item["snippet"]["title"])
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    video_thumbnail = item["snippet"]["thumbnails"]["medium"]["url"]
                    video_upload_date = item["snippet"]["publishedAt"]
                    video_tags = item["snippet"].get("tags", [])
                    video_description = html.unescape(item["snippet"]["description"])

                    vid_data = {
                        "id": video_id,
                        "title": video_title,
                        "url": video_url,
                        "thumbnail": video_thumbnail,
                        "upload_date": video_upload_date,
                        "tags": json.dumps(video_tags),
                        "description": video_description,
                        "transcript": self.get_transcript(video_url),
                    }

            return vid_data
        except Exception as e:
            print("Exception retrieving video details")
            print(e)
            print(video_id)
            print(response)
            print()
            print()
