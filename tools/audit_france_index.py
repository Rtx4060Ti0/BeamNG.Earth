"""Audit EVERY highway way in a completed local France index, without editing it.

This checks tags and stored reference diagnostics, not generated terrain, water,
mesh intersections, or physical collisions. Outputs are atomically published only
after EOF, count validation, SQLite quick_check and an unchanged input check.
Only the extract's coverage is audited (the supplied France extract is mainland
France and Corsica, NOT overseas France). Missing tags are coverage gaps, not errors.
"""
import argparse
from collections import Counter
import csv
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time

MOTOR = set('motorway motorway_link trunk trunk_link primary primary_link secondary secondary_link tertiary tertiary_link unclassified residential living_street service road'.split())
MAJOR = {'motorway', 'motorway_link', 'trunk', 'trunk_link'}
MEASURES = ('width', 'incline', 'layer', 'lanes', 'maxheight', 'oneway')
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)'
REASONS = {
    'degenerate_way': 'Troncon sans deux noeuds distincts',
    'repeated_adjacent_node': 'Noeuds consecutifs repetes',
    'bridge_and_tunnel_review': 'Pont et tunnel sur le meme troncon : examiner',
    'layer_unparsed': 'Niveau vertical non entier : examiner',
    'layer_extreme_review': 'Niveau vertical hors -5 a +5 : examiner',
    'width_unparsed': 'Largeur non interpretee par cet audit',
    'width_nonpositive': 'Largeur nulle ou negative',
    'narrow_motor_road_review': 'Chaussee motorisee declaree sous 1,8 m : examiner',
    'width_extreme_review': 'Largeur declaree superieure a 50 m : examiner',
    'incline_unparsed': 'Pente non interpretee par cet audit',
    'incline_extreme_review': 'Pente motorisee declaree forte : examiner',
    'lanes_unparsed': 'Nombre de voies non entier : examiner',
    'lanes_extreme_review': 'Nombre de voies hors 1 a 12 : examiner',
    'low_headroom_review': 'Hauteur limitee sous 2 m sur une voie motorisee',
    'oneway_unparsed': 'Sens unique non interprete par cet audit',
}


def metres(value):
    value = value.strip()
    feet = re.fullmatch(r'(\d+)\s*\'\s*(\d+(?:\.\d+)?)?\s*"?', value)
    if feet:
        return float(feet[1]) * .3048 + float(feet[2] or 0) * .0254
    m = re.fullmatch(rf'({NUMBER})\s*(m|km|cm|ft|mi)?', value)
    if not m:
        return None
    return float(m[1]) * {None: 1, 'm': 1, 'km': 1000, 'cm': .01, 'ft': .3048, 'mi': 1609.344}[m[2]]


def grade(value):
    m = re.fullmatch(rf'({NUMBER})\s*(%|°)?', value.strip())
    if not m:
        return None
    n = float(m[1])
    if m[2] == '°':
        return math.copysign(float('inf'), n) if abs(n) >= 90 else math.tan(math.radians(n)) * 100
    return n


