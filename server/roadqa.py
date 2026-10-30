"""Optional on-build diagnostics of planned profiles; never alters real terrain.

Reports only geometry generated in visited cells. A steep profile is a review item,
not proof that an actual road is wrong. No downloads, extra DEM sampling or auto-flattening.
"""
from collections import OrderedDict
import hashlib
import json
import logging
import os
from pathlib import Path
import threading

import numpy as np

log = logging.getLogger("earthd.roadqa")
_seen = OrderedDict()
_lock = threading.Lock()


def measure(xy, z, cls=""):
    xy, z = np.asarray(xy, np.float64)[:, :2], np.asarray(z, np.float64)
    if len(z) < 2:
        return {"flags": ["too_short"]}
    if not np.isfinite(xy).all() or not np.isfinite(z).all():
        return {"flags": ["non_finite"]}
    ds = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    valid = ds > .05
    slopes = np.diff(z)[valid] / ds[valid]
    curvature = np.abs(np.diff(slopes)) / np.maximum(.05, (ds[valid][:-1]+ds[valid][1:])*.5)
    flags = []
    maxgrade = float(np.max(np.abs(slopes), initial=0))
    maxcurve = float(np.max(curvature, initial=0))
    major = cls in ("motorway", "trunk")
    if maxgrade > (.10 if major else .25):
        flags.append("steep_profile_review")
    if maxcurve > (.005 if major else .02):
        flags.append("abrupt_grade_change_review")
    if np.any((~valid) & (np.abs(np.diff(z)) > .05)):
        flags.append("height_step_at_same_xy")
    return {"flags": flags, "length_m": round(float(ds.sum()), 3), "max_grade_pct":round(maxgrade*100,3),
            "max_grade_change_pct_per_m":round(maxcurve*100,3)}


def record(frame, label, profiles):
    directory = os.environ.get("BNE_ROAD_QA_DIR")
    if not directory:
        return
    try:
        profiles = list(profiles)
        if not profiles:
            return
        first = profiles[0][1][0]
        lat, lon, _ = frame.enu_to_geodetic(float(first[0]), float(first[1]), 0.)
        # The France profile audits metropolitan France/Corsica, leaving other areas untouched.
        if not (41.3 <= lat <= 51.2 and -5.6 <= lon <= 9.9):
            return
        import revisit
        signature = (label, round(float(lat),7), round(float(lon),7), tuple(str(p[0]) for p in profiles))
        key = hashlib.sha256(repr(signature).encode()).hexdigest()[:24]
        with _lock:
            if key in _seen:
                return
            _seen[key] = True
            if len(_seen) > 4096:
                _seen.popitem(last=False)
        findings = []
        for fid, xy, z, cls in profiles:
            m = measure(xy, z, cls)
            if m["flags"]:
                la, lo, _ = frame.enu_to_geodetic(float(xy[0][0]),float(xy[0][1]),0.)
                findings.append(dict(id=str(fid), lat=float(la),lon=float(lo),road_class=cls,**m))
        data = {"scope":"Planned profiles only; not a drive or collision test", "label":label,
                "profile_count":len(profiles), "findings":findings}
        path = Path(directory) / revisit.code_key() / (key + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
        os.replace(tmp,path)
    except Exception as exc:
        log.debug("Road diagnostic skipped: %s", exc)
