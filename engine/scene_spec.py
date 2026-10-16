"""What the Blender story renderer can show. Shared by scripts/write_story.py (prompt + validation)
and engine/render_blender.py (builder). Pure Python, no dependencies (runs inside Blender too).
"""
import re

SETTINGS = ["street", "home", "school", "park", "shop", "office", "night_sky", "lab"]
CHAR_TYPES = ["man", "woman", "boy", "girl", "grandpa", "grandma", "scientist", "robot"]
COLORS = {  # shirt / body colour -> linear-ish RGB used by Blender
    "red": (0.80, 0.08, 0.06), "blue": (0.06, 0.22, 0.85), "green": (0.10, 0.60, 0.15),
    "yellow": (0.95, 0.75, 0.05), "orange": (0.95, 0.35, 0.03), "purple": (0.40, 0.10, 0.70),
    "pink": (0.95, 0.35, 0.55), "teal": (0.03, 0.55, 0.55), "white": (0.85, 0.85, 0.85),
    "black": (0.04, 0.04, 0.05), "brown": (0.35, 0.18, 0.07), "gray": (0.40, 0.42, 0.45),
}
ACTIONS = ["walk", "talk", "point", "jump", "run", "fall", "sit", "celebrate", "shocked", "wave", "think"]
PROPS = ["none", "lightbulb", "book", "phone", "box", "coin", "trophy", "laptop", "ball", "clock"]

_SYN = {
    # settings
    "road": "street", "city": "street", "market": "shop", "bazaar": "shop", "store": "shop",
    "house": "home", "room": "home", "kitchen": "home", "living_room": "home", "bedroom": "home",
    "classroom": "school", "college": "school", "garden": "park", "village": "park", "field": "park",
    "forest": "park", "factory": "office", "workplace": "office", "company": "office", "laboratory": "lab",
    "night": "night_sky", "sky": "night_sky", "space": "night_sky", "nightsky": "night_sky",
    # characters
    "boy_child": "boy", "kid": "boy", "child": "boy", "girl_child": "girl", "lady": "woman", "female": "woman",
    "male": "man", "guy": "man", "engineer": "man", "old_man": "grandpa", "grandfather": "grandpa",
    "dada": "grandpa", "nana": "grandpa", "old_woman": "grandma", "grandmother": "grandma", "dadi": "grandma",
    "nani": "grandma", "doctor": "scientist", "inventor": "scientist", "professor": "scientist", "bot": "robot",
    # actions
    "walking": "walk", "talking": "talk", "speak": "talk", "say": "talk", "explain": "talk", "pointing": "point",
    "jumping": "jump", "running": "run", "falling": "fall", "fail": "fall", "sitting": "sit",
    "celebrating": "celebrate", "happy": "celebrate", "cheer": "celebrate", "dance": "celebrate",
    "surprised": "shocked", "shock": "shocked", "surprise": "shocked", "scared": "shocked", "waving": "wave",
    "thinking": "think", "idea": "think", "wonder": "think",
    # colours / props
    "grey": "gray", "violet": "purple", "cyan": "teal", "gold": "yellow", "bulb": "lightbulb", "light": "lightbulb",
    "mobile": "phone", "computer": "laptop", "money": "coin", "rupee": "coin", "package": "box", "parcel": "box",
    "watch": "clock", "award": "trophy", "cup": "trophy",
}


def norm(v, allowed, default):
    """Map an LLM value onto the allowed list (case, spaces, plurals, synonyms); else default."""
    if not isinstance(v, str):
        return default
    k = re.sub(r"[^a-z_]", "", v.strip().lower().replace(" ", "_").replace("-", "_"))
    for cand in (k, k.rstrip("s"), _SYN.get(k), _SYN.get(k.rstrip("s"))):
        if cand in allowed:
            return cand
    return default


def normalize(story):
    """Make story["cast"] and every sentence["scene"] safe for the renderer. Never raises.
    cast: [{"name","type","color"}] (1-3).  scene: {"setting","characters":[cast idx],"action","prop"}."""
    raw_cast = story.get("cast") if isinstance(story.get("cast"), list) else []
    cast = []
    for c in raw_cast[:3]:
        if not isinstance(c, dict):
            continue
        cast.append({"name": str(c.get("name") or f"char{len(cast)}")[:20],
                     "type": norm(c.get("type"), CHAR_TYPES, "man"),
                     "color": norm(c.get("color"), COLORS, ["blue", "red", "green"][len(cast) % 3])})
    names = {c["name"].lower(): i for i, c in enumerate(cast)}

    def char_index(ch):
        """cast index for an int, a name, or a {type,color} dict (added to cast if new and room left)."""
        if isinstance(ch, bool):
            return None
        if isinstance(ch, int):
            return ch if 0 <= ch < len(cast) else None
        if isinstance(ch, str):
            if ch.strip().isdigit():
                return char_index(int(ch.strip()))
            return names.get(ch.strip().lower())
        if isinstance(ch, dict):
            if ch.get("name") and str(ch["name"]).lower() in names:
                return names[str(ch["name"]).lower()]
            t = norm(ch.get("type"), CHAR_TYPES, None)
            col = norm(ch.get("color"), COLORS, None)
            for i, c in enumerate(cast):
                if c["type"] == t and (col is None or c["color"] == col):
                    return i
            if t and len(cast) < 3:
                cast.append({"name": str(ch.get("name") or f"char{len(cast)}")[:20], "type": t,
                             "color": col or ["blue", "red", "green"][len(cast) % 3]})
                names[cast[-1]["name"].lower()] = len(cast) - 1
                return len(cast) - 1
        return None

    prev_setting = None
    for i, s in enumerate(story.get("sentences") or []):
        sc = s.get("scene") if isinstance(s.get("scene"), dict) else {}
        setting = norm(sc.get("setting"), SETTINGS, None) or prev_setting or "street"
        chars = sc.get("characters") if isinstance(sc.get("characters"), list) else []
        idx = []
        for ch in chars:
            k = char_index(ch)
            if k is not None and k not in idx:
                idx.append(k)
        if not cast:
            cast.append({"name": "hero", "type": "man", "color": "blue"})
        if not idx:
            idx = [0]
        sc = {"setting": setting, "characters": idx[:3], "action": norm(sc.get("action"), ACTIONS, "talk"),
              "prop": norm(sc.get("prop"), PROPS, "none")}
        s["scene"] = sc
        prev_setting = setting
    story["cast"] = cast or [{"name": "hero", "type": "man", "color": "blue"}]
    return story
