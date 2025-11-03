from Part import Vertex
from FreeCAD import Vector
import Mesh
import MeshPart
from collections import namedtuple


def mesh_point_is_close(point, shape, tol=1.0e-6):
    return Vertex(point.x, point.y, point.z).distToShape(shape)[0] < tol


def is_point_on_edge(point, edge):
    return mesh_point_is_close(point, edge)


def is_point_on_end(point, edge):
    return mesh_point_is_close(
        point,
        edge.firstVertex(),
    ) or mesh_point_is_close(
        point,
        edge.lastVertex(),
    )


def split_mesh_at_edge(mesh, edges):

    # find points in mesh on edges

    def is_point_on_edges(point, edges):
        for e in edges:
            if is_point_on_edge(point, e):
                return True
        return False

    dart_point_indices = frozenset(
        [i for i, p in enumerate(mesh.Points) if is_point_on_edges(p, edges)]
    )

    def points_on_dart(poly):
        return frozenset(set(poly) & dart_point_indices)

    # find faces in mesh on edges
    DartPoly = namedtuple("DartPoly", ["poly_idx", "key_edges", "dart_points"])

    edge_polys = []
    for poly_idx, poly in enumerate(mesh.Topology[1]):
        list_poly = list(poly)
        n = len(list_poly)
        pd = points_on_dart(list_poly)
        if not pd:
            continue

        def get_key_edges():
            ue = []
            for j in range(n):
                p_this = list_poly[j]
                p_next = list_poly[(j + 1) % n]
                pl = frozenset([p_this, p_next])
                if (pl & pd) and (pl != pd):
                    ue.append(pl)
            return set(ue)

        edge_polys.append(DartPoly(poly_idx, get_key_edges(), pd))

    # sort and cluster
    end_polys = edge_polys.copy()

    chain = []

    def new_cluster():
        chain.append([edge_polys.pop(0)])
        return chain[-1]

    cluster = new_cluster()
    while edge_polys:

        def match(ref: DartPoly, j):
            ex = cluster[j]
            common_edges = ref.key_edges & ex.key_edges
            if not common_edges:
                return False

            cluster[j] = ex._replace(key_edges=ex.key_edges - common_edges)
            ref = ref._replace(key_edges=ref.key_edges - common_edges)
            if j == -1:
                cluster.append(ref)
            else:
                cluster.insert(0, ref)
            return True

        def check_dup(ref):
            if len(ref.dart_points) < 2:
                return False
            for ex in cluster:
                if len(ref.dart_points & ex.dart_points) >= 2:
                    return True
            return False

        def scan_match():
            for i, ref in enumerate(edge_polys):

                if check_dup(ref):
                    return False

                if match(ref, 0) or match(ref, -1):
                    edge_polys.pop(i)
                    return True
            return False

        if not scan_match():
            cluster = new_cluster()

    # split clusters

    def border_edge(poly: DartPoly, idx):
        free_edges = poly.key_edges
        for other in end_polys:
            if idx not in other.dart_points:
                continue
            if other.poly_idx == poly.poly_idx:
                continue
            free_edges -= free_edges & other.key_edges
        return len(free_edges)

    analysis_points = {k: [] for k in dart_point_indices}

    for cluster_idx, cluster in enumerate(chain):
        ref_last = None
        for ref in cluster:
            if len(ref.dart_points) < 2:
                continue
            ref_last = cluster[-1]

        # multilinks always cut  ab,bc -> a-(b)-c

        for ref in cluster:
            if len(ref.dart_points) < 2:
                continue
            if not (ref_last):
                ref_last = ref
                continue
            common = ref.dart_points & ref_last.dart_points
            if len(common) == 1:
                analysis_points[list(common)[0]].append(cluster_idx)
            ref_last = ref

        # address remaining end points
        for ref in cluster:

            def check_point(idx):
                if cluster_idx in analysis_points[idx]:
                    return
                for e_idx, poly in enumerate(end_polys):
                    if idx not in poly.dart_points:
                        continue
                    if border_edge(poly, idx):
                        analysis_points[idx].append(cluster_idx)
                        end_polys.pop(e_idx)
                        return

            for idx in ref.dart_points:
                check_point(idx)

    return analysis_points, chain


def make_dart(shape, edges, max_length=3.0):
    # - convert shape to mesh
    mesh = MeshPart.meshFromShape(Shape=shape, MaxLength=max_length)

    # - analyse mesh
    analysis_points, chain = split_mesh_at_edge(mesh, edges)

    poly_group = {}
    for group_idx, cluster in enumerate(chain):
        for ref in cluster:
            poly_group[ref.poly_idx] = group_idx

    # - generate new mesh
    mesh2 = Mesh.Mesh()
    for poly_idx, poly in enumerate(mesh.Topology[1]):

        if poly_idx not in poly_group:
            group_idx = -1
        else:
            group_idx = poly_group[poly_idx]

        def point_index_to_vector(i):
            p = mesh.Points[i]
            v = Vector(p.x, p.y, p.z)
            if (
                (group_idx > 0)
                and (i in analysis_points)
                and (group_idx in analysis_points[i])
            ):
                return v + Vector(0, 0, group_idx)
            return v

        vs = [point_index_to_vector(i) for i in list(poly)]
        mesh2.addFacet(*vs)

    return mesh2
