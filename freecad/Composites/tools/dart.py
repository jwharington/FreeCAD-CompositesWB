from Part import Vertex
from FreeCAD import Vector
import Mesh
import MeshPart
from collections import namedtuple


DartPoly = namedtuple("DartPoly", ["poly_idx", "key_edges", "dart_points"])


def is_point_on_edges(
    point,
    edges,
):
    def mesh_point_is_close(shape, tol=1.0e-3):
        return Vertex(point.x, point.y, point.z).distToShape(shape)[0] < tol

    for e in edges:
        if mesh_point_is_close(e):
            return True
    return False


def get_dart_polys(
    mesh,
    dart_point_indices,
):
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
    return edge_polys


def get_dart_clusters(
    edge_polys,
):
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

    return chain


def get_split_clusters(
    end_polys,
    dart_point_indices,
    chain,
):

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

        # multilinks always cut  ab,bc -> a-(b)-c
        def mark_intermediate_dart():

            def get_last_2poly_on_dart():
                ref_last = None
                # find last 2-poly on dart
                for ref in cluster:
                    if len(ref.dart_points) < 2:
                        continue
                    ref_last = cluster[-1]
                return ref_last

            ref_last = get_last_2poly_on_dart()
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

        mark_intermediate_dart()

        # address remaining end points in this cluster
        def mark_dart_ends():

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

            for ref in cluster:
                for idx in ref.dart_points:
                    check_point(idx)

        mark_dart_ends()

    return analysis_points


def get_poly_cluster(
    chain,
):
    poly_cluster = {}
    for cluster_idx, cluster in enumerate(chain):
        for ref in cluster:
            poly_cluster[ref.poly_idx] = cluster_idx
    return poly_cluster


def get_delta(
    mesh,
    chain,
):
    delta = {}
    n_delta = {}

    for cluster_idx, cluster in enumerate(chain):
        for ref in cluster:
            for p in ref.dart_points:
                k = (p, cluster_idx)
                delta[k] = Vector()
                n_delta[k] = 0

    for cluster_idx, cluster in enumerate(chain):
        for ref in cluster:

            def point_index_to_vector(i):
                p = mesh.Points[i]
                return Vector(p.x, p.y, p.z)

            pl = list(mesh.Topology[1][ref.poly_idx])

            barycenter = Vector()
            for i in pl:
                barycenter += point_index_to_vector(i) / len(pl)

            for p in ref.dart_points:
                v = point_index_to_vector(p) - barycenter
                k = (p, cluster_idx)
                delta[k] += v
                n_delta[k] += 1

    for cluster_idx, cluster in enumerate(chain):
        for ref in cluster:
            for p in ref.dart_points:
                k = (p, cluster_idx)
                if n_delta[k]:
                    delta[k] /= n_delta[k]
    return delta


def split_mesh_at_edge(
    mesh,
    edges,
):

    # find points in mesh on dart

    dart_point_indices = frozenset(
        [i for i, p in enumerate(mesh.Points) if is_point_on_edges(p, edges)]
    )

    # find facets in mesh on dart
    edge_polys = get_dart_polys(mesh, dart_point_indices)
    # make copy before modifying
    end_polys = edge_polys.copy()

    # sort and cluster
    chain = get_dart_clusters(edge_polys)

    # split clusters
    analysis_points = get_split_clusters(end_polys, dart_point_indices, chain)

    # - make lookup from poly index to which group it belongs to
    #  (this should be unique)
    poly_cluster = get_poly_cluster(chain)
    delta = get_delta(mesh, chain)

    return analysis_points, poly_cluster, delta


def generate_dart_mesh(
    mesh,
    analysis_points,
    poly_cluster,
    delta,
    gap_length,
):
    mesh_dart = Mesh.Mesh()
    for poly_idx, poly in enumerate(mesh.Topology[1]):

        if poly_idx not in poly_cluster:
            cluster_idx = -1
        else:
            cluster_idx = poly_cluster[poly_idx]

        def point_index_to_vector(i):
            p = mesh.Points[i]
            v = Vector(p.x, p.y, p.z)
            if (
                (cluster_idx >= 0)
                and (i in analysis_points)
                and (cluster_idx in analysis_points[i])
            ):
                return v + delta[(i, cluster_idx)] * gap_length
            return v

        vecs = [point_index_to_vector(i) for i in list(poly)]
        mesh_dart.addFacet(*vecs)

    return mesh_dart


def make_dart(shape, edges, max_length=4.0, gap_length=0.1):
    # - convert shape to mesh
    mesh = MeshPart.meshFromShape(Shape=shape, MaxLength=max_length)

    # - analyse mesh
    analysis_points, poly_cluster, delta = split_mesh_at_edge(mesh, edges)

    # - generate new mesh
    return generate_dart_mesh(
        mesh,
        analysis_points,
        poly_cluster,
        delta,
        gap_length=gap_length,
    )
