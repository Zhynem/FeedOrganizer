import json
import sqlite3

DB_FILE = "data.db3"

default_system_prompt = """You are an assistant AI that returns a category classifications from video information.
Please output a single line Python list object
Example:
%s

Do not wrap the object in markdown or use newlines and whitespace.
Do not give any additional commentary or warnings, if output is not formated as described here it will cause crashes.
Do not make up your own categories, only use the following categories: %s
If words from the title are present in an available category, include it in the response.
Always determine if the video is Educational or Entertainment and include the category.
NEVER classify a video as both Educational and Entertainment, pick one or the other depending on relevance.
Assign Educational if the video aims to impart some kind of real-world applicable knowledge.
Some examples:
  - Showing off something that was created, while it could contain educational moments, would be considered Entertainment focused.
  - Describing how certain protocols work, even if done in an exciting and engaging way, would be considered Educational focused.
  - Titles with humor like 'I Turned Myself Into a Human Battery', while containing educational moments, would be considered Entertainment focused.
Next determine relevance to the remaining categories.
Use at most 2 more categories.
This means you should return a list containing between 1 and 3 relevant categories.
Arrange your return list by having the most relevant categories at the beginning of the list.
"""
default_user_prompt = """Most frequent words in the transcript:
```
%s
```

Most frequent bigrams in the transcript (may be empty):
```
%s
```

Video Title: "%s"

As a reminder, these are the categories to use in classification: %s
"""
default_custom_stop_words = [
    "got",
    "uh",
    "like",
    "right",
    "let",
    "actually",
    "know",
    "yeah",
    "way",
    "get",
    "okay",
    "um",
    "kind",
    "pretty",
    "think",
    "x",
    "going",
    "good",
    "would",
    "see",
    "also",
    "really",
    "could",
    "well",
    "become",
    "lot",
    "well",
    "oh",
]


