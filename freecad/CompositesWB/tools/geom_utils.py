def get_line_intersection(p0_x, p0_y, p1_x, p1_y, p2_x, p2_y, p3_x, p3_y):

    s1_x = p1_x - p0_x
    s1_y = p1_y - p0_y
    s2_x = p3_x - p2_x
    s2_y = p3_y - p2_y

    dt = -s2_x * s1_y + s1_x * s2_y
    if dt == 0:
        raise ValueError("no step")
    t = (s2_x * (p0_y - p2_y) - s2_y * (p0_x - p2_x)) / dt
    if t < 0:
        return None

    ds = -s2_x * s1_y + s1_x * s2_y
    if ds == 0:
        raise ValueError("no step")
    s = (-s1_y * (p0_x - p2_x) + s1_x * (p0_y - p2_y)) / ds

    if (s < 0) or (s > 1):
        return None

    i_x = p0_x + (t * s1_x)
    i_y = p0_y + (t * s1_y)
    return (i_x, i_y)


def find_uv_intersection(uv, uv_last, face):
    bounds = face.ParameterRange

    lines = [
        (bounds[0], bounds[2], bounds[1], bounds[2]),
        (bounds[1], bounds[2], bounds[1], bounds[3]),
        (bounds[1], bounds[3], bounds[0], bounds[3]),
        (bounds[0], bounds[3], bounds[0], bounds[2]),
    ]
    for p2_x, p2_y, p3_x, p3_y in lines:
        res = get_line_intersection(
            uv_last[0], uv_last[1], uv[0], uv[1], p2_x, p2_y, p3_x, p3_y
        )
        if res is not None:
            return res
    raise ValueError("no intersection")
