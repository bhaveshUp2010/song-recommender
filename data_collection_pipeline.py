import requests
import pandas as pd
from flask import Flask, request,session
import os
from dotenv import load_dotenv

DATA_DIR = "/data" if os.getenv("RAILWAY_ENVIRONMENT") else "./data"
os.makedirs(DATA_DIR, exist_ok=True)

TOKENS_FILE = os.path.join(DATA_DIR,"user_tokens.csv")
INTERACTION_FILE_TEMPLATE = os.path.join(DATA_DIR, "user_interactions_{user_id}.csv")
load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URL = os.getenv("REDIRECT_URL")

def get_auth_url():
    scope = "user-top-read user-library-read playlist-read-private user-read-recently-played"
    scope = scope.replace(" ", "%20")
    url = (
        "https://accounts.spotify.com/authorize"
        "?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URL}"
        f"&scope={scope}"
    )
    return url


def get_jwt_tokens(auth_code):
    url = "https://accounts.spotify.com/api/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": auth_code,
        "redirect_uri": REDIRECT_URL,
        "client_secret": CLIENT_SECRET
    }
    res = requests.post(url=url, data=payload).json()
    return res["access_token"], res["refresh_token"]


def refresh_access_token(refresh_token):
    url = "https://accounts.spotify.com/api/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    res = requests.post(url=url, data=payload).json()
    return res["access_token"]


def spotify_get(endpoint, token, params=None):
    headers = {"Authorization": f"Bearer {token}"}
    endpoint = endpoint.lstrip("/")
    url = f"https://api.spotify.com/v1/{endpoint}"
    res = requests.get(url=url, headers=headers, params=params)
    return res.json()


def get_recently_played(token, user_id):
    data = spotify_get("me/player/recently-played", token, {"limit": 50})

    tracks = []
    for t in data.get("items", []):
        track = t.get("track")
        if not track:
            continue

        tracks.append({
            "user_id": user_id,
            "song_id": track["id"],
            "song_name": track["name"],
            "artist": track["artists"][0]["name"],
            "isrc": track["external_ids"].get("isrc", None),
            "release_date": track["album"]["release_date"],
            "song_popularity": track.get("popularity"),
            "duration_ms": track.get("duration_ms"),
            "rating_source": "recently_played",
            "score": 3
        })

    return tracks


def get_saved_songs(token, user_id):
    data = spotify_get("me/tracks", token, {"limit": 50})

    tracks = []
    for t in data.get("items", []):
        track = t.get("track")
        if not track:
            continue

        tracks.append({
            "user_id": user_id,
            "song_id": track["id"],
            "song_name": track["name"],
            "artist": track["artists"][0]["name"],
            "isrc": track["external_ids"].get("isrc", None),
            "release_date": track["album"]["release_date"],
            "song_popularity": track.get("popularity"),
            "duration_ms": track.get("duration_ms"),
            "rating_source": "saved_songs",
            "score": 4
        })

    return tracks


def get_top_tracks(token, user_id):
    data = spotify_get("me/top/tracks", token, {"limit": 50})

    tracks = []
    for t in data.get("items", []):
        tracks.append({
            "user_id": user_id,
            "song_id": t["id"],
            "song_name": t["name"],
            "artist": t["artists"][0]["name"],
            "isrc": t["external_ids"].get("isrc", None),
            "release_date": t["album"]["release_date"],
            "song_popularity": t.get("popularity"),
            "duration_ms": t.get("duration_ms"),
            "rating_source": "top_track",
            "score": 5
        })

    return tracks


def get_playlist_tracks(token, user_id):
    playlists = spotify_get("me/playlists", token).get("items", [])
    all_tracks = []

    for p in playlists:
        playlist_id = p["id"]
        playlist_tracks = spotify_get(f"playlists/{playlist_id}/tracks", token).get("items", [])

        for t in playlist_tracks:
            track = t.get("track")
            if not track:
                continue

            all_tracks.append({
                "user_id": user_id,
                "song_id": track["id"],
                "song_name": track["name"],
                "artist": track["artists"][0]["name"],
                "isrc": track["external_ids"].get("isrc", None),
                "release_date": track["album"]["release_date"],
                "song_popularity": track.get("popularity"),
                "duration_ms": track.get("duration_ms"),
                "rating_source": "playlist",
                "score": 3
            })

    return all_tracks


app = Flask(__name__)

app.secret_key = os.getenv("FLASK_APP_SECRET")

@app.route("/")
def hello():
    return """
    <h1>Hello, Please give some data </h1>
    <p><a href="/login">Go to /login to connect Spotify</a></p>
    """


@app.route("/login")
def login():
    return f"<a href='{get_auth_url()}'>Login to spotify</a>"


@app.route("/callback")
def callback():
    auth_code = request.args.get("code")
    access_token, refresh_token = get_jwt_tokens(auth_code)

    profile = spotify_get("/me", access_token)
    session["user_id"] = profile["id"]
    session["refresh_token"] = refresh_token
    user_id = session["user_id"]

    # print("User:", user_id)
    # print("Refresh Token:", refresh_token)

    # with open("user_tokens.csv", "a") as f:
    #     f.write(f"{user_id}, {refresh_token}\n")
    #     f.close()
    # print("refresh token saved")

    if not os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "w") as f:
            f.write("user_id,refresh_token\n")
    with open(TOKENS_FILE, "a") as f:
        f.write(f"{user_id},{refresh_token}\n")
    print("User's refresh token saved")

    interactions = []
    interactions += get_top_tracks(access_token, user_id)
    interactions += get_saved_songs(access_token, user_id)
    interactions += get_recently_played(access_token, user_id)
    interactions += get_playlist_tracks(access_token, user_id)

    df = pd.DataFrame(interactions).drop_duplicates(subset=["user_id", "song_id", "rating_source"])
    
    # df.to_csv(f"user_interactions_{user_id}.csv", index=False)
    # print("Saved user interaction data")

    interactions_file = INTERACTION_FILE_TEMPLATE.format(user_id = user_id)

    if os.path.exists(interactions_file):
        df.to_csv(interactions_file, mode="a", index=False, header= False)
    else:
        df.to_csv(interactions_file, index= False, header= True)
    print("Saved user interaction Data")

    return "<h1>Data collected! Check your CSV files 🎧</h1> <a href='/'>home</a>"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000)) 
    app.run(host="0.0.0.0", port=port)