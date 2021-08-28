import praw
import subprocess
from io import BytesIO
from PIL import Image
import easyocr
import numpy as np
import requests


SURE_COMMENT_TEMPLATE = """
The user who posted this TikTok is...

[{}](https://www.tiktok.com/{})

\u00a0

^^beep ^^boop ^^I'm ^^a ^^bot. ^^Contact ^^makeworld ^^if ^^needed.
""".strip()

UNSURE_COMMENT_TEMPLATE = """
The user who posted this TikTok is *probably*...

[{}](https://www.tiktok.com/{})

My link might be wrong, because I couldn't see the full name at the end of the video,
and had to try and find the floating name instead.

\u00a0

^^beep ^^boop ^^I'm ^^a ^^bot. ^^Contact ^^makeworld ^^if ^^needed.
""".strip()

TITLE_COMMENT_TEMPLATE = """
I detected one or more usernames in the title of this post! Here they are:

{}

\u00a0

^^beep ^^boop ^^I'm ^^a ^^bot. ^^Contact ^^makeworld ^^if ^^needed.

""".strip()

TITLE_AND_VIDEO_COMMENT_TEMPLATE = """
I detected one or more usernames in the title of this post! Here they are:

{}

Just in case, I also detected which user posted this TikTok using the video only:

[{}](https://www.tiktok.com/{})

\u00a0

^^beep ^^boop ^^I'm ^^a ^^bot. ^^Contact ^^makeworld ^^if ^^needed.
""".strip()


def np_multi_and(*args):
    result = args[0]
    for arr in args[1:]:
        # Chain all the ANDs
        result = np.logical_and(result, arr)
    return result


def download_video(url):
    subprocess.run(
        [
            "/usr/bin/env",
            "bash",
            "-c",
            f"~/.local/bin/yt-dlp -q -f 'bv*' --force-overwrites -o tmp/video {url}",
        ],
        check=True,
        timeout=10,
    )


def first_frame():
    proc = subprocess.run(
        [
            "/usr/bin/env",
            "bash",
            "-c",
            "ffmpeg -hide_banner -loglevel error -nostats -i tmp/video -c:v png -vframes 1 -f image2 -",
        ],
        check=True,
        capture_output=True,
    )

    stream = BytesIO(proc.stdout)
    img = Image.open(stream).convert("RGB")
    stream.close()
    return img


def last_frame():
    # Get frame count
    # https://stackoverflow.com/a/28376817
    proc = subprocess.run(
        [
            "/usr/bin/env",
            "bash",
            "-c",
            "ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 tmp/video",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    nframes = int(proc.stdout.strip())

    # Now extract that last frame using its number
    proc = subprocess.run(
        [
            "/usr/bin/env",
            "bash",
            "-c",
            f"ffmpeg -hide_banner -loglevel error -nostats -i tmp/video -vf \"select='eq(n,{nframes-1})'\" -c:v png -vframes 1 -f image2 -",
        ],
        check=True,
        capture_output=True,
    )

    stream = BytesIO(proc.stdout)
    img = Image.open(stream).convert("RGB")
    stream.close()
    return img


def preprocess_first_frame(img):
    # Only get left third, and then the top two-thirds of that
    img = img.crop((0, 0, int(img.width / 3), int(img.height / 3) * 2))

    return img

    # # HSV filter to only get the white text

    # # Saturation and value thresholds
    # # Out of a 100, then changed to 8-bit
    # # Old: 20, 77
    # # New: 20, 108 (out of 255)
    # MAX_SAT = int((30 / 100) * 255)
    # MIN_VAL = int((77 / 100) * 255)

    # hsv = np.asarray(img.convert("HSV"))
    # h = hsv[:, :, 0]
    # s = hsv[:, :, 1]
    # v = hsv[:, :, 2]

    # mask = np.logical_and(s < MAX_SAT, v > MIN_VAL)
    # # Invert mask so text will be black
    # mask = np.logical_not(mask)

    # return Image.fromarray(mask.astype("uint8") * 255)


def preprocess_last_frame(img):
    return img

    # # HSV filter to only get the white text

    # # Out of 255
    # MAX_SAT = 39

    # hsv = np.asarray(img.convert("HSV"))
    # s = hsv[:, :, 1]

    # mask = s < MAX_SAT
    # # Invert mask so text will be black
    # mask = np.logical_not(mask)

    # return Image.fromarray(mask.astype("uint8") * 255)


def clean_text(texts):
    for text in texts:
        if text.startswith("@"):
            # Model will sometimes miss the underscore
            return text.lower().replace(" ", "_")
        if text.startswith("TikTok @"):
            # Model will do this when reading the first frame text
            return text[len("TikTok ") :].lower().replace(" ", "_")


# Load model into memory
reader = easyocr.Reader(["en"], gpu=False)


def ocr(img):
    return reader.readtext(
        np.asarray(img),
        detail=0,
        allowlist="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456790_.@",
        paragraph=True,
    )


def tiktok_user_exists(username):
    """
    Returns a boolean for whether the provided TikTok username corresponds
    to a TikTok account. The username must start with the "@".
    """

    r = requests.get(
        f"https://www.tiktok.com/{username}",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:91.0) Gecko/20100101 Firefox/91.0"
        },
    )
    if r.status_code == 200:
        return True
    elif r.status_code == 404:
        return False

    raise Exception(f"Unexpected TikTok status code {r.status_code}")


