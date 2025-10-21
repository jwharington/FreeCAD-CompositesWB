from typing import Optional
import Part
import FreeCAD
import FreeCADGui as Gui

# from https://github.com/gbroques/ose-workbench-core


def find_face_in_selection_object(
    selection_object: "Gui.SelectionObject",
) -> Optional[Part.Face]:
    """Find the first face in the given selection object.
    :param selection_object: A given selection object.
    :type selection_object: Gui.SelectionObject
    :return: The first face found in the selection object.
    :rtype: Optional[Part.Face]
    """
    return _find_sub_object_by_shape_type(selection_object, ShapeType.FACE)


def _find_sub_object_by_shape_type(selection_object, shape_type):
    if selection_object is None:
        return None
    sub_objects = selection_object.SubObjects
    return _find_object_by_type(
        sub_objects,
        "sub objects",
        shape_type,
        lambda sub_object: _is_sub_object_type_of(sub_object, shape_type),
    )


def _find_object_by_type(objects, subject, object_type, filter_predicate):
    potential_objects = list(filter(filter_predicate, objects))
    num_matches = len(potential_objects)
    if num_matches == 0:
        return None
    if num_matches > 1:
        _print_warning_message(num_matches, subject, object_type)
    return potential_objects[0]


class ShapeType:
    """Shape Type Enumeration meant to mirror PartGui::DimSelections::ShapeType
    in FreeCAD C++ code.
    See:
        https://www.freecadweb.org/api/da/d26/classPartGui_1_1DimSelections.html
    """

    VERTEX = "Vertex"
    EDGE = "Edge"
    FACE = "Face"


def _is_sub_object_type_of(sub_object, shape_type):
    return sub_object.ShapeType == shape_type


def _print_warning_message(num_matches, subject, object_type):
    message_template = '{} {} matching type "{}" found in selection.'
    message_template += " Returning first match."
    message = message_template.format(num_matches, subject, object_type)
    FreeCAD.Console.PrintWarning(message)
