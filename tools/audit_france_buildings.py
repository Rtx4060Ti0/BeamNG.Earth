"""Check mapped and generated walls against Rue Melchior-de-Vogue's centreline.

Uses cached source buildings/roads and the real building planner. This checks wall
footprints, not every decorative mesh or an in-game collision ray.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
import buildings
import geodesy
import mapcells
from audit_france_profiles import CachedMap


def audit(output):
    frame=geodesy.EnuFrame(45.2411,4.6673,0.)
    md=CachedMap(Path.home()/'.cache/beamng-earth')
    cells=[md.cell(k,('roads','buildings')).layers for k in mapcells.cells_for_bbox(45.237,4.661,45.246,4.675)]
    lines=[]; seen=set()
    for cell in cells:
        f=cell['roads']
        if f is None: continue
        for i in range(len(f)):
            if 'melchior' not in str(f.attrs.get('name',['']*len(f))[i]).lower() or str(f.ids[i]) in seen: continue
            seen.add(str(f.ids[i]))
            for part in f.parts(i):
                ll=part[0];e,n,_=frame.geodetic_to_enu(ll[:,1],ll[:,0],0.)
                lines.append(LineString(np.c_[e,n]))
    road=unary_union(lines)
    if road.is_empty: raise ValueError('No cached Melchior road')
    x0=y0=-400.;x1=y1=400.
    result=buildings.tile_buildings(frame,x0,y0,x1,y1,[c['buildings'] for c in cells],lambda a,b:np.full(np.shape(a),350.))
    entries=[]
    for spec,gmin,gmax in result:
        ring=spec.ring+[x0,y0];drawn=buildings.drawn_ring(spec)+[x0,y0]
        raw,solid=Polygon(ring),Polygon(drawn)
        if not raw.is_valid: raw=raw.buffer(0)
        if not solid.is_valid: solid=solid.buffer(0)
        if min(raw.distance(road),solid.distance(road)) > 6: continue
        centre=np.mean(ring,axis=0);lat,lon,_=frame.enu_to_geodetic(*centre,0.)
        entries.append(dict(lat=float(lat),lon=float(lon),roof=spec.roof,
             mapped_distance_m=float(raw.distance(road)),generated_distance_m=float(solid.distance(road)),
             mapped_centreline_m=float(raw.intersection(road).length),generated_centreline_m=float(solid.intersection(road).length),
             added_footprint_m2=float(solid.difference(raw).area),ring=ring.tolist(),drawn=drawn.tolist()))
    report={'scope':'Mapped/generated wall outlines against street centreline, not a drive test',
        'road_features':len(seen),'buildings_near_street':len(entries),'missing_cache':sorted(md.missing),
        'generated_centreline_intrusions':sum(r['generated_centreline_m']>.05 for r in entries),
        'mapped_centreline_intrusions':sum(r['mapped_centreline_m']>.05 for r in entries),
        'road_lines':[list(line.coords) for line in lines], 'buildings':entries}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('road_lines','buildings')}))
    for r in entries:
        if r['generated_centreline_m']>.05: print(json.dumps({k:v for k,v in r.items() if k not in ('ring','drawn')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.output)
