"""Drive a supplied world-space route using real vehicle physics and save evidence.

Input is a JSON list of [x,y,z] points in the CURRENT Earth anchor. Placement is
performed only at the start by BeamNG's AI. No teleport or repair during the run.
The vehicle is parked and AI disabled on every exit. Use an expendable test car.
"""
import argparse
import json
import math
from pathlib import Path
import time

import mcp


def lua(code):
    return mcp.call("run_lua", {"code": code})


def stop():
    lua("local v=getPlayerVehicle(0); if v then "
        "v:queueLuaCommand([[ai.setMode('disabled'); input.event('throttle',0,2); "
        "input.event('brake',0,2); input.event('steering',0,2); "
        "input.event('parkingbrake',1,2); controller.setFreeze(1)]]) "
        "v:applyClusterVelocityScaleAdd(-1,0,0,0,0) end return 'parked'")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("route", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--speed", type=float, default=7.0)
    ap.add_argument("--seconds", type=float, default=60.0)
    args = ap.parse_args()
    pts = json.loads(args.route.read_text(encoding="utf-8"))
    if len(pts) < 3 or not all(len(p) == 3 and all(math.isfinite(v) for v in p) for p in pts):
        raise ValueError("Need at least three finite world-space points")
    state = json.loads(mcp.call("get_status"))
    if state["vehicle"]["jbeam"] != "pickup":
        raise RuntimeError("Only the temporary stock pickup may be used")
    route = [{"x":x, "y":y, "z":z, "r":2.5} for x,y,z in pts]
    spec = {"script":route, "routeSpeed":args.speed, "routeSpeedMode":"limit",
            "driveInLane":"off", "avoidCars":"off", "aggression":0.3}
    # Repair the test vehicle before, never during, the measured traversal.
    mcp.call("set_position", {"pos":dict(zip(("x","y","z"), (pts[0][0],pts[0][1],pts[0][2]+0.5)))})
    lua("local v=getPlayerVehicle(0); v:queueLuaCommand([[controller.setFreeze(0); "
        "input.event('parkingbrake',0,2); input.event('brake',0,2); input.event('throttle',0,2)]]) return 'ready'")
    out = {"method":"Real AI drive, initial placement only; no reset or teleport during measurement",
           "route":pts, "requested_speed_m_s":args.speed, "samples":[], "result":"timeout"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        lua("getPlayerVehicle(0):queueLuaCommand([==[ai.driveUsingPath(jsonDecode([===[" +
            json.dumps(spec) + "]===]))]==]); return 'started'")
        started = time.monotonic()
        while time.monotonic() - started < args.seconds:
            time.sleep(0.6)
            s = json.loads(mcp.call("get_status"))["vehicle"]
            p = s["pos"]
            distance = math.hypot(p["x"]-pts[-1][0], p["y"]-pts[-1][1])
            out["samples"].append({"t":round(time.monotonic()-started,3), "distance_to_end_m":distance, **s})
            if s["damage"] > 1:
                out["result"] = "damage"
                break
            if p["z"] < min(q[2] for q in pts) - 3:
                out["result"] = "fall"
                break
            if distance < 4.0:
                out["result"] = "reached"
                break
    finally:
        stop()
        out["elapsed_s"] = round(time.monotonic()-started,3)
        samples = out["samples"]
        out["max_damage"] = max((s["damage"] for s in samples), default=None)
        out["distance_m"] = sum(math.dist([a["pos"][k] for k in ("x","y","z")],
                                         [b["pos"][k] for k in ("x","y","z")]) for a,b in zip(samples,samples[1:]))
        args.out.write_text(json.dumps(out,indent=2), encoding="utf-8")
        print(json.dumps({k:v for k,v in out.items() if k not in ("route","samples")}), flush=True)
    return 0 if out["result"] == "reached" and out["max_damage"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
