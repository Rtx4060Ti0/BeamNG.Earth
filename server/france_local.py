"""Optional, read-only France PBF index. Never opens a partial build or writes in game."""
from functools import lru_cache
import json
import logging
import math
import os
from pathlib import Path
import sqlite3

log = logging.getLogger("earthd.france")


class Index:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.uri = self.path.as_uri() + "?mode=ro"
        con = self.connect()
        try:
            row = con.execute("SELECT value FROM meta WHERE key='manifest'").fetchone()
        finally:
            con.close()
        self.manifest = json.loads(row[0]) if row else {}
        if self.manifest.get("state") != "COMPLETE" or not self.manifest.get("eof") or self.manifest.get("schema") != 1:
            raise ValueError("France index is not complete or its schema is unsupported")

    def connect(self):
        return sqlite3.connect(self.uri, uri=True, timeout=.2)

    def nearby(self, lat, lon, radius=2000.):
        """A nearby *named point*, not containment in an administrative boundary."""
        if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        my = 111320.
        mx = my * max(.05, math.cos(math.radians(lat)))
        dx, dy = radius / mx, radius / my
        con = self.connect()
        try:
            rows = con.execute("""SELECT p.id,p.kind,p.name,p.lat,p.lon FROM place_bbox b JOIN places p ON p.id=b.id
                WHERE b.max_lon>=? AND b.min_lon<=? AND b.max_lat>=? AND b.min_lat<=?""",
                (lon-dx,lon+dx,lat-dy,lat+dy)).fetchall()
        finally:
            con.close()
        candidates = []
        for ident, kind, name, la, lo in rows:
            distance = math.hypot((lo-lon)*mx,(la-lat)*my)
            # A tiny locality is useful only nearby; don't call a remote hamlet the current city.
            limit = radius if kind in ("city","town","village") else 700.
            if distance <= limit:
                candidates.append((distance, ident, kind, name))
        if not candidates:
            return None
        distance, ident, kind, name = min(candidates)
        return {"id": ident, "kind": kind, "name": name, "distance_m": round(distance)}

    def road_tags(self, ids):
        ids = list(dict.fromkeys(int(i) for i in ids if i is not None))
        result = {}
        con = self.connect()
        try:
            for start in range(0, len(ids), 500):
                batch = ids[start:start+500]
                query = "SELECT id,tags FROM roads WHERE id IN (" + ",".join("?" for _ in batch) + ")"
                result.update((i,json.loads(tags)) for i,tags in con.execute(query,batch))
        finally:
            con.close()
        return result


@lru_cache(maxsize=2)
def _open(path):
    try:
        return Index(path)
    except (OSError, ValueError, sqlite3.Error, TypeError) as exc:
        log.warning("France index unavailable: %s", exc)
        return None


def configured():
    path = os.environ.get("BNE_FRANCE_DB", "")
    return _open(path) if path else None


def nearby_label(lat, lon):
    index = configured()
    if index is None:
        return ""
    try:
        place = index.nearby(float(lat),float(lon))
        if not place:
            return ""
        m = place["distance_m"]
        distance = f"{m} m" if m < 1000 else f"{m/1000:.1f} km"
        return f"Repère proche : {place['name']} ({distance})"
    except (OSError, ValueError, sqlite3.Error):
        return ""
