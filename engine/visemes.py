#!/usr/bin/env python3
"""Viseme lip-sync for the long-form cutout puppets.

Text -> mouth shapes, timed by edge-tts WordBoundary events:
  * every spoken word is split into aksharas / letter groups (Telugu, Devanagari) or letters/digraphs (English),
  * each unit maps to a viseme (closed M-B-P, A wide open, E/I spread, O round, U/W small round, F/V lip bite,
    L/T/D/N tongue up, S/CH/J clenched teeth, K/G/H relaxed open, AH schwa, X rest),
  * the word's duration is shared across its units by weight (long vowels longest, consonants short),
  * the renderer samples the timeline with a short triangular window (coarticulation / smooth blending) and closes the
    mouth when the speech envelope is silent (pauses inside a line).

A viseme is a parameter vector the head drawer turns into a mouth, so any blend of two shapes is itself drawable.
"""
import bisect

FIELDS = ("open", "width", "round", "teeth_up", "teeth_dn", "tongue", "tongue_up", "bite", "press")
_V = {
    #        open  width round t_up  t_dn  tong  t_up  bite  press
    "X":    (0.03, 1.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00),   # rest (lips together, relaxed)
    "MBP":  (0.00, 0.86, 0.15, 0.00, 0.00, 0.00, 0.00, 0.00, 1.00),   # m b p: pressed lips
    "A":    (0.95, 1.08, 0.05, 0.55, 0.00, 0.65, 0.00, 0.00, 0.00),   # aa: jaw wide open
    "AH":   (0.58, 1.00, 0.10, 0.45, 0.00, 0.45, 0.00, 0.00, 0.00),   # schwa / short a
    "E":    (0.40, 1.32, 0.00, 1.00, 0.55, 0.20, 0.00, 0.00, 0.00),   # e / i: spread lips, teeth show
    "O":    (0.56, 0.74, 1.00, 0.25, 0.00, 0.35, 0.00, 0.00, 0.00),   # o: round open
    "U":    (0.30, 0.44, 1.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00),   # u / w: small round pucker
    "FV":   (0.16, 1.02, 0.00, 1.00, 0.00, 0.00, 0.00, 1.00, 0.00),   # f v: top teeth on lower lip
    "L":    (0.48, 0.98, 0.05, 0.70, 0.20, 1.00, 1.00, 0.00, 0.00),   # l t d n r: tongue tip up
    "S":    (0.22, 1.16, 0.00, 1.00, 1.00, 0.00, 0.00, 0.00, 0.00),   # s sh ch j: clenched teeth
    "K":    (0.42, 0.96, 0.10, 0.45, 0.10, 0.50, 0.00, 0.00, 0.00),   # k g h y: relaxed open, tongue back
}
VIS = {k: dict(zip(FIELDS, v)) for k, v in _V.items()}
REST = VIS["X"]


# ----------------------------------------------------------------------------------------------- Indic scripts
def _indic_maps(base):
    """Consonant / vowel maps for Telugu (base 0x0C00) and Devanagari (0x0900): same ISCII layout."""
    cons = {}
    for off, v in [(0x15, "K"), (0x16, "K"), (0x17, "K"), (0x18, "K"), (0x19, "K"),
                   (0x1A, "S"), (0x1B, "S"), (0x1C, "S"), (0x1D, "S"), (0x1E, "L"),
                   (0x1F, "L"), (0x20, "L"), (0x21, "L"), (0x22, "L"), (0x23, "L"),
                   (0x24, "L"), (0x25, "L"), (0x26, "L"), (0x27, "L"), (0x28, "L"), (0x29, "L"),
                   (0x2A, "MBP"), (0x2B, "MBP"), (0x2C, "MBP"), (0x2D, "MBP"), (0x2E, "MBP"),
                   (0x2F, "E"), (0x30, "L"), (0x31, "L"), (0x32, "L"), (0x33, "L"), (0x34, "L"),
                   (0x35, "FV"), (0x36, "S"), (0x37, "S"), (0x38, "S"), (0x39, "K")]:
        cons[chr(base + off)] = v
    ind = {}   # independent vowels (letter, long?)
    for off, v, lg in [(0x05, "A", 0), (0x06, "A", 1), (0x07, "E", 0), (0x08, "E", 1), (0x09, "U", 0), (0x0A, "U", 1),
                       (0x0B, "E", 0), (0x0C, "L", 0), (0x0D, "E", 0), (0x0E, "E", 0), (0x0F, "E", 1), (0x10, "E", 1),
                       (0x11, "O", 0), (0x12, "O", 0), (0x13, "O", 1), (0x14, "O", 1)]:
        ind[chr(base + off)] = (v, lg)
    signs = {}
    for off, v, lg in [(0x3E, "A", 1), (0x3F, "E", 0), (0x40, "E", 1), (0x41, "U", 0), (0x42, "U", 1), (0x43, "E", 0),
                       (0x44, "E", 1), (0x45, "E", 0), (0x46, "E", 0), (0x47, "E", 1), (0x48, "E", 1), (0x49, "O", 0),
                       (0x4A, "O", 0), (0x4B, "O", 1), (0x4C, "O", 1)]:
        signs[chr(base + off)] = (v, lg)
    return cons, ind, signs, chr(base + 0x4D), chr(base + 0x02), chr(base + 0x01), chr(base + 0x03)


_TE = _indic_maps(0x0C00)
_HI = _indic_maps(0x0900)
NUKTA = "\u093C"


