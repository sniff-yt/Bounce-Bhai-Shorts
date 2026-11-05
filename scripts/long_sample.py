#!/usr/bin/env python3
"""Cut a written long story down to a ~60-90 s SAMPLE for pipeline checks: the opener line, then the scene with the
most back-and-forth dialogue (>= 2 speakers), capped at ~11 lines. usage: python scripts/long_sample.py story.json"""
import json, sys

p = sys.argv[1]
s = json.load(open(p, encoding="utf-8"))
sc = s["scenes"]
best = max(range(len(sc)), key=lambda i: (len({l.get("speaker") for l in sc[i]["lines"]} - {"narrator"}),
                                          sum(1 for l in sc[i]["lines"] if l.get("speaker") != "narrator")))
pick = dict(sc[best])
lines = pick["lines"][:11]
opener = sc[0]["lines"][0] if sc[0]["lines"] and sc[0]["lines"][0].get("speaker") == "narrator" else None
if opener and best != 0:
    lines = [opener] + [l for l in lines if l.get("speaker") != "narrator"][:10]
pick["lines"] = lines
pick.pop("moral_card", None)
s["scenes"] = [pick]
s["sample_of_scene"] = best
json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"::notice title=sample::scene {best} ({pick.get('set')}), {len(lines)} lines, speakers "
      f"{sorted({l.get('speaker') for l in lines})}")
