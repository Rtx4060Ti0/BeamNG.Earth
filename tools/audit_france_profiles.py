"""Measure generated road/bridge/tunnel centrelines at French regression sites.

Uses the current server algorithms and local map cache. Missing cells are recorded;
a report with missing data is not a complete validation. No driving/collision claim.
"""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import numpy as np
import dem
import geodesy
import grading
import mapcells
import mapdata
import mapgeom
import netfetch
import overture
import roads
import roadwidth

SITES = [("Annonay Malleval", 45.241695, 4.669288), ("Annonay Viaduc", 45.2482, 4.6763),
         ("Saint-Vallier tunnel", 45.171574, 4.822146), ("A7 Salaise", 45.35870, 4.80566),
         ("A7 Revollon", 45.31910, 4.81215),
         ("Annonay Etienne Frachon", 45.24672, 4.66239),
         ("Davezieux road wall", 45.26196, 4.70783),
         ("Peaugres Route de Lyon", 45.27093, 4.71525),
         ("Peaugres Le Flacher", 45.29916, 4.73516),
         ("Sablons Route des Alpes", 45.31848, 4.80529),
         ("Andance Saint-Clair", 45.24268, 4.79968),
         ("Saint-Vallier north portal", 45.17325, 4.82430),
         ("Montpellier Helene Boucher", 43.58140, 3.94327),
         ("Serrieres rail crossing", 45.31744, 4.76511),
         ("A7 Bouterne crossing", 45.08932, 4.87906),
         ("A7 south Saint-Vallier", 45.11959, 4.89512),
         ("Route de Saint-Donat", 45.16951, 4.88466),
         ("Rue Pierre Mendes France", 45.17714, 4.81614),
         ("RD82 Saint-Etienne-de-Valoux", 45.24067, 4.79555),
         ("Viaduc Daniel Aime south joint", 45.24793, 4.67659)]


class CachedMap(mapdata.MapData):
    def __init__(self, cache, online=False):
        super().__init__(str(cache), fetcher=netfetch.Fetcher(offline=not online))
        self.missing = set()

    def cell(self, key, layers=("roads",), kind="demand"):
        # Use the live decoder, including its road/rail tags and grade-separation
        # hook. Loading raw NPZ arrays alone silently bypassed those corrections.
        try:
            return super().cell(key, layers, kind)
        except netfetch.FetchError as exc:
            self.missing.add(f"{key} {','.join(layers)}: {exc}")
            return SimpleNamespace(layers={layer: None for layer in layers})


def metrics(xy, z):
    s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    ds = np.diff(s)
    valid = ds > .05
    slopes = np.diff(z)[valid] / ds[valid]
    changes = np.diff(slopes)
    return {"length_m": float(s[-1]), "max_grade_pct": float(np.max(np.abs(slopes), initial=0) * 100),
            "max_grade_change_pct": float(np.max(np.abs(changes), initial=0) * 100),
            "finite": bool(np.isfinite(z).all()), "s": s.tolist(), "z": np.asarray(z).tolist()}


def audit(cache, output, selected, radius=260, online_dem=False, online_map=False):
    report = {"scope": "Generated centrelines, 2 m samples. Not a driving test. Bridge water constraints omitted.",
              "overture_release": overture.RELEASE, "sites": []}
    height = dem.Dem(str(cache / "dem"), fetch_workers=4, fetcher=netfetch.Fetcher(offline=not online_dem))
    try:
        for name, lat, lon in SITES:
            if selected and name not in selected:
                continue
            started = time.monotonic()
            md = CachedMap(cache, online_map)
            md.dem = height
            frame = geodesy.EnuFrame(lat, lon, 0.)
            widths = roadwidth.RoadWidths(lambda k: md.cell(k, ("buildings",)).layers["buildings"])
            elev = lambda a, b: height.sample(a, b, grading.PROFILE_ZOOM)
            grader = grading.Grader(frame, md, elev, widths.get)
            physical = lambda a, b: grader.apply(a, b, elev(a, b), grading.ROAD_LIFT)
            site = {"name": name, "lat": lat, "lon": lon, "profiles": []}
            seen, feats = set(), []
            for key in mapcells.cells_for_bbox(lat-.004, lon-.006, lat+.004, lon+.006):
                f = md.cell(key).layers["roads"]
                if f is None:
                    continue
                feats.append(f)
                specs = roads.road_specs(f, widths=widths.get)
                for i in range(len(f)):
                    fid = str(f.ids[i])
                    sp = specs[i]
                    if fid in seen or sp is None or sp.kind not in roads.BUILT:
                        continue
                    seen.add(fid)
                    for ll in roads.ground_parts(f, i):
                        e, n, _ = frame.geodetic_to_enu(ll[:, 1], ll[:, 0], 0.)
                        line = np.c_[e, n]
                        if roads._seg_dist(np.zeros((1, 2)), line[:-1], line[1:]).min() > radius:
                            continue
                        for piece in grading.clip_polyline(line, (-radius, -radius, radius, radius)):
                            xy, _ = grading.resample(piece, 2.)
                            if len(xy) < 3:
                                continue
                            la, lo, _ = frame.enu_to_geodetic(xy[:, 0], xy[:, 1], 0.)
                            z = physical(la, lo)
                            site["profiles"].append({"id": fid, "name": str(f.attrs.get("name", [""]*len(f))[i]),
                                                     "kind": "road", "class": sp.cls, "xy": xy.tolist(), **metrics(xy,z)})
            cell = lambda k: md.cell(k).layers["roads"]
            for kind, bp in (("bridge", roads.BridgeProfiles(frame, cell, physical)),
                             ("tunnel", roads.TunnelProfiles(frame, cell, elev))):
                if kind == "tunnel":
                    bp.raw = elev
                    bp.ends = lambda a, b: grader.apply(a, b, elev(a, b), grading.ROAD_LIFT, roads_only=True)
                for fid, sp, xy, z, _ in bp.parts(feats, (-radius, -radius, radius, radius)):
                    item = {"id": fid, "kind": kind, "class": sp.cls, "xy": xy.tolist(), **metrics(xy,z)}
                    if kind == "bridge":
                        item["end_step_m"] = (np.asarray(z)[[0,-1]] - bp._ground(np.asarray(xy)[[0,-1]])).tolist()
                    site["profiles"].append(item)
            site.update(missing_cache=sorted(md.missing), elapsed_s=round(time.monotonic()-started,2))
            md.close()
            report["sites"].append(site)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            worst = sorted(site["profiles"], key=lambda r:r["max_grade_change_pct"], reverse=True)[:5]
            print(json.dumps({"site": name, "profiles":len(site["profiles"]), "missing":len(md.missing),
                              "seconds":site["elapsed_s"], "worst":[{k:v for k,v in r.items() if k not in ("s","z","xy")} for r in worst]}, ensure_ascii=False), flush=True)
    finally:
        height.pool.shutdown()
        height.urgent_pool.shutdown()
        height.probe_pool.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path.home()/".cache/beamng-earth")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site", action="append")
    parser.add_argument("--online-dem", action="store_true")
    parser.add_argument("--online-map", action="store_true")
    args = parser.parse_args()
    audit(args.cache, args.output, args.site, online_dem=args.online_dem, online_map=args.online_map)
