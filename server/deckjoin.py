"""Remove duplicate coplanar bridge faces, retaining their UVs and winding.

Ownership is stable by feature ID, independent of which tile is built first.
Different mapped levels and decks more than 1 m apart remain independent.
"""
import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union


def owner(chunk):
    if chunk.get("fixed") and not chunk.get("tunnel") and chunk.get("fid") is not None and chunk.get("level") is not None:
        return str(chunk["fid"]), chunk["level"]
    return None


def masks(pairs, context=(), extra=0.):
    groups = {}
    for (left, right, _v, _m, _layer, z), c in list(pairs) + list(context):
        if not c.get("deck") or owner(c) is None or z is None:
            continue
        key = owner(c)
        mid = (left+right)/2
        d = left-right
        d /= np.maximum(np.linalg.norm(d,axis=1),1e-9)[:,None]
        left, right = left+d*extra, right-d*extra
        group = groups.setdefault(key, [])
        for i in range(len(z)-1):
            poly = Polygon([left[i],right[i],right[i+1],left[i+1]]).buffer(0)
            if not poly.is_empty and poly.area>1e-8:
                group.append((poly,mid[i],mid[i+1],z[i],z[i+1]))
    result = {}
    for key, parts in groups.items():
        cut = []
        own = unary_union([p[0] for p in parts])
        for other, pieces in groups.items():
            if other >= key or other[1] != key[1]:
                continue
            for poly,a,b,za,zb in pieces:
                overlap = own.intersection(poly)
                if overlap.is_empty or overlap.area<1e-8:
                    continue
                q=np.array(overlap.representative_point().coords[0])
                def height(aa,bb,z0,z1):
                    dd=bb-aa
                    t=np.clip((q-aa)@dd/max(float(dd@dd),1e-12),0,1)
                    return z0+t*(z1-z0), float(np.linalg.norm(q-aa-t*dd))
                oz=height(a,b,za,zb)[0]
                zz=min((height(aa,bb,z0,z1) for _,aa,bb,z0,z1 in parts),key=lambda x:x[1])[0]
                if abs(oz-zz)<1.0:
                    cut.append(poly)
        if cut:
            result[key]=unary_union(cut)
    return result


def clip(P, T, UV, owners, cuts, origin=(0.,0.,0.)):
    """Return P,T,UV,source-triangle indices after subtracting owned overlaps."""
    if not cuts:
        return P,T,UV,np.arange(len(T))
    out_p,out_t,out_uv,source=[],[],[],[]
    offset=np.asarray(origin)[:2]
    n=0
    for i,tri in enumerate(T):
        p=P[tri];uv=UV[tri]
        cut=cuts.get(owners[i]) if i<len(owners) else None
        xy=p[:,:2]+offset
        if cut is None:
            vertices=[p];tex=[uv]
        else:
            poly=Polygon(xy)
            if poly.area<1e-8 or not poly.intersects(cut):
                vertices=[p];tex=[uv]
            else:
                remaining=poly.difference(cut)
                if remaining.is_empty:
                    continue
                vertices=[];tex=[]
                inv=np.linalg.inv(np.vstack([xy.T,np.ones(3)]))
                for face in shapely.get_parts(shapely.constrained_delaunay_triangles(remaining)):
                    q=np.asarray(face.exterior.coords)[:3,:2]
                    w=(inv@np.c_[q,np.ones(3)].T).T
                    pp=w@p
                    if np.cross(pp[1]-pp[0],pp[2]-pp[0])[2]*np.cross(p[1]-p[0],p[2]-p[0])[2]<0:
                        w=w[::-1];pp=pp[::-1]
                    vertices.append(pp);tex.append(w@uv)
        for pp,tt in zip(vertices,tex):
            out_p.append(pp);out_uv.append(tt);out_t.append((n,n+1,n+2));source.append(i);n+=3
    return (np.asarray(out_p).reshape(-1,3),np.asarray(out_t,dtype=np.int64).reshape(-1,3),
            np.asarray(out_uv).reshape(-1,2),np.asarray(source,dtype=np.int64))
