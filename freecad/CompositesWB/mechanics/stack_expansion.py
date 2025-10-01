from typing import List
from .stack_model_type import StackModelType
from .stack_model import merge_clt
from ..objects.lamina import Lamina
from ..util.geometry_util import format_layer


def merge_layers(
    prefix: str,
    layers: List[Lamina],
    exclude_core: bool,
) -> List[Lamina]:
    if len(layers) == 1:
        return layers

    has_core = sum([lay.core for lay in layers])

    if exclude_core and has_core:
        res = []
        buf = layers.copy()
        k = 0
        while buf:
            try:
                i = [lay.core for lay in buf].index(True)
                res.append(
                    merge_clt(
                        format_layer(prefix, k),
                        buf[0:i],
                    )
                )
                res.append(buf[i])
                if len(buf) > 1 + i:
                    buf = buf[i + 1 :]  # noqa
                else:
                    buf = []
            except Exception:
                res.append(
                    merge_clt(
                        format_layer(prefix, k),
                        buf,
                    )
                )
                buf = []
            k += 1
        return res
    elif has_core:
        return [merge_clt(prefix, layers, sandwich=True)]
    else:
        return [merge_clt(prefix, layers)]


def flatten_nested(
    prefix: str,
    layers: List[Lamina],
    res: List[Lamina],
    merge_depth: int = 0,
    depth: int = 0,
    exclude_core: bool = False,
):
    res_list = []
    k = 0
    for la in layers:
        if type(la) is list:
            res_inner = []
            flatten_nested(
                format_layer(prefix, k),
                la,
                res_inner,
                merge_depth=merge_depth,
                depth=depth + 1,
                exclude_core=exclude_core,
            )
            k += 1
            res_list.extend(res_inner)
        else:
            res_list.append(la)

    if depth == merge_depth:
        res_list = merge_layers(
            prefix,
            res_list,
            exclude_core=exclude_core,
        )
    res.extend(res_list)


def calc_stack_model(
    prefix: str,
    model_type: StackModelType,
    layers: List[Lamina],
) -> List[Lamina]:
    res = []
    if StackModelType.Discrete == model_type:
        # full expansion, no merging
        flatten_nested(prefix, layers, res, -1)
    elif StackModelType.SmearedFabric == model_type:
        flatten_nested(prefix, layers, res, 1)
    elif StackModelType.SmearedCore == model_type:
        flatten_nested(prefix, layers, res, 0, exclude_core=True)
    elif StackModelType.Smeared == model_type:
        flatten_nested(prefix, layers, res, 0, exclude_core=False)
    else:
        raise ValueError(f"Unhandled model_type {model_type}")

    return res
