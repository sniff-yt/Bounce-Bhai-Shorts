"""Acting for the long-form cartoons: what every character DOES on every line, and how it moves.

1. assign_beats(story): reads each line's text (te / hi / en keyword stems, timed with the TTS word boundaries), the
   writer's `action` field and the emotion, and gives every line one to three timed ACTION BEATS
   (call out, give, count money, eat, scratch head, look around, stomp ...). Narrator lines get an `actor` (the
   character they talk about, by target or by name) so the narration SHOWS what it describes.
2. ACTIONS: a keyframed animation library. Each action is a short timeline of arm targets (out, down relative to the
   shoulder, like long2d.GEST), hand shapes (open / point / fist / cup / pinch) and body offsets (lean, dip, head
   tilt, head turn, gaze, hip shift, foot lift, hop), with optional looping parts (a call repeated, coins counted) and
   oscillations (shaking hands, sobbing shoulders). evaluate() samples it with smooth (eased) in-betweens.
3. Talk + listen choreography helpers: speaking gestures change on stressed words (every ~1-1.6 s), listeners cycle
   through reaction poses and nod.
"""
import math
import re

# ============================================================================================ keywords -> actions
# (action, {lang: [stems]}). First match per word wins; the list order is the priority.
KW = [
    ("burn", {"te": ["కాలిపోతు", "కాలుతున్న", "చేతులు కాల", "మంటగా", "వేడెక్కి", "వేడిగా ఉంది"], "hi": ["जल रहे", "जल गया", "बहुत गरम", "गरम है"],
              "en": ["burning", "so hot", "it's hot", "burns"]}),
    ("call_out", {"te": ["కేకలు", "కేక ", "అరుస్త", "అరిచా", "అరిచి", "రండి రండి", "రండి పిల్లలు", "గట్టిగా పిలు", "పిలుస్త"],
                  "hi": ["चिल्ला", "आओ आओ", "आइए आइए", "आवाज़ लगा", "पुकार"], "en": ["shout", "calling out", "come, come", "come one"]}),
    ("count_money", {"te": ["డబ్బులు లెక్క", "లెక్కపెట్ట", "సంపాదించ", "గల్లా", "డబ్బులు కుప్ప", "డబ్బు", "డబ్బులు", "రూపాయ"],
                     "hi": ["गिन", "कमाई", "कमाया", "पैसे", "रुपये", "रुपए"], "en": ["count", "earned", "money", "rupees", "coins"]}),
    ("give", {"te": ["ఇదిగోండి", "ఇదిగో", "తీసుకోండి", "తీసుకో", "ఇస్తాను", "ఇచ్చాడు", "ఇచ్చింది", "ఇచ్చాను", "ఇవ్వండి"],
              "hi": ["ये लो", "यह लो", "लीजिए", "ले लो", "दे दिया", "दिया", "देता हूँ", "दूँगा"], "en": ["here you go", "take this", "here,", "gave", "give"]}),
    ("take", {"te": ["తీసేసు", "తీసుకున్నా", "లాక్కు", "పట్టుకోగానే", "పట్టుకున్న", "దొంగిలించ", "ఎత్తుకెళ్ళ"],
              "hi": ["छीन", "ले लिया", "उठा लिया", "चुरा", "पकड़ा"], "en": ["took", "grab", "snatch", "stole", "picked up"]}),
    ("eat", {"te": ["తిను", "తింటా", "తిన్నా", "తింటే", "రుచి"], "hi": ["खाओ", "खा ", "खाया", "खाते", "स्वाद"],
             "en": ["eat", "ate", "tasty", "delicious"]}),
    ("drink", {"te": ["తాగు", "తాగండి", "తాగా", "తాగి"], "hi": ["पियो", "पिया"], "en": ["drink", "sip"]}),
    ("cry", {"te": ["ఏడుస్త", "ఏడ్చ", "ఏడుపు", "కన్నీళ్ళు", "కన్నీరు"], "hi": ["रो ", "रोने", "रोया", "आँसू"], "en": ["cry", "cried", "tears", "sob"]}),
    ("laugh", {"te": ["నవ్వుకుంటు", "నవ్వుతు", "నవ్వా", "నవ్వు", "హహ", "హా హా"], "hi": ["हँस", "हंस", "हा हा"], "en": ["laugh", "haha", "giggl"]}),
    ("stomp", {"te": ["నోరు మూయ్", "కోపంగా", "కోపం", "పో!", "వెళ్ళు!", "నోర్మూసుకో"], "hi": ["गुस्सा", "चुप रहो", "चुप!", "भाग जाओ"],
               "en": ["angry", "shut up", "get lost", "go away"]}),
    ("sneak", {"te": ["ఎవరూ చూడకుండా", "మెల్లగా అడుగు", "మెల్లగా", "నక్కి", "దొంగచాటు", "చప్పుడు చేయకుండా"],
               "hi": ["चुपके", "धीरे धीरे", "दबे पाँव", "छुप"], "en": ["sneak", "quietly", "tiptoe", "nobody sees"]}),
    ("look_around", {"te": ["చుట్టూ", "అటు ఇటు", "అటూ ఇటూ", "ఎక్కడ ఉంది", "కనిపించడం లేదు", "వెతుకు"],
                     "hi": ["इधर उधर", "चारों ओर", "कहाँ है", "ढूंढ", "नहीं दिख"], "en": ["around", "where is", "look for", "search"]}),
    ("sprinkle", {"te": ["చల్లాడు", "చల్లా", "చల్లి", "పోశాడు", "వేశాడు", "కలిపా"], "hi": ["छिड़क", "डाल दिया", "डाला", "मिला दिया"],
                  "en": ["sprinkle", "poured", "pour", "mixed"]}),
    ("touch", {"te": ["తాకగానే", "తాకి", "తాకా", "ముట్టుకో"], "hi": ["छुआ", "छूते"], "en": ["touch"]}),
    ("beg", {"te": ["క్షమించండి", "క్షమించు", "దయచేసి", "బతిమాల", "బాబ్బాబు", "వేడుకు"], "hi": ["माफ़", "माफ", "कृपया", "विनती", "गिड़गिड़ा"],
             "en": ["sorry", "forgive", "please", "beg"]}),
    ("greet", {"te": ["నమస్కారం", "నమస్తే", "దండం"], "hi": ["नमस्ते", "प्रणाम", "राम राम"], "en": ["namaste", "hello", "greet"]}),
    ("stop", {"te": ["ఆగండి", "ఆగు", "ఆగుతావా", "ఒక్క నిమిషం"], "hi": ["रुको", "रुकिए", "ठहरो", "एक मिनट"], "en": ["stop", "wait", "one minute"]}),
    ("surprised", {"te": ["అయ్యో", "ఇదేంటి", "ఏంటిది", "నిజమా", "అరే"], "hi": ["अरे", "क्या!", "सच में", "यह क्या"], "en": ["what!", "oh no", "really?"]}),
    ("scared", {"te": ["భయం", "భయపడ", "అమ్మో"], "hi": ["डर", "बाप रे"], "en": ["scared", "afraid", "fear"]}),
    ("scratch", {"te": ["అర్థం కాలేదు", "ఏమైంది", "ఎలా అయ్యా", "ఏం జరిగింది", "ఎందుకు"], "hi": ["समझ नहीं", "क्या हुआ", "कैसे हुआ", "क्यों"],
                 "en": ["don't understand", "what happened", "how did", "why"]}),
    ("think", {"te": ["ఆలోచ", "అనుకున్నా", "ఉపాయం", "గుర్తు"], "hi": ["सोच", "उपाय", "याद"], "en": ["think", "idea", "remember", "plan"]}),
    ("show", {"te": ["చూశావా", "ఇటు చూడు", "చూడండి", "చూడు"], "hi": ["देखो", "देखिए", "देखा"], "en": ["look at", "see this", "look!"]}),
    ("point", {"te": ["అదిగో", "అక్కడ", "ఆ పిల్లాడు", "వాడు", "నువ్వు"], "hi": ["वो देखो", "वहाँ", "वह", "तुम"], "en": ["there", "you!", "that one"]}),
    ("celebrate", {"te": ["హమ్మయ్య", "భలే", "సంతోషం", "అదిరింది", "హుర్రే"], "hi": ["वाह", "खुशी", "मज़ा", "हुर्रे"], "en": ["yay", "hooray", "wonderful", "great"]}),
    ("wave", {"te": ["వెళ్ళొస్తా", "టాటా", "రండి"], "hi": ["अलविदा", "आओ", "चलो"], "en": ["bye", "come here", "come on"]}),
    ("shrug", {"te": ["ఏమో", "తెలియదు", "ఏం చేస్తాం", "పర్వాలేదు"], "hi": ["पता नहीं", "क्या करें", "कोई बात नहीं"], "en": ["don't know", "whatever", "never mind"]}),
    ("walk", {"te": ["నడుస్తూ", "నడిచి", "బయలుదేర", "అడుగులు వేస్తూ", "వెళ్ళాడు", "వెళ్ళింది", "వచ్చాడు", "వచ్చింది"],
              "hi": ["चलते", "चल पड़", "चला गया", "चली गई", "आया", "आई"], "en": ["walked", "walks", "went", "came"]}),
    ("run", {"te": ["పరిగెత్త", "పరుగు", "పరుగెత్త"], "hi": ["भाग", "दौड़"], "en": ["run", "ran", "rushed"]}),
]
# the writer's action names -> library actions
WRITER_MAP = {"shout": "call_out", "call": "call_out", "sell": "call_out", "call_out": "call_out", "count": "count_money",
              "greedy": "count_money", "rub_hands": "rub_hands", "angry": "stomp", "stomp": "stomp", "scold": "point",
              "confused": "scratch", "scratch": "scratch", "eat": "eat", "drink": "drink", "give": "give",
              "take": "take", "receive": "take", "cry": "cry", "laugh": "laugh", "beg": "beg", "plead": "beg", "greet": "greet",
              "namaste": "greet", "bow": "greet", "stop": "stop", "surprised": "surprised", "shocked": "surprised",
              "scared": "scared", "think": "think", "show": "show", "point": "point", "celebrate": "celebrate",
              "jump": "celebrate", "dance": "celebrate", "wave": "wave", "shrug": "shrug", "hips": "hips", "proud": "proud",
              "sad": "sad", "look_around": "look_around", "sneak": "sneak", "touch": "touch", "sprinkle": "sprinkle",
              "burn": "burn", "comfort": "comfort", "hug": "comfort", "cook": "work", "work": "work", "sit": "sad"}
