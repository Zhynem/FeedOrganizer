# Install:
- `python3 -m venv ./venv`
- `source ./venv/bin/activate`
- `pip install -r requirements.txt`
- `playwright install`
- `flet run main.py`

# Setup API key:
Go to https://cloud.google.com and sign up or sign in, create a project (I called mine FeedOrganizer)
- Inside the project click on the 'APIs & Services button'
- Click 'Enable APIs and Services'
- Add the 'Youtube Data API v3'
- Then go to 'Credentials'
- Create Credentials
- Create the API key
- Edit API key and limit it to just the Youtube Data API v3 service
- Copy down the value and add it to the settings page
- And boom, ya done :D