#!/usr/bin/env python3
"""Frame checker for the long-form cartoons, from the render plan (no video render needed).

usage: python scripts/long_qc.py out/long_x.json [--step 0.25] [--report out/long_x_qc.json] [--strict]

Builds the same Renderer the video uses (director tracks, gesture keyframes, camera shots), samples every scene and
checks each frame for:
  head_cut       a visible character whose head is not fully in frame (the rule: head fully in, or fully out)
  overlap        two standing characters' bodies overlapping each other
  prop_overlap   a standing character overlapping a stage prop or someone else's cart
  out_of_bounds  a speaking character standing off stage, or feet not on the stage floor line
  dup_prop       a unique story object (magic pot ...) visible more than once (held twice / held + placed)
  floating       a character's lowest sole above the ground while not jumping
  joints         elbows folded backwards / inward, knees bent backwards, impossible joint angles
  hand_face      a hand clipping through a face
  facing         a speaker turned away from the person spoken to
Prints a summary (GitHub ::warning annotations per failing category) and exits 1 when anything fails.
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
import long2d as L   # noqa: E402
import long_cast as LC   # noqa: E402
import long_props as LP   # noqa: E402

TOL = 3.0            # px (screen) a head may touch the frame edge
ELBOW_MIN, KNEE_MIN = 12.0, 60.0


def frame_rect(cam):
    cx, cy, z = cam
    return cx - L.W / 2 / z, cy - L.H / 2 / z, cx + L.W / 2 / z, cy + L.H / 2 / z, z


def check(story, step=0.25):
    r = L.Renderer(story, subs=False)
    issues = {k: [] for k in ("head_cut", "overlap", "prop_overlap", "out_of_bounds", "dup_prop", "floating", "joints",
                              "hand_face", "facing")}
    n_frames = 0
    es = story.get("end_screen")
    for i, sc in enumerate(r.scenes):
        plan = r.plans[i]
        tracks = plan["tracks"]
        t = sc["start"] + 0.5           # skip the crossfade
        end = sc["end"] - 0.5
        if sc.get("moral_card"):
            end = min(end, sc["lines"][-1]["start"] - 0.3)
        if es:
            end = min(end, es[0] - 0.1)
        props = [(pk, nm, px, own, L.prop_extent(pk, nm, px, own, r.looks)) for pk, nm, px, own in plan["props"]]
        while t < end:
            n_frames += 1
            cam = L.camera_at(r.shots[i], t, sc["end"])
            fl, ft, fr, fb, z = frame_rect(cam)
            tol = TOL / z
            poses, geo = {}, {}
            for cid in tracks:
                P = r.pose(t, i, cid)
                poses[cid] = P
                geo[cid] = LC.geometry(r.looks[cid], P)
            where = lambda cid: {"t": round(t, 2), "scene": i, "char": cid}
            visible = {}
            for cid, g in geo.items():
                rl, rr = g["reach"]
                out = rr <= fl or rl >= fr
                visible[cid] = not out
                if out:
                    continue
                hl, ht, hr, hb = g["head_box"]
                if not (hl >= fl - tol and hr <= fr + tol and ht >= ft - tol and hb <= fb + tol):
                    if not poses[cid].get("_walking"):
                        issues["head_cut"].append(dict(where(cid), head=[round(v) for v in g["head_box"]],
                                                       frame=[round(fl), round(ft), round(fr), round(fb)]))
            # bodies overlapping (standing characters only; someone walking past is fine)
            ids = list(geo)
            for a in range(len(ids)):
                for b in range(a + 1, len(ids)):
                    A, B = ids[a], ids[b]
                    if poses[A].get("_walking") or poses[B].get("_walking"):
                        continue
                    if not (visible[A] or visible[B]) or not all(-100 < poses[c]["x"] < L.W + 100 for c in (A, B)):
                        continue
                    al, _, ar, _ = geo[A]["body"]
                    bl, _, br, _ = geo[B]["body"]
                    ov = min(ar, br) - max(al, bl)
                    if ov > 20:
                        issues["overlap"].append(dict(where(A), other=B, px=round(ov)))
            for cid, g in geo.items():
                if poses[cid].get("_walking") or not visible[cid]:
                    continue
                bl, _, br, _ = g["body"]
                for pk, nm, px, own, (pl, pr) in props:
                    if own == cid:
                        continue
                    if pk == "stage" and plan.get("stage_key") and _taken(plan, poses, t):
                        continue
                    ov = min(br, pr) - max(bl, pl)
                    if ov > 30:
                        issues["prop_overlap"].append(dict(where(cid), prop=nm, px=round(ov)))
            # unique objects on screen
            count = {}
            for cid, P in poses.items():
                o = LP.obj_name(P.get("hold"))
                if o:
                    count[o] = count.get(o, 0) + 1
            for gs, ge, obj, a, b in plan["gives"]:
                if gs <= t <= ge:
                    count[obj] = count.get(obj, 0) + 1
            key = plan.get("stage_key")
            if key and not _taken(plan, poses, t):
                count[key] = count.get(key, 0) + 1
            for o, c in count.items():
                if c > 1 and o in L.UNIQUE_OBJ:
                    issues["dup_prop"].append({"t": round(t, 2), "scene": i, "object": o, "count": c})
            # feet, joints, hands, facing
            speaking = {cid for cid in tracks if r.speaking(t, i, cid)}
            for cid, g in geo.items():
                P = poses[cid]
                if abs(P["y"] - L.FLOOR) > 0.5:
                    issues["out_of_bounds"].append(dict(where(cid), why="feet off the floor line", y=P["y"]))
                if cid in speaking and not P.get("_walking") and not (-60 < P["x"] < L.W + 60):
                    issues["out_of_bounds"].append(dict(where(cid), why="speaking off stage", x=round(P["x"])))
                hop = P.get("hop", 0.0) + P.get("bob", 0.0)
                if hop <= 0.01 and g["sole"] < L.FLOOR - 2.0:
                    issues["floating"].append(dict(where(cid), gap=round(L.FLOOR - g["sole"], 1)))
                an = g["angles"]
                bad = []
                for k in ("elbow_l", "elbow_r"):
                    if an[k] < ELBOW_MIN:
                        bad.append(f"{k}={an[k]:.0f}")
                for k in ("knee_l", "knee_r"):
                    if an[k] < KNEE_MIN:
                        bad.append(f"{k}={an[k]:.0f}")
                for s_ in ("l", "r"):
                    if g["elbow_out_" + s_] < -3:
                        bad.append(f"elbow_{s_} folds inward ({g['elbow_out_' + s_]:.0f})")
                    if g["knee_fwd_" + s_] < -2:
                        bad.append(f"knee_{s_} bends backward ({g['knee_fwd_' + s_]:.0f})")
                if bad:
                    issues["joints"].append(dict(where(cid), bad=bad))
                hx, hy, hw, hu, hd = g["head"]
                rf = g["head"][2] / 1.08
                for s_, (px_, py_) in g["hands"].items():
                    if s_ == "l" and r.looks[cid].get("stick"):
                        pass
                    dist = math.hypot(px_ - hx, py_ - hy)
                    if dist < rf * 1.0 + g["hand_r"] * (1 - LC.FACE_CLEAR) - 3:
                        issues["hand_face"].append(dict(where(cid), hand=s_, dist=round(dist), face_r=round(rf)))
            for cid in speaking:
                P = poses[cid]
                if P.get("_walking") or abs(P["facing"]) < 0.99:
                    continue
                ln = next((sc["lines"][li] for a, b, li in tracks[cid]["speak"] if a <= t <= b), None)
                if not ln:
                    continue
                tgt = ln.get("target") if ln.get("target") in tracks and ln.get("target") != cid else None
                if tgt is None:
                    others = [o for o in tracks if o != cid and -200 < poses[o]["x"] < L.W + 200]
                    if not others:
                        continue
                    tgt = min(others, key=lambda o: abs(poses[o]["x"] - P["x"]))
                dx = poses[tgt]["x"] - P["x"]
                just_walked = any(we <= t <= we + 0.3 for ws, we, *_ in tracks[cid]["walks"])
                if abs(dx) > 40 and (dx > 0) != (P["facing"] > 0) and t - ln["start"] > 0.6 and not just_walked:
                    issues["facing"].append(dict(where(cid), target=tgt))
            t += step
    return issues, n_frames


def _taken(plan, poses, t):
    key = plan.get("stage_key")
    return any(LP.obj_name(P.get("hold")) == key for P in poses.values()) or \
        any(gs <= t <= ge and obj == key for gs, ge, obj, a, b in plan["gives"])


def main():
    path = sys.argv[1]
    args = sys.argv[2:]
    step = float(args[args.index("--step") + 1]) if "--step" in args else 0.25
    rep = args[args.index("--report") + 1] if "--report" in args else path[:-5] + "_qc.json"
    story = json.load(open(path, encoding="utf-8"))
    issues, n = check(story, step)
    summary = {k: len(v) for k, v in issues.items()}
    json.dump({"frames": n, "step": step, "summary": summary, "issues": {k: v[:60] for k, v in issues.items()}},
              open(rep, "w"), indent=1)
    bad = {k: v for k, v in summary.items() if v}
    print(f"frame QC: {n} sampled frames, step {step}s -> {summary}")
    for k, v in issues.items():
        if v:
            ex = "; ".join(json.dumps(x, ensure_ascii=False) for x in v[:3])
            print(f"::warning title=frame QC {k}::{len(v)} frames ({len(v) * step:.1f}s). e.g. {ex}"[:1000])
    if not bad:
        print("frame QC: PASS")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