EMO_DEFAULT = {"greedy": "rub_hands", "angry": "stomp", "sad": "sad", "cry": "cry", "laugh": "laugh", "happy": "proud",
               "proud": "proud", "thinking": "think", "worried": "scratch", "scared": "scared", "surprised": "surprised",
               "ashamed": "sad", "sly": "rub_hands"}
MOVES = {"walk", "run", "enter", "exit"}
VENDOR_ACTS = {"call_out", "count_money", "work", "sprinkle", "burn", "touch"}   # done at the cart, from behind it
NEEDS_TARGET = {"give", "take", "point", "show", "beg", "stop", "comfort"}


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").lower())


def detect(text, lang):
    """[(char offset, action)] for every keyword stem found in the text, in text order."""
    t = _norm(text) + " "
    out = []
    taken = []
    for act, stems in KW:
        for st in stems.get(lang, []) + (stems.get("en", []) if lang != "en" else []):
            st = st.lower()
            i = t.find(st)
            while i >= 0:
                if not any(a <= i < b for a, b in taken):
                    out.append((i, act))
                    taken.append((i, i + len(st)))
                i = t.find(st, i + len(st))
    out.sort()
    return out


def _word_time(ln, char_pos):
    """Time of the word that contains the character offset (from the TTS word boundaries)."""
    words = ln.get("words") or []
    if not words:
        frac = char_pos / max(1, len(ln.get("text") or ""))
        return ln["start"] + (ln["end"] - ln["start"]) * frac
    text = _norm(ln.get("text"))
    # map words to offsets in order
    pos, idx = 0, []
    for w in words:
        j = text.find(_norm(w[2]), pos)
        if j < 0:
            j = pos
        idx.append(j)
        pos = j + max(1, len(w[2]))
    k = 0
    for n, j in enumerate(idx):
        if j <= char_pos:
            k = n
    return words[k][0]