def inspect(tags, node_count, first, last):
    """Return review reasons, never modify/flatten the map from a tag alone."""
    out = []
    cls = tags.get('highway', '')
    motor = cls in MOTOR
    bridge = tags.get('bridge', 'no') not in ('no', '')
    tunnel = tags.get('tunnel', 'no') not in ('no', '')
    if node_count < 2 or (node_count == 2 and first == last):
        out.append('degenerate_way')
    if bridge and tunnel:
        out.append('bridge_and_tunnel_review')
    layer = tags.get('layer')
    if layer:
        if not re.fullmatch(r'[+-]?\d+', layer):
            out.append('layer_unparsed')
        elif abs(int(layer)) > 5:
            out.append('layer_extreme_review')
    if tags.get('width'):
        n = metres(tags['width'])
        if n is None:
            out.append('width_unparsed')
        elif n <= 0:
            out.append('width_nonpositive')
        elif motor and n < 1.8:
            out.append('narrow_motor_road_review')
        elif n > 50:
            out.append('width_extreme_review')
    if tags.get('incline') and tags['incline'] not in ('up', 'down', 'up/down'):
        n = grade(tags['incline'])
        if n is None:
            out.append('incline_unparsed')
        elif motor and abs(n) > (10 if cls in MAJOR else 25):
            out.append('incline_extreme_review')
    if tags.get('lanes'):
        if not re.fullmatch(r'\d+', tags['lanes']):
            out.append('lanes_unparsed')
        elif not 1 <= int(tags['lanes']) <= 12:
            out.append('lanes_extreme_review')
    if tags.get('maxheight') and motor:
        n = metres(tags['maxheight'])
        if n is not None and n < 2:
            out.append('low_headroom_review')
    if tags.get('oneway') and tags['oneway'] not in ('yes', 'no', '-1', '1', 'true', 'false', 'reversible', 'alternating'):
        out.append('oneway_unparsed')
    return out