def _indic_units(word, maps, lang):
    cons, ind, signs, virama, anus, candra, visarga = maps
    units = []   # (viseme, weight)
    chars = list(word)
    i, n = 0, len(chars)
    while i < n:
        c = chars[i]
        if c in cons:
            v = cons[c]
            if i + 1 < n and chars[i + 1] == NUKTA:   # फ़ ज़ ...
                v = {"MBP": "FV", "S": "S", "K": "K"}.get(v, v)
                i += 1
            units.append((v, 0.75))
            nxt = chars[i + 1] if i + 1 < n else ""
            if nxt == virama:   # conjunct or dead consonant: no vowel
                i += 2
                continue
            if nxt in signs:
                sv, lg = signs[nxt]
                units.append((sv, 1.9 if lg else 1.3))
                i += 2
                continue
            # inherent vowel: Telugu says a clear short "a"; Hindi drops the word-final schwa
            last = all(not (ch in cons or ch in ind) for ch in chars[i + 1:])
            if lang == "hi":
                if not last or len(word) <= 1:
                    units.append(("AH", 1.0))
            else:
                units.append(("A" if not last else "AH", 1.15))
            i += 1
            continue
        if c in ind:
            v, lg = ind[c]
            units.append((v, 1.9 if lg else 1.3))
        elif c == anus or c == candra:
            nxt = next((ch for ch in chars[i + 1:] if ch in cons), "")
            units.append(("MBP" if (not nxt and lang == "te") or cons.get(nxt) == "MBP" else "L", 0.7))
        elif c == visarga:
            units.append(("K", 0.6))
        elif c.isascii() and c.isalnum():
            units += _en_units(c)
        i += 1
    return units


# ----------------------------------------------------------------------------------------------- English
_DIG = {"th": "L", "sh": "S", "ch": "S", "ph": "FV", "ng": "K", "ck": "K", "wh": "U", "qu": "K",
        "oo": "U", "ee": "E", "ea": "E", "ou": "O", "ow": "O", "oa": "O", "ai": "E", "ay": "E", "oi": "O", "au": "O", "aw": "O"}
_LET = {"a": "A", "e": "E", "i": "E", "o": "O", "u": "AH", "y": "E", "b": "MBP", "m": "MBP", "p": "MBP", "f": "FV",
        "v": "FV", "w": "U", "t": "L", "d": "L", "n": "L", "l": "L", "r": "L", "s": "S", "z": "S", "c": "S", "j": "S",
        "x": "S", "k": "K", "g": "K", "q": "K", "h": "K"}
_DIGITS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
           "8": "eight", "9": "nine"}


def _en_units(word):
    w = "".join(_DIGITS.get(ch, ch) for ch in word.lower())
    w = "".join(ch for ch in w if ch.isalpha())
    if len(w) > 3 and w.endswith("e") and w[-2] not in "aeiou":
        w = w[:-1]   # silent final e
    units, i = [], 0
    while i < len(w):
        dg = w[i:i + 2]
        if dg in _DIG:
            v = _DIG[dg]
            units.append((v, 1.6 if dg[0] in "aeiou" else 0.8))
            if dg in ("ow", "ou"):
                units.append(("U", 0.6))
            i += 2
            continue
        ch = w[i]
        v = _LET.get(ch)
        if ch == "c" and w[i + 1:i + 2] in ("a", "o", "u", "l", "r", "k", ""):
            v = "K"
        if ch == "y" and i == 0:
            v = "E"
        if v:
            units.append((v, 1.3 if ch in "aeiouy" else 0.75))
        i += 1
    return units


def word_units(word, lang):
    if any(0x0C00 <= ord(c) <= 0x0C7F for c in word):
        u = _indic_units(word, _TE, "te")
    elif any(0x0900 <= ord(c) <= 0x097F for c in word):
        u = _indic_units(word, _HI, "hi")
    else:
        u = _en_units(word)
    return u or [("AH", 1.0)]


# ----------------------------------------------------------------------------------------------- timeline
LEAD = 0.035   # the mouth forms a shape slightly before its sound


def line_keys(words, lang):
    """[(t0, t1, viseme)] covering each word of one line; gaps between words are rest (X)."""
    keys = []
    for w0, w1, text in words:
        units = word_units(str(text), lang)
        dur = max(0.04, w1 - w0)
        tot = sum(wt for _, wt in units)
        t = w0 - LEAD
        for v, wt in units:
            d = dur * wt / tot
            keys.append((t, t + d, v))
            t += d
    return keys


class Track:
    """Viseme timeline for one speaker in one line; sample(t) -> blended parameter dict."""

    def __init__(self, keys):
        self.keys = sorted(keys)
        self.starts = [k[0] for k in self.keys]

    def at(self, t):
        i = bisect.bisect_right(self.starts, t) - 1
        if i < 0:
            return "X"
        a, b, v = self.keys[i]
        if t <= b + 0.03:
            return v
        return "X" if (i + 1 >= len(self.keys) or self.keys[i + 1][0] - b > 0.07) else v

    def sample(self, t, half=0.038):
        acc = dict.fromkeys(FIELDS, 0.0)
        tot = 0.0
        for k, wgt in ((-1.0, 0.5), (-0.5, 0.8), (0.0, 1.0), (0.5, 0.8), (1.0, 0.5)):
            v = VIS[self.at(t + k * half)]
            for f in FIELDS:
                acc[f] += v[f] * wgt
            tot += wgt
        out = {f: acc[f] / tot for f in FIELDS}
        # pressed lips must read as closed even when blended with a neighbour
        if self.at(t) == "MBP":
            out["open"] *= 0.35
            out["press"] = max(out["press"], 0.8)
        return out


def blend(a, b, k):
    return {f: a[f] + (b[f] - a[f]) * k for f in FIELDS}


if __name__ == "__main__":
    import sys
    for w in sys.argv[1:] or ["అవును", "బంగారు", "మారుతుందనుకుంటాడు", "बहुत", "लालची", "money", "with"]:
        print(w, word_units(w, "te"))