def get_username_from_video(url):
    """
    Downloads the TikTok video and returns the text of the username, including the "@".

    The second return value is a boolean, indicating whether the last frame or
    first frame was used. The last frame (True) is much much more reliable,
    so the the first frame is only used when the username is cutoff in the last frame.

    If the first object returned is None the no username could be found.
    """

    download_video(url)
    img = preprocess_last_frame(last_frame())
    img.show()
    text = clean_text(ocr(img))

    if text is None or not tiktok_user_exists(text):
        # Username couldn't be found or didn't exist - maybe misread or cutoff
        # Try to find it with the floating logo in the first frame instead
        # This is much more error-prone
        img = preprocess_first_frame(first_frame())
        img.show()
        text = clean_text(ocr(img))

        if tiktok_user_exists(text):
            return text, False

        return None, False

    return text, True


def get_usernames_from_title(title):
    users = []

    for word in title.split():
        if word.startswith("@"):
            users.append(word)
    return users


def main():
    reddit = praw.Reddit("bot")
    subreddit = reddit.subreddit("TikTokCringe")

    for submission in subreddit.stream.submissions(skip_existing=True):

        print("https://old.reddit.com" + submission.permalink)

        if not submission.url.startswith("https://v.redd.it/"):
            # Ignore any spam links like YouTube that could cause a massive download
            # on the server
            continue

        skip = False
        for comment in submission.comments:
            if comment.author.name == "tiktok-link":
                # Bot has commented here before
                skip = True
                break

        if skip:
            continue

        title_usernames = get_usernames_from_title(submission.title)
        if len(title_usernames) > 0:
            # Generate markdown
            title_usernames_md = ""
            for username in title_usernames:
                title_usernames_md += (
                    f"[{username}](https://www.tiktok.com/{username}\n\n"
                )

        try:
            username, sure = get_username_from_video(submission.url)
        except Exception as e:
            # Log to stdout
            print(e)
            continue

        if len(title_usernames) > 0 and username is not None:
            tmpl = TITLE_AND_VIDEO_COMMENT_TEMPLATE
            tmpl = tmpl.format(title_usernames_md, username, username)
        elif len(title_usernames) > 0 and username is None:
            tmpl = TITLE_COMMENT_TEMPLATE
            tmpl = tmpl.format(title_usernames_md)
        elif username is not None and sure:
            tmpl = SURE_COMMENT_TEMPLATE
            tmpl = tmpl.format(username, username)
        elif username is not None and not sure:
            tmpl = UNSURE_COMMENT_TEMPLATE
            tmpl = tmpl.format(username, username)
        else:
            # username is None
            continue

        print(tmpl)
        submission.reply(tmpl)


if __name__ == "__main__":
    main()