def narrator_actor(ln, cast_ids, names):
    """Who a narrator line is about: its actor / target, else the first cast character named in the text."""
    for key in ("actor", "target"):
        if ln.get(key) in cast_ids:
            return ln[key]
    text = ln.get("text") or ""
    best = None
    for cid in cast_ids:
        nm = names.get(cid)
        for cand in filter(None, {nm, (nm or "")[:-1] if nm and len(nm) > 3 else None}):
            i = text.find(cand)
            if i >= 0 and (best is None or i < best[0]):
                best = (i, cid)
    return best[1] if best else None


def assign_beats(story):
    """Fill ln['beats'] = [[t0, t1, actor, action], ...] (and ln['actor'] for narration) for every line."""
    lang = story.get("lang", "te")
    names = {c["id"]: c.get("name", c["id"]) for c in story.get("characters", [])}
    for sc in story.get("scenes", []):
        cast_ids = []
        for c in sc.get("cast") or []:
            cid = c if isinstance(c, str) else c.get("id")
            if cid in names and cid not in cast_ids:
                cast_ids.append(cid)
        for ln in sc["lines"]:
            for cid in (ln.get("speaker"), ln.get("target")):
                if cid in names and cid not in cast_ids:
                    cast_ids.append(cid)
        for li, ln in enumerate(sc["lines"]):
            if "start" not in ln:
                continue
            ls, le = ln["start"], ln["end"]
            sp = ln.get("speaker")
            narr = sp not in names
            actor = sp if not narr else narrator_actor(ln, cast_ids, names)
            if narr and actor and not ln.get("actor"):
                ln["actor"] = actor
            if not actor:
                ln["beats"] = []
                continue
            wa = (ln.get("action") or "talk").lower().strip()
            beats = []
            found = detect(ln.get("text"), lang)
            # the writer's action first (from the start of the line)
            lib = WRITER_MAP.get(wa)
            emo_ = (ln.get("emotion") or "").lower()
            if wa == "shout" and emo_ in ("angry",):
                lib = "stomp"
            elif wa == "shout" and emo_ in ("surprised", "scared", "worried", "shocked"):
                lib = "surprised"
            subject_ok = True
            if narr and actor:   # "people laugh at GOPI-ni": the named character is the object, not the doer
                nm = names.get(actor) or ""
                i_ = (ln.get("text") or "").find(nm)
                after = (ln.get("text") or "")[i_ + len(nm): i_ + len(nm) + 2] if i_ >= 0 else ""
                if i_ >= 0 and (after.startswith("ని") or after.startswith("ను") or after.startswith(" को") or
                                after.startswith("को")):
                    subject_ok = False
            if lib and wa not in MOVES:
                beats.append([ls + (0.05 if not narr else 0.3), None, actor, lib])
            for pos, act in found:
                if not subject_ok and act not in ("surprised", "look_around", "scratch", "sad", "scared", "burn", "touch"):
                    act = "look_around" if act in ("laugh", "point", "show", "celebrate") else None
                    if act is None:
                        continue
                if act == "count_money" and (wa in ("give", "take", "beg") or any(b[3] in ("give", "take") for b in beats)):
                    continue   # mentions money while handing it over: the give is the action
                if act in ("walk", "run"):
                    if narr and wa == "talk" and not ln.get("_moved"):
                        ln["action"] = act       # narration describes a walk: the subject really walks
                        ln["_moved"] = True
                    continue
                if act == "sneak" and narr and wa == "talk":
                    ln["action"] = "walk"
                if act in NEEDS_TARGET and act in ("give", "take") and not ln.get("target") and len(cast_ids) < 2:
                    continue
                t = max(ls, _word_time(ln, pos) - 0.15)
                if beats and t - beats[-1][0] < 1.3:
                    if beats[-1][3] in ("point", "show", "surprised", "scratch") and act not in ("point", "show"):
                        beats[-1][3] = act     # a more specific action replaces a generic one
                    continue
                if beats and beats[-1][3] == act:
                    continue
                beats.append([t, None, actor, act])
                if len(beats) >= 3:
                    break
            if not beats:   # nothing named: act out the feeling (narration shows the subject; speakers talk)
                e = (ln.get("emotion") or "neutral").lower()
                if narr:
                    beats.append([ls + 0.3, None, actor, EMO_DEFAULT.get(e, "look_around" if li % 2 else "think")])
                elif e in ("cry", "angry", "laugh", "scared", "surprised") and wa in ("talk", ""):
                    beats.append([ls + 0.05, None, actor, EMO_DEFAULT[e]])
            beats.sort(key=lambda b: b[0])
            for k, b in enumerate(beats):
                nxt = beats[k + 1][0] if k + 1 < len(beats) else le + 0.25
                dmax = ACTIONS.get(b[3], {}).get("max", 3.2)
                b[1] = min(nxt - 0.05, b[0] + dmax, le + 0.4)
                b[1] = max(b[1], b[0] + min(1.0, ACTIONS.get(b[3], {}).get("min", 1.0)))
            ln["beats"] = [[round(b[0], 3), round(b[1], 3), b[2], b[3]] for b in beats]
    return story


