"""Read a France OSM extract without changing it. Publish a validated local index.

This audits highway tags and node references, NOT elevations or in-game collisions.
Only named place nodes and highway ways cross the Python boundary; no planet-sized
node-location table is needed. Dependencies: pyosmium (index creation only).
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

import osmium

SCHEMA = 1
PLACES = {"city", "town", "village", "hamlet", "isolated_dwelling", "locality", "suburb", "quarter", "neighbourhood"}
MOTOR = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link",
         "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service", "road"}
TAGS = {"name", "name:fr", "ref", "highway", "bridge", "tunnel", "layer", "level", "incline", "lanes", "width",
        "maxspeed", "sidewalk", "lit", "smoothness", "surface", "oneway", "access", "vehicle", "motor_vehicle",
        "maxheight", "maxweight", "destination", "destination:forward", "destination:backward", "destination:ref",
        "destination:lanes", "junction"}


def issues(tags, refs):
    out = []
    if len(refs) < 2 or len(set(refs)) < 2:
        out.append("degenerate_way")
    if any(a == b for a, b in zip(refs, refs[1:])):
        out.append("repeated_adjacent_node")
    if tags.get("layer"):
        try:
            int(tags["layer"])
        except ValueError:
            out.append("non_integer_layer")
    if tags.get("bridge", "no") not in ("no", "") and tags.get("tunnel", "no") not in ("no", ""):
        out.append("bridge_and_tunnel_review")
    return out


def write_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def build(source, output):
    source, output = source.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(f"Index already exists; choose a new output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".partial")
    if partial.exists():
        raise FileExistsError(f"Previous partial retained; choose a new output: {partial}")
    status = output.with_suffix(".progress.json")
    before = source.stat()
    started = time.monotonic()
    counts, classes, warnings = Counter(), Counter(), Counter()
    state = {"state": "RUNNING", "phase": "read_pbf", "source": str(source), "output": str(output),
             "source_bytes": before.st_size, "schema": SCHEMA, "eof": False,
             "scope": "All highway ways and named place nodes in the extract; no DEM/collision validation."}
    con = sqlite3.connect(partial)
    con.executescript("""
        PRAGMA journal_mode=DELETE; PRAGMA synchronous=NORMAL; PRAGMA cache_size=-32768;
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE roads (id INTEGER PRIMARY KEY, highway TEXT, name TEXT, bridge INTEGER, tunnel INTEGER,
                            node_count INTEGER, first_node INTEGER, last_node INTEGER, tags TEXT NOT NULL);
        CREATE TABLE places (id INTEGER PRIMARY KEY, kind TEXT, name TEXT, lat REAL, lon REAL);
        CREATE VIRTUAL TABLE place_bbox USING rtree(id, min_lon, max_lon, min_lat, max_lat);
        CREATE TABLE findings (way_id INTEGER, reason TEXT);
    """)
    rows, places, findings = [], [], []

    def progress(phase=None):
        if phase:
            state["phase"] = phase
        state.update(elapsed_s=round(time.monotonic() - started, 1), counts=dict(counts),
                     classes=dict(classes), findings=dict(warnings))
        write_json(status, state)
        print(json.dumps({k: state[k] for k in ("phase", "elapsed_s", "counts")}), flush=True)

    def flush():
        con.executemany("INSERT INTO roads VALUES (?,?,?,?,?,?,?,?,?)", rows)
        con.executemany("INSERT INTO places VALUES (?,?,?,?,?)", places)
        con.executemany("INSERT INTO place_bbox VALUES (?,?,?,?,?)", [(r[0], r[4], r[4], r[3], r[3]) for r in places])
        con.executemany("INSERT INTO findings VALUES (?,?)", findings)
        con.commit()
        rows.clear(); places.clear(); findings.clear()

    progress()
    try:
        fp = osmium.FileProcessor(source, osmium.osm.NODE | osmium.osm.WAY).with_filter(osmium.filter.KeyFilter("highway", "place"))
        header = fp.header
        state["replication_timestamp"] = header.get("osmosis_replication_timestamp")
        last = time.monotonic()
        for obj in fp:
            if obj.is_node():
                kind = obj.tags.get("place", "")
                name = obj.tags.get("name:fr") or obj.tags.get("name")
                if kind in PLACES and name and obj.location.valid():
                    places.append((obj.id, kind, name, obj.location.lat, obj.location.lon))
                    counts["places"] += 1
            elif obj.is_way() and obj.tags.get("highway"):
                tags = {t.k: t.v for t in obj.tags if t.k in TAGS}
                highway = tags["highway"]
                bridge = tags.get("bridge", "no") not in ("no", "")
                tunnel = tags.get("tunnel", "no") not in ("no", "")
                refs = [n.ref for n in obj.nodes]
                rows.append((obj.id, highway, tags.get("name:fr") or tags.get("name", ""), int(bridge), int(tunnel),
                             len(refs), refs[0] if refs else None, refs[-1] if refs else None,
                             json.dumps(tags, ensure_ascii=False, separators=(",", ":"))))
                counts["highway_ways"] += 1
                counts["motor_road_ways"] += highway in MOTOR
                counts["bridge_ways"] += bridge
                counts["tunnel_ways"] += tunnel
                counts["motor_bridge_ways"] += bridge and highway in MOTOR
                counts["motor_tunnel_ways"] += tunnel and highway in MOTOR
                counts["destination_ways"] += any(k.startswith("destination") for k in tags)
                classes[highway] += 1
                found = issues(tags, refs)
                findings.extend((obj.id, reason) for reason in found)
                warnings.update(found)
            if len(rows) + len(places) >= 5000:
                flush()
            if time.monotonic() - last > 10:
                progress()
                last = time.monotonic()
        flush()
        state["eof"] = True
        progress("hash_source")
        sha = hashlib.file_digest(source.open("rb"), "sha256").hexdigest()
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError("Source changed during indexing")
        progress("validate_sqlite")
        con.execute("CREATE INDEX roads_name ON roads(name)")
        con.execute("CREATE INDEX findings_way ON findings(way_id)")
        check = con.execute("PRAGMA integrity_check").fetchall()
        if check != [("ok",)] or not counts["highway_ways"] or not counts["places"]:
            raise RuntimeError(f"Index validation failed: {check}")
        if con.execute("SELECT count(*) FROM roads").fetchone()[0] != counts["highway_ways"]:
            raise RuntimeError("Road count mismatch")
        if con.execute("SELECT count(*) FROM place_bbox").fetchone()[0] != counts["places"]:
            raise RuntimeError("Place count mismatch")
        state.update(state="COMPLETE", phase="ready", sha256=sha, integrity="ok", elapsed_s=round(time.monotonic()-started, 1),
                     counts=dict(counts), classes=dict(classes), findings=dict(warnings))
        con.execute("INSERT INTO meta VALUES ('manifest', ?)", (json.dumps(state, ensure_ascii=False),))
        con.commit()
        con.close()
        os.replace(partial, output)
        write_json(output.with_suffix(".report.json"), state)
        write_json(status, state)
        print(json.dumps(state, ensure_ascii=False), flush=True)
    except BaseException as exc:
        con.close()
        state.update(state="FAILED", error=f"{type(exc).__name__}: {exc}")
        progress()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.source, args.output)
