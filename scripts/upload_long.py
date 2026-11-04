#!/usr/bin/env python3
"""Upload a finished long-form story (normal video, not a Short) to Bounce Bhai, set its custom thumbnail, and log it.

usage: python scripts/upload_long.py out/long_x.json
Only the workflow's publish=true path calls this. Title "<title> | <Language> Moral Story | Bounce Bhai", category
Film & Animation, default (audio) language = the story language, description with the moral, chapters (one per
scene) and hashtags, not made for kids. thumbnails.set needs a verified channel: a failure is a ::warning, not an error.
Appends {"format": "long_story", "lang": ...} to data/history.json and the theme to data/long_topics.json.
"""
import sys as _sys, traceback as _tb


def _gh_error(t, e, tb):
    _tb.print_exception(t, e, tb)
    print("::error title=upload_long::" + (type(e).__name__ + ": " + str(e)).replace("\n", " ")[:900], flush=True)


_sys.excepthook = _gh_error
import datetime, json, os, sys

from googleapiclient.http import MediaFileUpload

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yt_client import youtube   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG_NAME = {"te": "Telugu", "hi": "Hindi", "en": "English"}
MORAL = {"te": "నీతి", "hi": "सीख", "en": "Moral"}
CHAPTERS = {"te": "అధ్యాయాలు", "hi": "अध्याय", "en": "Chapters"}
SUB = {"te": "🔔 ప్రతి రోజు ఒక కొత్త కథ కోసం సబ్‌స్క్రైబ్ చేయండి 👉 https://www.youtube.com/@bouncebhaiofficial?sub_confirmation=1",
       "hi": "🔔 रोज़ एक नई कहानी के लिए सब्सक्राइब करें 👉 https://www.youtube.com/@bouncebhaiofficial?sub_confirmation=1",
       "en": "🔔 Subscribe for a new moral story every day 👉 https://www.youtube.com/@bouncebhaiofficial?sub_confirmation=1"}
FOOT = {"te": "కోడ్‌తో గీసిన నిజమైన 2D కార్టూన్ యానిమేషన్ (AI చిత్రాలు కాదు).",
        "hi": "कोड से बनाया गया असली 2D कार्टून एनिमेशन (AI तस्वीरें नहीं)।",
        "en": "Real 2D cartoon animation drawn with code (no AI slideshow images)."}
ASK = {"te": "ఈ కథ మీకు నచ్చిందా? మీకు నచ్చిన పాత్ర ఎవరు? కామెంట్ చేయండి 👇",
       "hi": "आपको यह कहानी कैसी लगी? आपका पसंदीदा किरदार कौन है? कमेंट करें 👇",
       "en": "Did you like this story? Who was your favourite character? Comment below 👇"}
HASH = {"te": "#TeluguStories #MoralStories #TeluguKathalu #Cartoon #BounceBhai",
        "hi": "#HindiKahani #MoralStories #HindiStories #Cartoon #BounceBhai",
        "en": "#MoralStories #EnglishStories #Cartoon #Kahani #BounceBhai"}


def ts(sec):
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def chapters(story):
    out, last = [], -99
    for i, sc in enumerate(story["scenes"]):
        t = 0 if i == 0 else sc["start"]
        if t - last < 12:
            continue
        name = (sc.get("chapter") or "").strip() or f"Part {i + 1}"
        out.append(f"{ts(t)} {name}")
        last = t
    return out if len(out) >= 3 else []


def build(story):
    lang = story.get("lang", "hi")
    suffix = f" | {LANG_NAME[lang]} Moral Story | Bounce Bhai"
    title = story["title"].strip()
    if len(title) + len(suffix) > 100:
        title = title[:100 - len(suffix) - 1].rstrip() + "…"
    chap = chapters(story)
    desc = [story.get("description", "").strip(), "", f"✨ {MORAL[lang]}: {story['moral']}", ""]
    if chap:
        desc += [f"⏱️ {CHAPTERS[lang]}:"] + chap + [""]
    desc += [SUB[lang], FOOT[lang], "", HASH[lang]]
    tags = list(dict.fromkeys((story.get("tags") or []) + ["moral story", "moral stories", "kahani", "cartoon",
                                                             "animated story", f"{LANG_NAME[lang].lower()} stories", "bounce bhai"]))
    while len(",".join(tags)) > 480:
        tags.pop()
    body = {"snippet": {"title": title + suffix, "description": "\n".join(desc)[:4900], "tags": tags, "categoryId": "1",
                        "defaultLanguage": lang, "defaultAudioLanguage": lang},
            "status": {"privacyStatus": os.environ.get("YT_PRIVACY", "public"), "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": False, "embeddable": True}}
    return body


def main(path):
    story = json.load(open(path, encoding="utf-8"))
    video = story.get("video") or path[:-5] + ".mp4"
    body = build(story)
    print("title:", body["snippet"]["title"])
    yt = youtube(check_channel=True)
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(video, mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024))
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st:
            print(f"  upload {st.progress() * 100:.0f}%", flush=True)
    vid = resp["id"]
    print(f"::notice title=uploaded::https://youtu.be/{vid}", flush=True)
    thumb = story.get("thumb")
    if thumb and os.path.exists(thumb):
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumb, mimetype="image/jpeg")).execute()
            print("custom thumbnail set")
        except Exception as e:
            print(f"::warning title=thumbnail::custom thumbnail not set (channel may need phone verification): {str(e)[:300]}")
    try:
        yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {
            "snippet": {"textOriginal": f"{ASK[story.get('lang', 'hi')]}\n✨ {story['moral']}"}}}}).execute()
    except Exception as e:
        print("comment skipped:", str(e)[:200])
    story["video_id"] = vid
    json.dump(story, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    hp = os.path.join(ROOT, "data", "history.json")
    try:
        hist = json.load(open(hp, encoding="utf-8"))
    except Exception:
        hist = []
    hist.append({"date": now, "title": story["title"], "video_id": vid, "format": "long_story", "lang": story.get("lang"),
                 "topic": story.get("theme"), "yt_title": body["snippet"]["title"], "duration": story.get("duration")})
    with open(hp, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1); f.write("\n")
    tp = os.path.join(ROOT, "data", "long_topics.json")
    try:
        topics = json.load(open(tp, encoding="utf-8"))
    except Exception:
        topics = []
    topics.append({"date": now, "lang": story.get("lang"), "theme": story.get("theme"), "seed": story.get("seed_theme"),
                   "title": story["title"], "video_id": vid})
    with open(tp, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=1); f.write("\n")


if __name__ == "__main__":
    main(sys.argv[1])
