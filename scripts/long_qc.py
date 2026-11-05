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
MOTION checks (sampled at 8 fps, what the viewer sees moving):
  frozen         a character on screen > 3 s with no pose change (arms, head, hips, lean, position, facing)
  speaker_static a speaker with no gesture / action change for > 2 s while talking
  narration_idle a narrator line about a character (named / actor) with no visible matching action beat
  turn_squash    a character drawn narrower than full width (|facing| < 1) - turns must mirror, never squash
STAGING checks (HARD failures: exit 2, the episode is not made):
  speaker_hidden    a dialogue line whose speaker is not on screen (head fully in frame) or whose mouth never moves
  reaction_in_line  a reaction / listener shot cut in while the speaker is still talking
  teleport          a character changing position faster than a run (a cut moved somebody)
  order_flip        two standing characters swapping sides within a scene (180-degree rule)
  partner_far       conversation partners (adjacent marks) more than 2.0 head-widths apart, face to face
  partner_facing    conversation partners not facing each other
  narration_hidden  a narration line naming characters on stage while none of them is on screen
Prints a summary (GitHub ::warning / ::error annotations per failing category); exit 2 on a staging failure,
1 when only the softer frame checks fail, 0 when everything passes.
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
    motion_checks(r, story, issues)
    staging_checks(r, story, issues, step)
    return issues, n_frames


HARD = ("speaker_hidden", "reaction_in_line", "teleport", "order_flip", "partner_far", "partner_facing", "narration_hidden")
PARTNER_GAP_MAX = 2.0     # head-widths between the two faces (edge to edge)


