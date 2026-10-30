import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dem
import france_local
import mapcells
import netfetch
import roadqa
import buildings
import grading
import roads
from test_roads import features, FRAME
from types import SimpleNamespace


class PedestrianBridgeTest(unittest.TestCase):
    def test_footbridge_has_deck_without_becoming_a_driving_road(self):
        f = features([[(0,0),(160,0)],[(0,20),(160,20)]],
                     ['pedestrian','footway'], flags=[(0,'is_bridge')])
        spec = roads.bridge_specs(f)[0]
        self.assertIsNotNone(spec)
        self.assertEqual(spec.width, 4.0)
        self.assertIsNone(roads.bridge_specs(f)[1])
        self.assertIsNone(roads.road_specs(f)[0])
        self.assertEqual(roads.road_specs(f)[1].cls, "footway")
        import navgraph
        self.assertNotIn(spec.cls, navgraph.DRIVE)
        self.assertNotIn(roads.road_specs(f)[1].cls, navgraph.DRIVE)
        chunks = roads.build_tile(FRAME, 0, 0, [f], lambda la,lo: np.full(np.asarray(la).shape,100.))
        self.assertTrue(any(c.get('deck') for c in chunks))


class IgnTest(unittest.TestCase):
    def test_raw_elevation_request_and_coverage(self):
        k = mapcells.cell_of(45.24,4.67)
        self.assertTrue(dem.ign_covers((k.z,k.x,k.y)))
        self.assertFalse(dem.ign_covers((14,2621,6332)))
        q = parse_qs(urlparse(dem.source_url(dem.IGN,k.z,k.x,k.y)).query)
        self.assertEqual(q['CRS'],['EPSG:3857'])
        self.assertEqual(q['FORMAT'],['image/x-bil;bits=32'])
        box = list(map(float,q['BBOX'][0].split(',')))
        self.assertGreater(box[2],box[0]); self.assertGreater(box[3],box[1])

    def test_partial_coverage_falls_back_per_pixel_and_is_not_mirrored(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,BNE_DEM_SOURCE='ign'):
            obj = dem.Dem(d)
            self.addCleanup(obj.pool.shutdown); self.addCleanup(obj.probe_pool.shutdown); self.addCleanup(obj.urgent_pool.shutdown)
            key = (16,33618,23514)
            a = np.full((512,512),350.,dtype='<f4'); a[0,0]=-99999
            with patch.object(obj,'_download',return_value=a.tobytes()), patch.object(obj,'_make_global_tile',return_value=np.full((512,512),20.,np.float32)), patch.object(obj,'_mirror_put') as mirror:
                out = obj._load_tile(key)
            self.assertEqual(out[0,0],20.); self.assertEqual(out[1,1],350.)
            mirror.assert_not_called()
            self.assertIn('ign',obj._mirror_path(key))

    def test_unavailable_ign_keeps_global_fallback(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,BNE_DEM_SOURCE='ign'):
            obj=dem.Dem(d)
            self.addCleanup(obj.pool.shutdown); self.addCleanup(obj.probe_pool.shutdown); self.addCleanup(obj.urgent_pool.shutdown)
            with patch.object(obj,'_download',side_effect=netfetch.HostUnavailable('offline')), patch.object(obj,'_make_global_tile',return_value=np.zeros((512,512),np.float32)) as fallback:
                obj._make_tile((16,33618,23514))
                fallback.assert_called_once()
            with self.assertRaises(ValueError): dem.decode_ign(b'XML error response')