def save_json(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def audit(source, output):
    source, output = source.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(output)
    partial = output.with_name(output.name + '.partial')
    partial.mkdir(parents=True, exist_ok=False)
    before = source.stat()
    started = time.monotonic()
    con = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    counts, reasons, coverage = Counter(), Counter(), Counter()
    report = {'state': 'RUNNING', 'eof': False, 'source': str(source),
              'date_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'All highway rows in the input extract; tags and stored reference diagnostics only.',
              'not_checked': ['DEM elevations and slope continuity', 'water surfaces', 'building/road intersection',
                              'bridge deck clearance and collision', 'tunnel openings', 'physical driving',
                              'areas absent from the input extract, including overseas France'],
              'thresholds_are_review_triggers_not_road_design_standards': True,
              'reasons': REASONS}

    def progress(phase):
        report.update(phase=phase, elapsed_s=round(time.monotonic()-started, 2), counts=dict(counts),
                      findings=dict(reasons), coverage=dict(coverage))
        save_json(partial / 'progress.json', report)
        print(json.dumps({'phase': phase, 'read': counts['highway_ways'], 'total': report.get('expected_ways'),
                          'elapsed_s': report['elapsed_s']}), flush=True)

    try:
        manifest = json.loads(con.execute("SELECT value FROM meta WHERE key='manifest'").fetchone()[0])
        if manifest.get('state') != 'COMPLETE' or not manifest.get('eof') or manifest.get('schema') != 1:
            raise ValueError('Input index is incomplete or unsupported')
        report['source_manifest'] = manifest
        report['expected_ways'] = manifest['counts']['highway_ways']
        progress('sqlite_check')
        if con.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed')
        report['sqlite_quick_check'] = 'ok'
        report['named_place_bounds'] = con.execute('SELECT min(lat),max(lat),min(lon),max(lon) FROM places').fetchone()
        # Preserve reference diagnostics from the full PBF pass; the compact index
        # intentionally does not store every intermediate node reference.
        inherited = {}
        for way, reason in con.execute('SELECT way_id,reason FROM findings'):
            inherited.setdefault(way, set()).add('layer_unparsed' if reason == 'non_integer_layer' else reason)
        with (partial / 'points-a-examiner.csv').open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['way_id', 'osm_url', 'highway', 'name', 'reasons', 'tags'])
            last_progress = time.monotonic()
            for way, cls, name, bridge, tunnel, nodes, first, last, raw in con.execute('SELECT * FROM roads ORDER BY id'):
                tags = json.loads(raw)
                counts['highway_ways'] += 1
                counts['motor_road_ways'] += cls in MOTOR
                counts['bridge_ways'] += bool(bridge)
                counts['tunnel_ways'] += bool(tunnel)
                counts['motor_bridge_ways'] += bool(bridge) and cls in MOTOR
                counts['motor_tunnel_ways'] += bool(tunnel) and cls in MOTOR
                for key in MEASURES:
                    coverage[key + '_present'] += bool(tags.get(key))
                if bridge or tunnel:
                    coverage['structure_layer_missing'] += not bool(tags.get('layer'))
                found = sorted(set(inspect(tags, nodes, first, last)) | inherited.pop(way, set()))
                if found:
                    reasons.update(found)
                    counts['ways_to_review'] += 1
                    counts['motor_ways_to_review'] += cls in MOTOR
                    # Avoid spreadsheet formula interpretation of untrusted OSM names.
                    safe_name = ("'" + name) if name and name[0] in '=+-@\t\r' else name
                    writer.writerow([way, f'https://www.openstreetmap.org/way/{way}', cls, safe_name, ';'.join(found), raw])
                if counts['highway_ways'] % 10000 == 0 and time.monotonic()-last_progress >= 10:
                    progress('read_all_ways')
                    last_progress = time.monotonic()
        report['eof'] = True
        if inherited:
            raise ValueError('Reference diagnostics point to absent roads')
        for key in ('highway_ways', 'motor_road_ways', 'bridge_ways', 'tunnel_ways', 'motor_bridge_ways', 'motor_tunnel_ways'):
            if counts[key] != manifest['counts'][key]:
                raise ValueError('Count mismatch: ' + key)
        progress('hash_input')
        with source.open('rb') as f:
            report['index_sha256'] = hashlib.file_digest(f, 'sha256').hexdigest()
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Input changed during audit')
        report['state'] = 'COMPLETE'
        progress('ready')
        save_json(partial / 'rapport.json', report)
        rows = '\n'.join(f'| {REASONS.get(k, k)} | {v:,} |' for k,v in reasons.most_common())
        md = f'''# Controle des donnees routieres France

Etat : TERMINE. {counts['highway_ways']:,} / {report['expected_ways']:,} troncons lus jusqu'a la fin.
Extrait OSM : {manifest.get('replication_timestamp')}. France metropolitaine et Corse ; outre-mer absent.
Integrite SQLite et compteurs verifies. La base source n'a pas ete modifiee.

{counts['motor_road_ways']:,} troncons de routes motorisees, {counts['bridge_ways']:,} troncons de ponts,
{counts['tunnel_ways']:,} troncons de tunnels (ce ne sont pas des ouvrages uniques).

{counts['ways_to_review']:,} troncons a examiner, dont {counts['motor_ways_to_review']:,} motorises.
Une alerte peut decrire une situation reelle correcte ; aucune correction automatique des donnees OSM.
Les details et liens OSM sont dans [points-a-examiner.csv](points-a-examiner.csv).

| Motif de controle | Occurrences |
| --- | ---: |
{rows}

## Limites

Ce controle ne certifie pas la praticabilite dans BeamNG. Les altitudes, collisions, batiments,
eau et raccords du terrain genere ne figurent pas dans cet index. Les tags manquants ne sont
pas consideres comme des erreurs. Les routes sans alerte ne sont donc pas certifiees.
Le diagnostic du generateur continue dans les cellules visitees si BNE_ROAD_QA_DIR est configure.

Regles de lecture : [pentes](https://wiki.openstreetmap.org/wiki/Key:incline),
[largeurs](https://wiki.openstreetmap.org/wiki/Key:width),
[niveaux](https://wiki.openstreetmap.org/wiki/Key:layer).
'''
        (partial / 'LIRE-LE-RAPPORT.md').write_text(md, encoding='utf-8')
        os.replace(partial, output)
        print(json.dumps({'state': 'COMPLETE', 'output': str(output), 'counts': counts, 'findings': reasons}), flush=True)
        return report
    except BaseException as exc:
        report.update(state='FAILED', error=f'{type(exc).__name__}: {exc}')
        progress('failed')
        raise
    finally:
        con.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    audit(args.source, args.output)