def staging_checks(r, story, issues, step=0.25):
    for k in HARD + ("partner_split",):
        issues.setdefault(k, [])
    for i, sc in enumerate(r.scenes):
        tracks = r.plans[i]["tracks"]
        shots = r.shots[i]
        # teleports: any keyframe pair moving faster than a run, on stage
        for cid, tr in tracks.items():
            ks = tr["keys"]
            for (ta, xa), (tb, xb) in zip(ks, ks[1:]):
                if abs(xb - xa) < 40 or (min(xa, xb) > L.W + 150 or max(xa, xb) < -150):
                    continue
                if (tb - ta) < 1e-6 or abs(xb - xa) / (tb - ta) > L.WALK_SPEED * 2.4:
                    issues["teleport"].append({"t": round(ta, 2), "scene": i, "char": cid, "from": round(xa), "to": round(xb)})
        # 180-degree rule: the left-to-right order of standing characters never changes inside a scene
        sides = {}
        t = sc["start"] + 0.3
        while t < sc["end"] - 0.3:
            P = {c: r.pose(t, i, c) for c in tracks}
            st = [c for c in tracks if -100 < P[c]["x"] < L.W + 100 and not P[c].get("_walking")]
            for a in range(len(st)):
                for b in range(a + 1, len(st)):
                    k = (st[a], st[b])
                    sgn = P[st[a]]["x"] < P[st[b]]["x"]
                    if k in sides and sides[k] != sgn:
                        issues["order_flip"].append({"t": round(t, 2), "scene": i, "pair": list(k)})
                    sides[k] = sgn
            t += 0.5
        # dialogue: speaker on screen + mouth moving; no listener cut inside a line; partners close + face to face
        for li, ln in enumerate(sc["lines"]):
            sp = ln.get("speaker")
            a_, b_ = ln["start"] + 0.12, ln["end"] - 0.1
            if sp in tracks:
                for sh in shots:
                    if len(sh) > 5 and sh[5] == "reaction" and a_ < sh[0] < b_:
                        issues["reaction_in_line"].append({"t": round(sh[0], 2), "scene": i, "line": li, "speaker": sp})
                hidden, opened, n = 0, 0, 0
                t = a_
                while t < b_:
                    cam = L.camera_at(shots, t, sc["end"])
                    fl, ft, fr, fb, z = frame_rect(cam)
                    P = r.pose(t, i, sp)
                    g = LC.geometry(r.looks[sp], P)
                    hl, ht, hr, hb = g["head_box"]
                    tol = TOL / z
                    if not (hl >= fl - tol and hr <= fr + tol and ht >= ft - tol and hb <= fb + tol):
                        hidden += 1
                    m = r.mouth(t, i, sp)
                    if m and m.get("open", 0) > 0.12:
                        opened += 1
                    n += 1
                    t += step / 2
                if n and hidden:
                    issues["speaker_hidden"].append({"t": ln["start"], "scene": i, "line": li, "speaker": sp,
                                                     "hidden_frac": round(hidden / n, 2)})
                elif n >= 4 and opened == 0:
                    issues["speaker_hidden"].append({"t": ln["start"], "scene": i, "line": li, "speaker": sp, "why": "mouth never opens"})
                mate = r.addressee(i, li, sp, ln["start"] + 0.3)
                if mate:
                    t = ln["start"] + 0.6
                    while t < ln["end"] - 0.2:
                        Ps, Pm = r.pose(t, i, sp), r.pose(t, i, mate)
                        if not (Ps.get("_walking") or Pm.get("_walking")) and all(-100 < p["x"] < L.W + 100 for p in (Ps, Pm)):
                            hw_s, hw_m = L.head_w(r.looks[sp]), L.head_w(r.looks[mate])
                            gap = (abs(Ps["x"] - Pm["x"]) - (hw_s + hw_m) / 2) / ((hw_s + hw_m) / 2)
                            between = [o for o in tracks if o not in (sp, mate) and min(Ps["x"], Pm["x"]) < r.pose(t, i, o)["x"] < max(Ps["x"], Pm["x"])]
                            if gap > PARTNER_GAP_MAX:
                                issues["partner_split" if between else "partner_far"].append(
                                    {"t": round(t, 2), "scene": i, "line": li, "pair": [sp, mate], "gap_hw": round(gap, 2)})
                            dx = Pm["x"] - Ps["x"]
                            if abs(dx) > 40 and not between and ((dx > 0) != (Ps["facing"] > 0) or (dx > 0) == (Pm["facing"] > 0)):
                                just = any(we <= t <= we + 0.5 for ws, we, *_ in tracks[sp]["walks"] + tracks[mate]["walks"])
                                if not just:
                                    issues["partner_facing"].append({"t": round(t, 2), "scene": i, "line": li, "pair": [sp, mate]})
                            break
                        t += 0.5
            else:
                on = [c for c in tracks if -100 < r.pose(ln["start"] + 0.3, i, c)["x"] < L.W + 100]
                named = [c for c in r.mentioned(ln, on)]
                if named and ln["start"] - sc["start"] > 3.0:
                    seen, n = 0, 0
                    t = a_
                    while t < b_:
                        cam = L.camera_at(shots, t, sc["end"])
                        fl, ft, fr, fb, z = frame_rect(cam)
                        for c in named:
                            g = LC.geometry(r.looks[c], r.pose(t, i, c))
                            hl, ht, hr, hb = g["head_box"]
                            if hl >= fl and hr <= fr:
                                seen += 1
                                break
                        n += 1
                        t += step
                    if n and seen < 0.6 * n:
                        issues["narration_hidden"].append({"t": ln["start"], "scene": i, "line": li, "named": named,
                                                           "seen_frac": round(seen / n, 2)})


SIG_TOL = {"lh": 16.0, "rh": 16.0, "head_tilt": 3.5, "hip_shift": 4.5, "lean": 2.5, "x": 10.0, "dip": 4.0}


def _sig(P):
    return {"lh": P["lh"], "rh": P["rh"], "head_tilt": P["head_tilt"], "hip_shift": P["hip_shift"], "lean": P["lean"],
            "x": P["x"], "dip": P["dip"], "facing": 1 if P["facing"] > 0 else -1, "hold": P.get("hold"),
            "smile": round(P.get("smile", 0), 1), "gest": (P.get("_gest"), P.get("_act"))}


def _changed(a, b):
    for k, tol in SIG_TOL.items():
        va, vb = a[k], b[k]
        if isinstance(va, tuple):
            if math.hypot(va[0] - vb[0], va[1] - vb[1]) > tol:
                return True
        elif abs(va - vb) > tol:
            return True
    return a["facing"] != b["facing"] or a["hold"] != b["hold"] or abs(a["smile"] - b["smile"]) > 0.25


