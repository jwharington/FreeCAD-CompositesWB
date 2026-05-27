# SPDX-License-Identifier: LGPL-2.1-or-later

import numpy as np


def calc_failure_tsai_wu(
    stress_tensor,
    strain_tensor,
    model_options,
):
    o = model_options
    s = stress_tensor

    F1 = 1 / o["XT"] - 1 / o["XC"]
    F2 = 1 / o["YT"] - 1 / o["YC"]
    F3 = 1 / o["ZT"] - 1 / o["ZC"]
    F11 = 1 / (o["XT"] * o["XC"])
    F22 = 1 / (o["YT"] * o["YC"])
    F33 = 1 / (o["ZT"] * o["ZC"])
    F44 = 1 / o["S23"] ** 2
    F55 = 1 / o["S13"] ** 2
    F66 = 1 / o["S12"] ** 2
    F23 = o.get("f23", 0.0) * np.sqrt(F22 * F33)
    F13 = o.get("f13", 0.0) * np.sqrt(F11 * F33)
    F12 = o.get("f12", 0.0) * np.sqrt(F11 * F22)

    return (
        F1 * s[0]
        + F2 * s[1]
        + F3 * s[2]
        + F11 * s[0] ** 2
        + F22 * s[1] ** 2
        + F33 * s[2] ** 2
        + F44 * s[3] ** 2
        + F55 * s[4] ** 2
        + F66 * s[5] ** 2
        + 2 * (F23 * s[1] * s[2] + F13 * s[0] * s[2] + F12 * s[0] * s[1])
    )


def calc_failure_hashin(
    stress_tensor,
    strain_tensor,
    model_options,
):
    o = model_options
    s = stress_tensor

    # fibre failure
    if s[0] > 0:
        f_ff = (s[0] / o["XT"]) ** 2 + (s[3] ** 2 + s[4] ** 2) / o["S12"] ** 2
    else:
        f_ff = -s[0] / o["XC"]

    # interlaminar failure
    f_ilf = (s[5] ** 2 - s[1] * s[2]) / o["S23"] ** 2
    f_ilf += (s[3] ** 2 + s[4] ** 2) / o["S12"] ** 2

    sc = s[1] + s[2]
    if sc >= 0:
        f_ilf += sc**2 / o["YT"] ** 2
    else:
        f_ilf += sc**2 / (4 * o["S23"] ** 2)
        f_ilf += (o["YC"] ** 2 / (4 * o["S23"] ** 2) - 1) * sc / o["YC"]

    return np.max([f_ff, f_ilf])


def register_composite_failure_models():
    try:
        from femresult.failuremodels import register_failure_model
    except Exception:
        return False

    register_failure_model(
        "tsai_wu",
        calc_failure_tsai_wu,
        metadata={"provider": "CompositesWB", "category": "composite"},
    )
    register_failure_model(
        "hashin",
        calc_failure_hashin,
        metadata={"provider": "CompositesWB", "category": "composite"},
    )
    # Namespaced aliases for explicit selection.
    register_failure_model(
        "composites.tsai_wu",
        calc_failure_tsai_wu,
        metadata={"provider": "CompositesWB", "category": "composite"},
    )
    register_failure_model(
        "composites.hashin",
        calc_failure_hashin,
        metadata={"provider": "CompositesWB", "category": "composite"},
    )
    return True