class DBHandler:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE)
        self.cur = self.conn.cursor()
        self.initialize()

    def initialize(self):
        # Check if schema exists
        self.cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='feeds';"
        )
        if not self.cur.fetchone():
            print("Creating schema")
            self.create_schema()
            self.conn.commit()

    def create_schema(self):
        print("Creating tables")
        create_tables_queries = [
            "create table settings (setting TEXT PRIMARY KEY, setting_value ANY NOT NULL)",
            "CREATE TABLE IF NOT EXISTS feeds (username TEXT PRIMARY KEY, display_name TEXT)",
            "CREATE TABLE IF NOT EXISTS categories (llm_category TEXT PRIMARY KEY, display_category TEXT NOT NULL UNIQUE)",
            "CREATE TABLE IF NOT EXISTS video_categories (video_id TEXT, llm_category TEXT, FOREIGN KEY (video_id) REFERENCES videos(video_id), FOREIGN KEY (llm_category) REFERENCES categories(llm_category))",
            "CREATE TABLE IF NOT EXISTS videos (video_id TEXT PRIMARY KEY NOT NULL UNIQUE, username TEXT, url TEXT NOT NULL, title TEXT NOT NULL, upload_date DATE, thumbnail BLOB, tags TEXT, description TEXT, transcript TEXT, FOREIGN KEY (username) REFERENCES feeds(username) ON DELETE CASCADE)",
        ]
        for query in create_tables_queries:
            self.cur.execute(query)
        self.conn.commit()
        print("Done")

        # Add default settings
        print("Adding default settings")
        self.put_setting("app_confirm_delete", "True")
        self.put_setting("app_tooltip_time", "1000")
        self.put_setting("yt_api_key", "Fill in this value...")
        self.put_setting("ollama_model", "qwen2.5-coder:7b")
        self.put_setting("ollama_ctx_size", "1200")
        self.put_setting("ollama_system_prompt", default_system_prompt)
        self.put_setting("ollama_user_prompt", default_user_prompt)
        self.put_setting(
            "ollama_custom_stop_words", json.dumps(default_custom_stop_words)
        )
        print("Done")

    def add_feed(self, username, display_name):
        self.cur.execute(
            "INSERT INTO feeds (username, display_name) VALUES (?, ?)",
            (username, display_name),
        )
        self.conn.commit()

    def add_category(self, llm_category, display_category):
        self.cur.execute(
            "INSERT INTO categories (llm_category, display_category) VALUES (?, ?)",
            (
                llm_category,
                display_category,
            ),
        )
        self.conn.commit()

    def add_video(
        self,
        video_id,
        feed_id,
        url,
        title,
        upload_date,
        thumbnail,
        tags,
        description,
        transcript,
        categories,
    ):
        # Insert video
        self.cur.execute(
            "INSERT INTO videos (video_id, username, url, title, upload_date, thumbnail, tags, description, transcript) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                video_id,
                feed_id,
                url,
                title,
                upload_date,
                thumbnail,
                tags,
                description,
                transcript,
            ),
        )
        # Insert video categories
        for category in categories:
            self.cur.execute(
                "INSERT INTO video_categories (video_id, llm_category) VALUES (?, ?)",
                (video_id, category),
            )
        self.conn.commit()

    def get_uncategorized_videos(self):
        self.cur.execute(
            """
            SELECT v.video_id, v.username, v.url, v.title, v.upload_date, v.thumbnail, v.tags, v.description, v.transcript
            FROM videos v
            LEFT JOIN video_categories vc ON v.video_id = vc.video_id
            WHERE vc.video_id IS NULL;
            """
        )

        # Fetch all results from the executed query
        rows = self.cur.fetchall()

        # Define a list to hold the formatted video data
        uncategorized_videos = []

        # Iterate over each row and convert it to a dictionary
        for row in rows:
            video_dict = {
                "video_id": row[0],
                "username": row[1],
                "url": row[2],
                "title": row[3],
                "upload_date": row[4],
                "thumbnail": row[5],
                "tags": row[6],
                "description": row[7],
                "transcript": row[8],
            }
            uncategorized_videos.append(video_dict)

        # Return the list of dictionaries
        return uncategorized_videos

    def bulk_add_video_category(self, data):
        for item in data:
            video_id, llm_category = item
            # print(f"Adding item {video_id} | {llm_category}")
            self.cur.execute(
                "INSERT INTO video_categories (video_id, llm_category) VALUES (?, ?)",
                (video_id, llm_category),
            )
        self.conn.commit()

    def truncate_video_categories(self):
        self.cur.execute("DELETE FROM video_categories;")
        self.conn.commit()

    def delete_feed(self, username):
        # Delete videos associated with the feed
        self.cur.execute(
            "DELETE FROM videos WHERE username = ?",
            (username,),
        )
        # Delete the feed itself
        self.cur.execute("DELETE FROM feeds WHERE username = ?", (username,))
        self.conn.commit()

    def delete_category(self, llm_category):
        # Delete video categories associated with the category
        self.cur.execute(
            "DELETE FROM video_categories WHERE llm_category = ?", (llm_category,)
        )
        # Delete the category itself
        self.cur.execute(
            "DELETE FROM categories WHERE llm_category = ?", (llm_category,)
        )
        self.conn.commit()

    def get_channel_usernames(self):
        self.cur.execute(
            "SELECT username FROM feeds",
        )
        return [c[0] for c in self.cur.fetchall()]

    def get_feed_display(self):
        self.cur.execute("SELECT display_name FROM feeds ORDER BY display_name ASC")
        return [f[0] for f in self.cur.fetchall()]

    def get_feed_full(self):
        self.cur.execute(
            "SELECT username, display_name FROM feeds ORDER BY display_name ASC"
        )
        return [(i[0], i[1]) for i in self.cur.fetchall()]

    def get_categories_display(self):
        self.cur.execute(
            "SELECT display_category FROM categories ORDER BY display_category ASC",
        )
        return [c[0] for c in self.cur.fetchall()]

    def get_categories_full(self):
        self.cur.execute(
            "SELECT llm_category, display_category FROM categories ORDER BY display_category ASC"
        )
        return [(c[0], c[1]) for c in self.cur.fetchall()]

    def get_llm_categories_list(self):
        self.cur.execute("SELECT llm_category FROM categories")
        return [c[0] for c in self.cur.fetchall()]

    def get_full_video_data(self):
        self.cur.execute(
            "SELECT video_id, url, title, upload_date, thumbnail, tags, description, transcript FROM videos"
        )
        return [
            {
                "id": v[0],
                "url": v[1],
                "title": v[2],
                "upload_date": v[3],
                "thumbnail": v[4],
                "tags": v[5],
                "description": v[6],
                "transcript": v[7],
            }
            for v in self.cur.fetchall()
        ]

    def update_title(self, video_id, new_title):
        self.cur.execute(
            "UPDATE videos SET title = ? WHERE video_id = ?", (new_title, video_id)
        )
        self.conn.commit()

    def video_grid_query_construct(self, feed_filters, category_filters, limit):
        query = """
                SELECT v.video_id, f.username, f.display_name, v.url, v.title, v.upload_date, v.thumbnail, c.display_category
                FROM videos v
                JOIN video_categories vc ON v.video_id = vc.video_id
                JOIN categories c ON vc.llm_category = c.llm_category
                JOIN feeds f ON v.username = f.username
            """

        # Construct the WHERE clause based on feed_filters and category_filters
        where_clauses = []

        if feed_filters:
            feed_placeholders = ", ".join(["?"] * len(feed_filters))
            where_clauses.append(f"f.username IN ({feed_placeholders})")

        if category_filters:
            category_placeholders = ", ".join(["?"] * len(category_filters))
            # Use a subquery to ensure each video matches all categories
            where_clauses.append(
                f"""
                    v.video_id IN (
                        SELECT vc.video_id
                        FROM video_categories vc
                        WHERE vc.llm_category IN ({category_placeholders})
                        GROUP BY vc.video_id
                        HAVING COUNT(DISTINCT vc.llm_category) = ?
                    )
                """
            )

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY v.upload_date DESC LIMIT ?;"

        # Prepare the parameters for the query
        params = []
        if feed_filters:
            params.extend(feed_filters)
        if category_filters:
            params.extend(category_filters)
            params.append(
                len(category_filters)
            )  # Add the count of categories for the HAVING clause
        params.append(limit)

        return query, tuple(params)

    def get_video_grid_data(self, feed_filters, category_filters, limit=100):
        # Thank you qwen2.5-coder:32b for giving me the function to construct a query
        # that or's the feeds and and's the categories
        query, params = self.video_grid_query_construct(
            feed_filters, category_filters, limit
        )
        self.cur.execute(query, params)
        results = self.cur.fetchall()

        videos = []
        video_dict = {}
        for row in results:
            (
                video_id,
                username,
                display_name,
                url,
                title,
                upload_date,
                thumbnail,
                category,
            ) = row
            if video_id not in video_dict:
                video_dict[video_id] = {
                    "id": video_id,
                    "url": url,
                    "username": username,
                    "display_name": display_name,
                    "title": title,
                    "upload_date": upload_date,
                    "thumbnail": thumbnail,
                    "categories": [],
                }
            video_dict[video_id]["categories"].append(category)

        for _, video in video_dict.items():
            videos.append(video)

        return videos

    def get_video_transcript(self, video_id):
        self.cur.execute(
            "SELECT transcript FROM videos WHERE video_id = ?", (video_id,)
        )
        return self.cur.fetchone()[0]

    def delete_video_categories(self, video_id):
        self.cur.execute("DELETE FROM video_categories WHERE video_id = ?", (video_id,))
        self.conn.commit()

    def get_video_title(self, video_id):
        self.cur.execute("SELECT title FROM videos WHERE video_id = ?", (video_id,))
        return self.cur.fetchone()[0]

    def get_current_video_ids_and_titles(self):
        self.cur.execute("SELECT video_id, title FROM videos;")
        results = self.cur.fetchall()
        return [c[0] for c in results], [c[1] for c in results]

    def put_setting(self, name, value):
        self.cur.execute(
            "INSERT INTO settings (setting, setting_value) VALUES (?, ?) ON CONFLICT(setting) DO UPDATE SET setting_value = excluded.setting_value;",
            (name, value),
        )
        self.conn.commit()

    def get_settings(self):
        self.cur.execute("SELECT setting, setting_value FROM settings")
        return {i[0]: i[1] for i in self.cur.fetchall()}