class LocalIndexTest(unittest.TestCase):
    def test_partial_database_is_rejected_and_ready_names_keep_accents(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'index.sqlite'
            con=sqlite3.connect(p)
            con.executescript('CREATE TABLE meta(key TEXT,value TEXT); CREATE TABLE places(id INTEGER PRIMARY KEY,kind TEXT,name TEXT,lat REAL,lon REAL); CREATE VIRTUAL TABLE place_bbox USING rtree(id,min_lon,max_lon,min_lat,max_lat); CREATE TABLE roads(id INTEGER PRIMARY KEY,tags TEXT);')
            con.execute('INSERT INTO meta VALUES (?,?)',('manifest',json.dumps({'state':'RUNNING','schema':1})))
            con.commit()
            with self.assertRaises(ValueError): france_local.Index(p)
            con.execute('UPDATE meta SET value=?',(json.dumps({'state':'COMPLETE','eof':True,'schema':1}),))
            con.execute('INSERT INTO places VALUES (1,?,?,?,?)',('hamlet','Les Étroits',45.24,4.67))
            con.execute('INSERT INTO place_bbox VALUES (1,4.67,4.67,45.24,45.24)')
            con.execute('INSERT INTO roads VALUES (12,?)',(json.dumps({'destination':'Annonay'}),))
            con.commit(); con.close()
            index=france_local.Index(p)
            self.assertEqual(index.nearby(45.24,4.67)['name'],'Les Étroits')
            self.assertIsNone(index.nearby(45.30,4.67))
            self.assertIsNone(index.nearby(float('nan'),4.67))
            self.assertEqual(index.road_tags([12,999])[12]['destination'],'Annonay')


class ProfileReviewTest(unittest.TestCase):
    def test_inferred_underpass_cannot_flood_dry_ground(self):
        self.assertEqual(grading.underpass_target(3.5,2.5),3.5)
        self.assertEqual(grading.underpass_target(.1,2.5),.1)
        self.assertLess(grading.underpass_target(40.,42.),40.)
        self.assertLess(grading.underpass_target(-2.,2.),-2.)

    def test_precomputed_clearance_is_not_subtracted_twice(self):
        self.assertEqual(grading.underpass_target(40.,38.,clearance=0.),38.)
        self.assertEqual(grading.underpass_target(3.5,-1.,clearance=0.),3.5)

    def test_real_constant_slope_is_preserved_and_a_step_is_detected(self):
        x=np.arange(0.,100.,2.); xy=np.c_[x,np.zeros(len(x))]
        z=.18*x
        self.assertEqual(roadqa.measure(xy,z)['flags'],[])
        np.testing.assert_array_equal(z,.18*x)
        broken=z.copy(); broken[len(z)//2:]+=2
        self.assertIn('abrupt_grade_change_review',roadqa.measure(xy,broken)['flags'])
        self.assertIn('height_step_at_same_xy',roadqa.measure([[0,0],[0,0],[2,0]],[1,2,2])['flags'])


class CrossingAndPortalTest(unittest.TestCase):
    def test_rail_mesh_stays_above_road_tunnel(self):
        import railways
        f=features([[(-150.,0.),(400.,0.)],[(0.,-40.),(0.,40.)]],
                   ['standard_gauge','secondary'],subtypes=['rail','road'],flags=[(1,'is_tunnel')])
        x=np.arange(-150.,400.1,2.)
        # A bare-earth DEM sees the lower road at this crossing. Smoothing the
        # dip alone leaves both the railway and its ballast inside the bore.
        level=lambda xx:100.+.002*xx-6.*np.exp(-(xx/11.)**2)
        p=grading.Plan(np.c_[x,np.zeros(len(x))],level(x),railways.GRADE_HALF_M)
        g=grading.Grader(FRAME,None,lambda a,b:np.full(np.shape(a),100.))
        key=mapcells.cell_of(FRAME.lat0,FRAME.lon0)
        g.cells[key]=[(grading.RAIL_TAG+'upper-track',p)]
        g.covers[key]=[(np.array([[0.,-40.],[0.,40.]]),3.5+grading.TUNNEL_KEEP_M)]
        def ground(xy):
            return g._surface_over_tunnels(xy[:,0],xy[:,1],level(xy[:,0]),0.,[key])
        P,T,_,mats,M=railways.tile_mesh(FRAME,0,0,[f],ground)
        # Include the ballast sides, not just the rails: they used to block a
        # pickup in Saint-Vallier while the road's own floor was continuous.
        inside=P[(np.abs(P[:,0])<4.) & (np.abs(P[:,1])<4.)]
        self.assertGreater(len(inside),0,'the railway remains present over the bore')
        self.assertGreater(float(inside[:,2].min()),97.,'no rail or ballast in the road clearance')
        self.assertTrue((M==mats.index(railways.STEEL)).any())
        np.testing.assert_allclose(ground(np.array([[100.,0.],[0.,38.]])),level(np.array([100.,0.])))

    def test_upper_carriageway_restored_without_raising_lower_portal(self):
        f=features([[(-150,0),(150,0)],[(0,-30),(0,30)]],['motorway','residential'],flags=[(1,'is_tunnel')])
        md=SimpleNamespace(cell=lambda *a,**kw:SimpleNamespace(layers={'roads':f}))
        g=grading.Grader(FRAME,md,lambda a,b:np.full(np.shape(a),100.))
        x=np.arange(-150.,150.1,2.);xy=np.c_[x,np.zeros(len(x))]
        z=100.+.02*x-3.*np.exp(-(x/12.)**2)
        plan=grading.Plan(xy,z,5.)
        key=mapcells.cell_of(FRAME.lat0,FRAME.lon0)
        g.cells[key]=[('upper',plan)]  # as after a shared/revisit plan-cache read
        g.covers[key]=[(np.array([[0.,-30.],[0.,30.]]),3.+grading.TUNNEL_KEEP_M)]
        g.md=None  # no map download is allowed after a complete cache read
        e=np.array([-20.,0.,20.,0.]);n=np.array([0.,0.,0.,28.]);base=np.array([97.,94.,97.,80.])
        out=g._surface_over_tunnels(e,n,base,0.,[key])
        np.testing.assert_allclose(out[:3],100.+.02*e[:3],atol=.02)
        self.assertEqual(out[-1],80.,'the lower approach stays at its own height')
        self.assertIn(key,g.crossovers)

    def test_cliff_sample_repaired_only_on_connected_approach(self):
        f=features([[(0,0),(300,0)],[(-24,0),(0,0)],[(-24,80),(0,80)]],['secondary']*3,flags=[(0,'is_tunnel')])
        def elev(la,lo):
            e,_,_=FRAME.geodetic_to_enu(la,lo,0.)
            return 100.+20.*np.exp(-(e/3.)**2)
        specs=roads.road_specs(f)
        plans=[(str(f.ids[i]),grading.plan_road(FRAME,roads.ground_parts(f,i)[0],specs[i],elev)) for i in (1,2)]
        before=plans[1][1].z.copy()
        grading.Grader(FRAME,None,elev)._repair_tunnel_portals(f,plans)
        self.assertLess(np.max(np.abs(plans[0][1].z-100)),.15)
        np.testing.assert_array_equal(plans[1][1].z,before)

    def test_verified_bore_has_no_fake_open_section(self):
        s=np.arange(0.,309.,4.);z=128.+s*.024+np.where((s>140)&(s<300),30.,2.)
        z[[0,-1]]=[128.,135.4]
        floor,kinds=roads.tunnel_sections(s,z,continuous=True)
        np.testing.assert_allclose(floor,np.linspace(128.,135.4,len(s)))
        self.assertTrue((kinds==2).all())
        self.assertTrue((roads.tunnel_sections(s,z)[1]==0).any())

    def test_short_approach_uses_connected_road_without_a_step(self):
        f=features([[(0,0),(30,0)],[(-14,0),(0,0)],[(-80,0),(-14,0)]],
                   ['secondary']*3,flags=[(0,'is_tunnel')])
        def elev(la,lo):
            e,_,_=FRAME.geodetic_to_enu(la,lo,0.)
            return 100.+8.*np.exp(-(e/9.)**2)
        specs=roads.road_specs(f)
        plans=[(str(f.ids[i]),grading.plan_road(FRAME,roads.ground_parts(f,i)[0],specs[i],elev)) for i in (1,2)]
        grading.Grader(FRAME,None,elev)._repair_tunnel_portals(f,plans)
        self.assertLess(abs(plans[0][1].z[-1]-100.),.15)
        self.assertLess(abs(plans[0][1].z[0]-plans[1][1].z[-1]),.15)

    def test_true_steep_approach_is_not_flattened(self):
        f=features([[(0,0),(30,0)],[(-80,0),(0,0)]],['secondary']*2,flags=[(0,'is_tunnel')])
        def elev(la,lo):
            e,_,_=FRAME.geodetic_to_enu(la,lo,0.)
            return 100.+.18*e
        p=grading.plan_road(FRAME,roads.ground_parts(f,1)[0],roads.road_specs(f)[1],elev)
        before=p.z.copy()
        grading.Grader(FRAME,None,elev)._repair_tunnel_portals(f,[(str(f.ids[1]),p)])
        np.testing.assert_array_equal(p.z,before)

    def test_terrain_quad_across_a_portal_does_not_block_it(self):
        axis=np.arange(-32.,32.,2.);x,y=np.meshgrid(axis,axis);z=np.where(x<0,0.,30.)
        part=('full',roads.Spec(7.,'paved',False,'secondary',False),np.array([[-20.,0.],[20.,0.]]),np.array([10.,10.]),0.)
        mask=roads.tunnel_hole_mask([part],z,0,0,2.)
        self.assertTrue(mask[16,15])
        self.assertFalse(mask[:,20:].any())


class TunnelEntranceOverlapTest(unittest.TestCase):
    def test_floor_covers_grid_hole_before_portal_without_moving_the_tube(self):
        import roadmesh
        part=('bore',roads.Spec(7.,'paved',False,'secondary',False),
              np.array([[0.,0.],[40.,0.]]),np.array([10.,10.]),0.)
        tunnels=SimpleNamespace(_ground=lambda xy:np.full(len(xy),9.96),
                                mouth=lambda fid:(True,False))
        chunks=roads._tunnel_apron_chunks(tunnels,[part],(-20.,-20.,60.,20.))
        self.assertEqual(len(chunks),1,'only the real mouth gets an overlap')
        c=chunks[0]
        self.assertTrue(c['deck'] and c['no_tube'] and c['fixed'])
        self.assertFalse(any(c['portal']))
        self.assertIsNone(roadmesh.tunnel(chunks,(0.,0.,0.)), 'no extra portal or tube')
        # Wheel track 0.75 m before the mouth, where the terrain quad was removed.
        left,right,_,_,_,z=roadmesh.ribbons(chunks)[0]
        self.assertLess(min(left[:,0].min(),right[:,0].min()),-.75)
        self.assertGreaterEqual(max(left[:,0].max(),right[:,0].max()),0.)
        self.assertLess(min(left[:,1].min(),right[:,1].min()),-2.45)
        self.assertGreater(max(left[:,1].max(),right[:,1].max()),2.45)
        self.assertAlmostEqual(float(z[0]),9.96)
        self.assertAlmostEqual(float(z[-1]),10.)

    def test_overlap_is_clipped_at_tile_seam(self):
        part=('bore',roads.Spec(7.,'paved',False,'secondary',False),
              np.array([[1.,0.],[40.,0.]]),np.array([10.,10.]),0.)
        t=SimpleNamespace(_ground=lambda xy:np.full(len(xy),10.),mouth=lambda fid:(True,False))
        left=roads._tunnel_apron_chunks(t,[part],(-10.,-10.,0.,10.))
        right=roads._tunnel_apron_chunks(t,[part],(0.,-10.,10.,10.))
        self.assertTrue(left and right)
        np.testing.assert_allclose(left[0]['n'][-1][:2],right[0]['n'][0][:2],atol=1e-6)
        self.assertAlmostEqual(left[0]['n'][-1][2],right[0]['n'][0][2])


class BuildingOutlineTest(unittest.TestCase):
    def test_skewed_wall_does_not_expand_into_street(self):
        ring=np.array([[0.,0.],[30.,0.],[29.,9.],[0.,6.]])
        self.assertFalse(buildings.box_walls_fit(ring))
        spec=buildings.plan(ring,{'class':'house','roof_shape':'gabled'},lat=45.24,lon=4.66)
        np.testing.assert_array_equal(buildings.drawn_ring(spec),ring)
        rectangle=np.array([[0.,0.],[30.,0.],[30.,9.],[0.,9.]])
        self.assertTrue(buildings.box_walls_fit(rectangle))


if __name__=='__main__': unittest.main()