# ============================================================================================ the action library
# Arm targets (out, down) in adult units relative to each shoulder, like long2d.GEST: r = near/front hand (out > 0 =
# forward, toward the facing side), l = far/back hand (out < 0 = forward). Shapes: open, point, fist, cup, pinch, palm.
# Body: lean (deg, + forward), dip (px, knees bend), tilt (head deg, + = down/forward), turn (head turn -1..1),
# gx/gy (gaze), hip (px), foot (near foot lift px), hop (px).
def K(t, **p):
    return (t, p)


ACTIONS = {
    "call_out": {"keys": [K(0.0, r=(50, 110), rs="open"), K(0.28, r=(40, -76), rs="cup", l=(22, 164), ls="fist", lean=-2, tilt=-4),
                          K(0.6, r=(42, -80), rs="cup", lean=6, tilt=-9, dip=3), K(1.0, r=(40, -76), lean=0, tilt=-3, dip=0)],
                 "loop": (0.28, 1.0), "osc": {"turn": (0.2, 0.35)}, "max": 3.4},
    "count_money": {"keys": [K(0.0, r=(50, 110), l=(-60, 116), rs="pinch", ls="palm", tilt=6, gy=0.55),
                             K(0.22, r=(30, 104), l=(-70, 112), tilt=8),
                             K(0.44, r=(50, 110), l=(-60, 116), tilt=6)],
                    "loop": (0.0, 0.44), "osc": {"hip": (1.2, 0.5)}, "max": 3.0},
    "rub_hands": {"keys": [K(0.0, r=(-10, 112), l=(-50, 110), rs="open", ls="open", lean=3, tilt=-2),
                           K(0.18, r=(4, 106), l=(-62, 114)), K(0.36, r=(-10, 112), l=(-50, 110))],
                  "loop": (0.0, 0.36), "max": 2.6},
    "give": {"keys": [K(0.0, r=(30, 130), rs="palm"), K(0.25, r=(18, 120), rs="palm", lean=-2),
                      K(0.75, r=(176, 84), rs="palm", lean=7, tilt=3), K(1.5, r=(172, 86), lean=6),
                      K(2.1, r=(60, 150), rs="open", lean=1, tilt=0)], "max": 2.4, "min": 1.6},
    "take": {"keys": [K(0.0, r=(60, 140), rs="open"), K(0.45, r=(160, 88), rs="open", lean=6),
                      K(0.85, r=(150, 90), rs="fist", lean=5), K(1.4, r=(40, 112), rs="fist", lean=-1, tilt=4)], "max": 2.0, "min": 1.4},
    "eat": {"keys": [K(0.0, r=(60, 110), rs="pinch"), K(0.35, r=(70, -30), rs="pinch", tilt=-3),
                     K(0.6, r=(68, -26), tilt=-2), K(0.95, r=(60, 100), tilt=2)], "loop": (0.0, 0.95), "max": 3.0},
    "drink": {"keys": [K(0.0, r=(60, 110), rs="fist"), K(0.4, r=(70, -36), rs="fist", tilt=-10, lean=-3),
                       K(1.4, r=(70, -36), tilt=-12, lean=-4), K(1.8, r=(60, 110), tilt=0, lean=0)], "max": 2.2},
    "cry": {"keys": [K(0.0, r=(60, 60), l=(-40, 70), rs="fist", ls="fist", tilt=8),
                     K(0.35, r=(64, -70), l=(-50, -60), tilt=12, dip=4)],
            "osc": {"dip": (2.5, 4.2), "tilt": (1.5, 4.2), "r_down": (5, 4.2)}, "max": 4.0},
    "laugh": {"keys": [K(0.0, r=(-20, 150), l=(-50, 150), rs="open", ls="open", lean=-4, tilt=-8),
                       K(0.3, r=(-28, 142), l=(-58, 144), lean=-7, tilt=-12)],
              "osc": {"dip": (3.0, 3.6), "lean": (2.0, 3.6)}, "max": 3.2},
    "stomp": {"keys": [K(0.0, r=(80, 60), l=(22, 164), rs="fist", ls="fist", lean=4),
                       K(0.18, r=(96, -96), rs="fist", foot=28, dip=-2, lean=6),
                       K(0.32, r=(100, -60), foot=0, dip=12, lean=8, tilt=6),
                       K(0.55, r=(96, -100), dip=2, lean=5, tilt=0),
                       K(0.9, r=(100, -70), foot=22, dip=0),
                       K(1.04, r=(98, -96), foot=0, dip=10, lean=7),
                       K(1.3, r=(96, -90), dip=1, lean=4)],
              "osc": {"r_out": (6, 3.5)}, "max": 2.6},
    "sneak": {"keys": [K(0.0, r=(80, 100), l=(-60, 110), rs="open", ls="open", dip=18, lean=9, tilt=4),
                       K(0.6, r=(84, 96), l=(-66, 104), dip=22, lean=10, turn=-0.4, gx=0.1)],
              "osc": {"turn": (0.5, 0.3)}, "max": 4.0},
    "look_around": {"keys": [K(0.0, turn=0.4, gx=0.35, r=(40, 160), rs="open"), K(0.45, turn=-0.5, gx=-0.4, tilt=-2, hip=-3),
                             K(1.15, turn=-0.5, gx=-0.4, tilt=-2), K(1.6, turn=0.6, gx=0.45, tilt=2, hip=3),
                             K(2.3, turn=0.6, gx=0.45), K(2.7, turn=0.4, gx=0.35, tilt=0, hip=0)], "max": 2.8, "min": 1.8},
    "sprinkle": {"keys": [K(0.0, r=(80, 80), rs="pinch", tilt=6, gy=0.5), K(0.3, r=(118, 30), rs="pinch", lean=4, tilt=10)],
                 "osc": {"r_out": (8, 7.0), "r_down": (5, 7.0)}, "max": 2.8},
    "touch": {"keys": [K(0.0, r=(60, 120), rs="open"), K(0.4, r=(150, 120), rs="open", lean=5, tilt=6),
                       K(0.7, r=(150, 118)), K(0.85, r=(40, 60), rs="open", lean=-6, dip=6, tilt=-6),
                       K(1.4, r=(50, 80), lean=-3, dip=2)], "osc": {}, "max": 2.0},
    "burn": {"keys": [K(0.0, r=(70, 70), l=(-70, 74), rs="open", ls="open", lean=-5, tilt=-4),
                      K(0.2, r=(80, 50), l=(-80, 54))],
             "osc": {"r_out": (18, 9.0), "l_out": (18, 9.5), "r_down": (10, 11.0), "hip": (3, 6.0)}, "hop": 0.05, "max": 2.6},
    "beg": {"keys": [K(0.0, r=(-44, 70), l=(-50, 66), rs="open", ls="open", lean=4, tilt=5),
                     K(0.4, r=(-40, 62), l=(-46, 60), lean=12, tilt=10, dip=4),
                     K(1.2, r=(-40, 60), l=(-46, 58), lean=9, tilt=8, dip=3)], "osc": {"lean": (1.5, 1.6)}, "max": 3.2},
    "greet": {"keys": [K(0.0, r=(-44, 64), l=(-50, 62), rs="open", ls="open"), K(0.35, lean=14, tilt=12, dip=3),
                       K(0.9, lean=2, tilt=2, dip=0)], "max": 1.8},
    "stop": {"keys": [K(0.0, r=(60, 100), rs="open", lean=0), K(0.2, r=(170, -42), rs="open", lean=-3, tilt=-3),
                      K(0.5, r=(166, -38))], "osc": {"r_out": (4, 3.0)}, "max": 2.4},
    "surprised": {"keys": [K(0.0, r=(40, 160), l=(40, 160), dip=8), K(0.12, r=(110, -110), l=(110, -110), rs="open", ls="open",
                                                                        lean=-8, dip=-2, tilt=-6),
                           K(0.6, r=(100, -90), l=(100, -90), lean=-4, tilt=-3)], "hop": 0.1, "max": 1.8},
    "scared": {"keys": [K(0.0, r=(58, 40), l=(-150, 46), rs="open", ls="open", lean=-8, dip=6),
                        K(0.3, r=(70, -30), l=(-120, -20), lean=-10, dip=10, tilt=-4)],
               "osc": {"hip": (2.5, 9.0), "r_out": (5, 8.0)}, "max": 3.0},
    "scratch": {"keys": [K(0.0, r=(40, 120), rs="open", tilt=4), K(0.35, r=(46, -170), rs="open", tilt=9, gy=-0.3, gx=0.15)],
                "osc": {"r_out": (7, 6.0), "r_down": (4, 6.0)}, "max": 2.8},
    "think": {"keys": [K(0.0, r=(30, 120), l=(22, 140), rs="fist"), K(0.4, r=(-30, 14), l=(-50, 118), rs="fist", ls="open", tilt=6,
                                                                           gy=-0.35, gx=0.1)],
              "osc": {"tilt": (1.5, 0.9)}, "max": 3.2},
    "show": {"keys": [K(0.0, r=(50, 120), rs="palm"), K(0.35, r=(128, 4), rs="palm", lean=3, tilt=-3),
                      K(1.2, r=(124, 10), lean=2)], "osc": {"r_down": (3, 1.5)}, "max": 2.6},
    "point": {"keys": [K(0.0, r=(60, 110), rs="point"), K(0.22, r=(206, 34), rs="point", lean=5, tilt=2),
                       K(0.38, r=(186, 42), lean=3), K(0.54, r=(206, 34), lean=5), K(1.0, r=(200, 38), lean=3)], "max": 2.4},
    "celebrate": {"keys": [K(0.0, r=(60, 60), l=(60, 60), dip=8), K(0.15, r=(88, -168), l=(88, -168), rs="open", ls="open",
                                                                      tilt=-6, dip=-2)],
                  "osc": {"r_down": (16, 5.0), "l_down": (16, 5.0)}, "hop": 0.12, "max": 2.4},
    "wave": {"keys": [K(0.0, r=(60, 100), rs="open"), K(0.25, r=(70, -150), rs="open", tilt=-3)],
             "osc": {"r_out": (26, 1.8)}, "max": 2.2},
    "shrug": {"keys": [K(0.0, r=(40, 150), l=(40, 150)), K(0.3, r=(86, 50), l=(86, 50), rs="palm", ls="palm", tilt=7, dip=-3),
                       K(1.0, r=(84, 56), l=(84, 56), tilt=5, dip=0)], "max": 1.8},
    "hips": {"keys": [K(0.0, r=(30, 150), l=(30, 150)), K(0.3, r=(22, 164), l=(22, 164), rs="fist", ls="fist", lean=-2, tilt=-3)],
             "max": 2.6},
    "proud": {"keys": [K(0.0, r=(30, 150), l=(30, 150)), K(0.35, r=(22, 164), l=(22, 164), rs="fist", ls="fist", lean=-4, tilt=-6,
                                                              dip=-1)], "osc": {"tilt": (1.2, 1.0)}, "max": 2.6},
    "sad": {"keys": [K(0.0, r=(10, 196), l=(10, 196)), K(0.6, r=(-10, 196), l=(4, 200), rs="open", tilt=10, lean=4, dip=3, gy=0.6)],
            "max": 3.0},
    "comfort": {"keys": [K(0.0, r=(60, 120), rs="open"), K(0.5, r=(150, 40), rs="open", lean=6, tilt=4), K(1.6, r=(148, 46), lean=5)],
                "osc": {"r_down": (4, 1.6)}, "max": 2.4},
    "work": {"keys": [K(0.0, r=(80, 110), l=(-50, 110), rs="fist", ls="open", tilt=8, gy=0.5),
                      K(0.3, r=(100, 100), l=(-40, 116)), K(0.6, r=(80, 110), l=(-50, 110))], "loop": (0.0, 0.6), "max": 3.0},
}
ACTION_EXPR = {"cry": "cry", "laugh": "laugh", "stomp": "angry", "surprised": "surprised", "scared": "scared",
               "burn": "scared", "count_money": "greedy", "rub_hands": "greedy", "beg": "worried", "sad": "sad",
               "celebrate": "happy", "scratch": "thinking", "think": "thinking", "proud": "proud", "eat": "happy",
               "sneak": "sly", "look_around": "worried", "greet": "happy"}
