from Part import Vertex
from FreeCAD import Vector
import Mesh
import MeshPart
from collections import namedtuple


def mesh_point_is_close(point, shape, tol=1.0e-3):
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

    # find points in mesh on dart

    def is_point_on_edges(point, edges):
        for e in edges:
            if is_point_on_edge(point, e):
                return True
        return False

    dart_point_indices = frozenset(
        [i for i, p in enumerate(mesh.Points) if is_point_on_edges(p, edges)]
    )

    # find facets in mesh on dart
    DartPoly = namedtuple("DartPoly", ["poly_idx", "key_edges", "dart_points"])

    def points_on_dart(poly):
        return frozenset(set(poly) & dart_point_indices)

    edge_polys = []
    for poly_idx, poly in enumerate(mesh.Topology[1]):
        list_poly = list(poly)
        n_facet_points = len(list_poly)
        dart_points = points_on_dart(list_poly)
        if not dart_points:
            continue

        # edges in facet touching dart
        def get_key_edges():
            key_edges = []
            for j in range(n_facet_points):
                p_this = list_poly[j]
                p_next = list_poly[(j + 1) % n_facet_points]
                this_edge_points = frozenset([p_this, p_next])
                if this_edge_points == dart_points:
                    # don't need these
                    continue
                if this_edge_points & dart_points:
                    key_edges.append(this_edge_points)
            return set(key_edges)

        edge_polys.append(DartPoly(poly_idx, get_key_edges(), dart_points))

    # sort and cluster
    end_polys = edge_polys.copy()

    chain = []

    def new_cluster():
        chain.append([edge_polys.pop(0)])
        return chain[-1]

    cluster = new_cluster()
    while edge_polys:

        def match(ref: DartPoly, ref_idx):
            ex = cluster[ref_idx]
            common_edges = ref.key_edges & ex.key_edges
            if not common_edges:
                return False

            def removed_edge(p):
                return p._replace(key_edges=p.key_edges - common_edges)

            # update items to remove the linking edge
            cluster[ref_idx] = removed_edge(ex)
            ref = removed_edge(ref)

            # insert in cluster
            if ref_idx == -1:
                cluster.append(ref)
            else:
                cluster.insert(0, ref)
            return True

        def edge_present_in_group(ref):
            if len(ref.dart_points) < 2:
                return False
            for ex in cluster:
                if len(ref.dart_points & ex.dart_points) >= 2:
                    return True
            return False

        def scan_link():
            for i, ref in enumerate(edge_polys):

                if edge_present_in_group(ref):
                    return False

                if match(ref, 0) or match(ref, -1):
                    edge_polys.pop(i)
                    return True
            return False

        if not scan_link():
            # if poly couldn't be linked to existing cluster,
            # for example because already present in group
            # it must need a new cluster
            cluster = new_cluster()

    # split clusters

    def border_edge(poly: DartPoly, idx):
        # detect wheter a poly is a border edge at idx
        free_edges = poly.key_edges
        for other in end_polys:
            if idx not in other.dart_points:
                continue
            if other.poly_idx == poly.poly_idx:
                continue
            free_edges -= free_edges & other.key_edges
        return len(free_edges)

    # map of point indices to which cluster they are used in
    analysis_points = {k: [] for k in dart_point_indices}

    for cluster_idx, cluster in enumerate(chain):
        ref_last = None
        # find last 2-poly on dart
        for ref in cluster:
            if len(ref.dart_points) < 2:
                continue
            ref_last = cluster[-1]

        # multilinks always cut  ab,bc -> a-(b)-c

        for ref in cluster:
            if len(ref.dart_points) < 2:
                continue
            if not ref_last:
                ref_last = ref
                continue
            common = ref.dart_points & ref_last.dart_points
            if len(common) == 1:
                analysis_points[list(common)[0]].append(cluster_idx)
            ref_last = ref

        # address remaining end points in this cluster
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


def make_dart(shape, edges, max_length=4.0):
    # - convert shape to mesh
    mesh = MeshPart.meshFromShape(Shape=shape, MaxLength=max_length)

    # - analyse mesh
    analysis_points, chain = split_mesh_at_edge(mesh, edges)

    # - make lookup from poly index to which group it belongs to
    #  (this should be unique)
    poly_cluster = {}
    for cluster_idx, cluster in enumerate(chain):
        for ref in cluster:
            poly_cluster[ref.poly_idx] = cluster_idx

    # - generate new mesh
    mesh2 = Mesh.Mesh()
    for poly_idx, poly in enumerate(mesh.Topology[1]):

        if poly_idx not in poly_cluster:
            cluster_idx = -1
        else:
            cluster_idx = poly_cluster[poly_idx]

        def point_index_to_vector(i):
            p = mesh.Points[i]
            v = Vector(p.x, p.y, p.z)
            if (
                (cluster_idx > 0)
                and (i in analysis_points)
                and (cluster_idx in analysis_points[i])
            ):
                return v + Vector(0, 0, cluster_idx)
            return v

        vecs = [point_index_to_vector(i) for i in list(poly)]
        mesh2.addFacet(*vecs)

    return mesh2
