#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
spec_to_model(): dispatch from spec["type"] to the right model class.

This module contains the factory that creates model instances from spec dicts
(JSON-compatible plain dicts).  It is the ONLY place that maps spec type
strings to model classes for spec-based construction.

xml_compat.py is the only module that imports lxml / xmltodict.
"""
from typing import Any, Dict


def spec_to_model(spec: Dict[str, Any]):
    """Create a WaNo model instance from a spec dict.

    The returned model has its common fields (name, visibility_condition, …)
    and all type-specific fields applied.  It is completely independent of any
    XML tree.

    Parameters
    ----------
    spec:
        A JSON-compatible dict as produced by ``xml_compat.element_to_spec``
        or by a model's own ``to_spec()`` method.

    Returns
    -------
    AbstractWanoModel
        A fully initialised model instance.
    """
    # Late imports to avoid circular dependencies at module load time.
    from SimStackServer.WaNo.WaNoModels import (
        WaNoItemFloatModel,
        WaNoItemIntModel,
        WaNoItemStringModel,
        WaNoItemBoolModel,
        WaNoItemFileModel,
        WaNoChoiceModel,
        WaNoDynamicChoiceModel,
        WaNoMatrixModel,
        WaNoModelDictLike,
        MultipleOfModel,
        WaNoSwitchModel,
        WaNoNoneModel,
        WaNoThreeRandomLetters,
    )

    _SPEC_TYPE_TO_CLASS: Dict[str, type] = {
        "float": WaNoItemFloatModel,
        "int": WaNoItemIntModel,
        "string": WaNoItemStringModel,
        "bool": WaNoItemBoolModel,
        "file": WaNoItemFileModel,
        "choice": WaNoChoiceModel,
        "dynamic_choice": WaNoDynamicChoiceModel,
        "matrix": WaNoMatrixModel,
        "dict": WaNoModelDictLike,
        "multipleof": MultipleOfModel,
        "switch": WaNoSwitchModel,
        "none": WaNoNoneModel,
        "three_random": WaNoThreeRandomLetters,
    }

    spec_type = spec["type"]
    ModelClass = _SPEC_TYPE_TO_CLASS[spec_type]
    model = ModelClass.from_spec(spec)

    xml_tag = spec.get("xml_tag")
    if xml_tag is not None:
        import SimStackServer.WaNo.WaNoFactory as _factory
        view_cls = _factory.WaNoFactory.get_qt_view_class(xml_tag)
        if view_cls is not None:
            model.set_view_class(view_cls)

    return model