ACTION_FX = {"stomp": "steam", "surprised": "bang", "scratch": "question", "think": "question", "burn": "steam_hot"}
ACTION_HOLD = {"count_money": "money", "eat": None, "drink": "chai"}   # eat: the food named in the line
HELD_FREE = {"give", "take", "show", "point", "celebrate", "wave", "stop", "touch", "eat", "drink", "sprinkle", "count_money"}


def _smooth(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def evaluate(name, u, dur, t_abs=0.0):
    """Pose dict of action `name`, u seconds into a beat of length dur. Missing keys mean "no opinion"."""
    A = ACTIONS.get(name)
    if not A:
        return {}
    keys = A["keys"]
    loop = A.get("loop")
    if loop and u > loop[1]:
        span = loop[1] - loop[0]
        u = loop[0] + (u - loop[0]) % span
    # carry every parameter forward through the keys
    state, out = {}, None
    timeline = []
    for t, p in keys:
        state = dict(state, **p)
        timeline.append((t, dict(state)))
    if u <= timeline[0][0]:
        out = dict(timeline[0][1])
    elif u >= timeline[-1][0]:
        out = dict(timeline[-1][1])
    else:
        for (ta, pa), (tb, pb) in zip(timeline, timeline[1:]):
            if ta <= u <= tb:
                k = _smooth((u - ta) / max(1e-6, tb - ta))
                out = {}
                for key in set(pa) | set(pb):
                    a, b = pa.get(key, pb.get(key)), pb.get(key, pa.get(key))
                    if isinstance(a, tuple):
                        out[key] = (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
                    elif isinstance(a, str):
                        out[key] = b if k > 0.5 else a
                    else:
                        out[key] = a + (b - a) * k
                break
    for key, (amp, hz) in (A.get("osc") or {}).items():
        v = amp * math.sin(2 * math.pi * hz * t_abs)
        if key in ("r_out", "r_down", "l_out", "l_down"):
            hand, ax = key[0], 0 if key.endswith("out") else 1
            if hand in out:
                h = list(out[hand]); h[ax] += v; out[hand] = tuple(h)
        else:
            out[key] = out.get(key, 0.0) + v
    return out


# ============================================================================================ talk + listen poses
TALK_SETS = {   # gesture names in long2d.GEST, by mood
    "neutral": ["talk_open", "talk_both", "talk_up", "talk_low", "talk_self", "talk_chop", "talk_count"],
    "happy": ["talk_wide", "talk_up", "talk_both", "talk_open", "talk_self"],
    "angry": ["talk_chop", "point", "talk_fist", "talk_chop", "talk_both"],
    "sad": ["talk_low", "talk_self", "talk_open", "sad"],
    "greedy": ["talk_count", "greedy", "talk_up", "talk_self"],
    "scared": ["talk_both", "scared", "talk_self"],
    "worried": ["talk_self", "worried", "talk_open", "talk_low"],
}
TALK_MOOD = {"happy": "happy", "laugh": "happy", "proud": "happy", "angry": "angry", "sad": "sad", "cry": "sad",
             "ashamed": "sad", "greedy": "greedy", "sly": "greedy", "scared": "scared", "worried": "worried",
             "surprised": "scared"}
LISTEN_SETS = {
    "neutral": ["rest", "fold", "clasp", "rest", "chin", "hips"],
    "happy": ["rest", "clasp", "hips", "rest"],
    "angry": ["fold", "hips", "fold"],
    "sad": ["sad", "clasp", "rest"],
    "worried": ["worried", "clasp", "chin"],
    "greedy": ["greedy", "hips", "fold"],
    "thinking": ["chin", "think", "fold"],
    "scared": ["scared", "clasp"],
}
LISTEN_MOOD = {"happy": "happy", "laugh": "happy", "proud": "happy", "angry": "angry", "sad": "sad", "cry": "sad",
               "ashamed": "sad", "worried": "worried", "greedy": "greedy", "sly": "greedy", "thinking": "thinking",
               "scared": "scared", "surprised": "worried"}


def stress_times(words, min_gap=0.65):
    """Onsets of stressed words (long words, phrase starts) for nods, hand beats and gesture changes."""
    out = []
    prev_end = -1e9
    for w0, w1, w in words:
        long_w = (w1 - w0) > 0.34 or len(w) >= 6
        phrase = w0 - prev_end > 0.18
        if (long_w or phrase) and (not out or w0 - out[-1] >= min_gap):
            out.append(w0)
        prev_end = w1
    return out


def hsh(*xs):
    h = 2166136261
    for x in xs:
        for ch in str(x):
            h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h / 4294967296.0
