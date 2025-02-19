#!/usr/bin/env python3

import base64
import random
import re
import sys
import subprocess
import platform
import os

import httpx
from bs4 import BeautifulSoup 
from Cryptodome.Cipher import AES

try:
    import orjson as json
except ImportError:
    import json

MPV_EXECUTABLE = "mpv"

DEFAULT_MEDIA_REFERER = "https://membed.net"


def pad(data):
    return data + chr(len(data) % 16) * (16 - len(data) % 16)


def aes_encrypt(data: str, *, key, iv):
    return base64.b64encode(
        AES.new(key, AES.MODE_CBC, iv=iv).encrypt(pad(data).encode())
    )


def aes_decrypt(data: str, *, key, iv):
    return (
        AES.new(key, AES.MODE_CBC, iv=iv)
        .decrypt(base64.b64decode(data))
        .strip(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\x10")
    )

color = [  
    "\u001b[31m",
    "\u001b[32m",
    "\u001b[33m",
    "\u001b[34m",
    "\u001b[35m",
    "\u001b[36m",
    "\u001b[37m"
]

def map_shows(query: str) -> list:

    URL = f"https://imdb.com/find?q={query}&ref_=nv_sr_sm"

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:100.0) Gecko/20100101 Firefox/100.0"
        }

    with httpx.Client(follow_redirects=True) as client:
        res = client.get(URL, headers=headers)
    
    scode = res.status_code
    if scode == 200:
        pass
    elif scode == 404:
        print("QueryError: show not found")
    else:
        print(f"returned => {scode}")

    soup = BeautifulSoup(res.text, "html.parser")
    td = soup.find_all('td', attrs={'class': "result_text"})

    shows = list()
    for instance in list(td):

        show = re.search(
            r'<td class="result_text"> <a href="/title/([a-z0-9]{8,})/\?ref_=fn_al_tt_[0-9]{1,}"(.*)</td>',
            str(instance)
            )

        if show is not None:
            title_ = re.sub(
                r'(<(|/)small>|<(|/)br(|/)>|<(|/)a>|<(|/)span>|<(|/)i>|<|>)', 
                "", 
                str(show.group(2))
                )
            
            title_ = re.sub(r' - .*', "", title_)
            instance  = {'id': str(show.group(1)), 'name': title_}
            shows.append(instance)
    
    return shows


def show_info() -> dict:
    
    try:
        if len(sys.argv) == 1:
            query = input("Search: ")
            if query == "": 
                print("ValueError: no query parameter provided")
                exit(0)
        else:
            query = "".join(sys.argv[1:])

        shows = map_shows(query=query.replace(" ", "+"))
        
        for idx, info in enumerate(shows):
            color_idx = random.randint(0, len(color)-1) if idx >= len(color) else idx
            print(f'[{idx+1}] {color[color_idx]}{info["name"]}\u001b[0m')

        ask = int(input(": "))-1
        if(ask >= len(shows)):
            print("IndexError: index out of range.")
            exit(1)
            
    except ValueError:
        return shows[0]
    except KeyboardInterrupt:
        exit(0)

    return shows[ask] 


CONTENT_ID_REGEX = re.compile(r"streaming\.php\?id=([^&?/#]+)")

SECRET = b"25742532592138496744665879883281"
IV = b"9225679083961858"


ENCRYPT_AJAX_ENDPOINT = "https://membed.net/encrypt-ajax.php"
GDRIVE_PLAYER_ENDPOINT = "https://database.gdriveplayer.us/player.php"

show = show_info()
with httpx.Client() as client:

    try:
        content_id = CONTENT_ID_REGEX.search(
            client.get(
                GDRIVE_PLAYER_ENDPOINT,
                params={
                    "imdb": show['id'],
                },
            ).text
        ).group(1)
    except AttributeError:
        print("SupportError: can't play series and episodes")
        exit(0)


    content = json.loads(
        aes_decrypt(
            json.loads(
                client.get(
                    ENCRYPT_AJAX_ENDPOINT,
                    params={"id": aes_encrypt(content_id, key=SECRET, iv=IV).decode()},
                    headers={"x-requested-with": "XMLHttpRequest"},
                ).text
            )["data"],
            key=SECRET,
            iv=IV,
        )
    )

subtitles = (_.get("file") for _ in content.get("track", {}).get("tracks", []))

media = (content.get("source", []) or []) + (content.get("source_bk", []) or [])

for content_index, source in enumerate(media):
    print(f" > {content_index} / {source['label']} / {source['type']}")

if not media:
    raise RuntimeError("Could not find any media for playback.")

if len(media) > 1:
    try:
        while not (
                (user_selection := input("Take it or leave it, index: ")).isdigit()
            and (parsed_us := int(user_selection)) in range(content_index)
        ):
            print("Nice joke. Now you have to TRY AGAIN!!!")
        selected = media[parsed_us]
    except KeyboardInterrupt:
        exit(0)
else:
    selected = media[0]

def determine_path() -> str:
    
    plt = platform.system()

    if plt == "Windows":
        return f"C://Users//{os.getenv('username')}//Downloads"
    
    elif (plt == "Linux"):
        return f"/home/{os.getlogin()}/Downloads"
    
    elif (plt == "Darwin"):
        return f"/Users/{os.getlogin()}/Downloads"

    else:
        print("[!] Make an issue for your OS.")


def download(path: str = determine_path()):
    
    name = show['name']
    name = name.replace(" ", "-")
    name = name.replace("\"", "")
    
    args = [
        "aria2c",
        f"--referer={DEFAULT_MEDIA_REFERER}",
        f"--dir={path}",
        selected["file"]
    ]
    
    aria2c_process = subprocess.Popen(args)
    
    aria2c_process.wait()

    print(f"Downloaded at {path}")


def play():
    args = [
        MPV_EXECUTABLE,
        selected["file"],
        f"--referrer={DEFAULT_MEDIA_REFERER}",
        f"--force-media-title=Playing {show['name']}",
    ]
    args.extend(f"--sub-file={_}" for _ in subtitles)

    mpv_process = subprocess.Popen(args)

    mpv_process.wait()


def choice():
    print("~"*60)
    print("1. Play the movie.")
    print("2. Download the movie.")
    print("~"*60)
    
    ch = int(input("Enter your choice: "))

    while True:
        if ch == 1:
            play()
            break
        elif ch == 2:
            download()
            break
        else:
            print("Invalid choice")
            exit(0)

choice()