def motion_checks(r, story, issues, fps=8.0):
    for k in ("frozen", "speaker_static", "narration_idle", "turn_squash"):
        issues.setdefault(k, [])
    es = story.get("end_screen")
    for i, sc in enumerate(r.scenes):
        tracks = r.plans[i]["tracks"]
        end = sc["end"] - 0.3
        if sc.get("moral_card"):
            end = min(end, sc["lines"][-1]["start"] - 0.3)
        if es:
            end = min(end, es[0] - 0.1)
        last_sig, last_t, flagged = {}, {}, {}
        last_g, last_gt = {}, {}
        vis_time = {}
        t = sc["start"] + 0.35
        shot_i = None
        while t < end:
            cam = L.camera_at(r.shots[i], t, sc["end"])
            si = max(k_ for k_, sh in enumerate(r.shots[i]) if sh[0] <= t) if r.shots[i][0][0] <= t else 0
            fl, ft, fr, fb, z = frame_rect(cam)
            for cid in tracks:
                P = r.pose(t, i, cid)
                if abs(P["facing"]) < 0.99:
                    issues["turn_squash"].append({"t": round(t, 2), "scene": i, "char": cid, "facing": round(P["facing"], 2)})
                g = LC.geometry(r.looks[cid], P)
                rl, rr = g["reach"]
                visible = not (rr <= fl or rl >= fr)
                vis_time.setdefault(cid, []).append((t, visible))
                sig = _sig(P)
                if not visible or si != shot_i and cid not in last_sig:
                    last_sig[cid], last_t[cid] = sig, t
                if not visible:
                    flagged[cid] = False
                    continue
                if cid not in last_sig or _changed(sig, last_sig[cid]):
                    last_sig[cid], last_t[cid], flagged[cid] = sig, t, False
                elif t - last_t[cid] > 3.0 and not flagged.get(cid):
                    issues["frozen"].append({"t": round(last_t[cid], 2), "scene": i, "char": cid, "held_s": round(t - last_t[cid], 1)})
                    flagged[cid] = True
                if r.speaking(t, i, cid) and not P.get("_walking"):
                    gk = (P.get("_gest"), P.get("_act"))
                    if cid not in last_g or last_g[cid] != gk or t - last_gt.get(cid, -9) > 50:
                        if cid in last_g and last_g[cid] == gk:
                            pass
                        last_g[cid], last_gt[cid] = gk, t
                    elif t - last_gt[cid] > 2.0:
                        issues["speaker_static"].append({"t": round(last_gt[cid], 2), "scene": i, "char": cid, "gesture": list(map(str, gk))})
                        last_gt[cid] = t
                else:
                    last_g.pop(cid, None)
            shot_i = si
            t += 1.0 / fps
        # narration lines: the character they describe must visibly act, on screen, while they are told
        for li, ln in enumerate(sc["lines"]):
            if ln.get("speaker") in tracks:
                continue
            actor = ln.get("actor") if ln.get("actor") in tracks else None
            if not actor:
                continue
            beats = [b for b in (ln.get("beats") or []) if b[2] == actor]
            moved = any(ws < ln["end"] and we > ln["start"] for ws, we, *_ in tracks[actor]["walks"])
            if not beats and not moved:
                issues["narration_idle"].append({"t": ln["start"], "scene": i, "char": actor, "why": "no action beat"})
                continue
            seen = [v for tt, v in vis_time.get(actor, []) if ln["start"] <= tt <= ln["end"]]
            if seen and sum(seen) < 0.5 * len(seen):
                issues["narration_idle"].append({"t": ln["start"], "scene": i, "char": actor, "why": "actor off screen"})


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
    bad = {k: v for k, v in summary.items() if v and k != "partner_split"}
    hard = {k: v for k, v in bad.items() if k in HARD}
    print(f"frame QC: {n} sampled frames, step {step}s -> {summary}")
    for k, v in issues.items():
        if v:
            ex = "; ".join(json.dumps(x, ensure_ascii=False) for x in v[:3])
            lvl = "error" if k in HARD else "warning"
            print(f"::{lvl} title=frame QC {k}::{len(v)} cases. e.g. {ex}"[:1000])
    if not bad:
        print("frame QC: PASS")
    elif not hard:
        print("frame QC: staging PASS (soft frame warnings only)")
    else:
        print("frame QC: STAGING FAIL " + ", ".join(f"{k}={v}" for k, v in hard.items()))
    sys.exit(2 if hard else (1 if bad else 0))


if __name__ == "__main__":
    main()
