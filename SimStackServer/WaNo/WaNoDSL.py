#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Builder DSL for WaNo models.

Provides thin spec-builder classes that compose WaNo model trees using
plain Python without any XML.  Each class produces a JSON-compatible spec
dict via ``to_spec()`` and can be converted to a live model via
``to_model()``.

Example::

    from SimStackServer.WaNo.WaNoDSL import Root, Box, Float, Int, Bool

    wano = Root(
        "MySimulation",
        Box(
            "Settings",
            Float("temperature", value=300.0),
            Int("steps", value=1000),
            Bool("verbose", value=False),
        ),
        exec_command="run_sim.sh",
        output_files=["results.yml"],
    )
    model = wano.to_model()
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "Float",
    "Int",
    "Bool",
    "String",
    "File",
    "Choice",
    "DynamicChoice",
    "Matrix",
    "NoneNode",
    "ThreeRandom",
    "Box",
    "Switch",
    "SwitchOption",
    "MultipleOf",
    "Root",
]


# ---------------------------------------------------------------------------
# Base node
# ---------------------------------------------------------------------------


class _Node:
    """Base class for all spec-builder nodes."""

    def __init__(
        self,
        name: str,
        *,
        description: str = "",
        visibility_condition: Optional[str] = None,
        visibility_var_path: str = "",
        import_from: Optional[str] = None,
        force_disable: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.visibility_condition = visibility_condition
        self.visibility_var_path = visibility_var_path
        self.import_from = import_from
        self.force_disable = force_disable

    def _common(self) -> Dict[str, Any]:
        """Return the common spec fields dict."""
        out: Dict[str, Any] = {"name": self.name}
        if self.description:
            out["description"] = self.description
        if self.visibility_condition is not None:
            out["visibility_condition"] = self.visibility_condition
            out["visibility_var_path"] = self.visibility_var_path
        if self.import_from is not None:
            out["import_from"] = self.import_from
        if self.force_disable:
            out["force_disable"] = self.force_disable
        return out

    def to_spec(self) -> Dict[str, Any]:
        """Return a JSON-compatible spec dict for this node."""
        raise NotImplementedError

    def to_model(self):
        """Construct and return the live WaNo model for this node."""
        from SimStackServer.WaNo.WaNoSpec import spec_to_model

        return spec_to_model(self.to_spec())


# ---------------------------------------------------------------------------
# Scalar leaf nodes
# ---------------------------------------------------------------------------


class Float(_Node):
    """WaNoFloat — a floating-point parameter."""

    def __init__(self, name: str, value: float = -100.0, **kwargs) -> None:
        super().__init__(name, **kwargs)
        self.value = float(value)

    def to_spec(self) -> Dict[str, Any]:
        return {"type": "float", "value": self.value, **self._common()}


class Int(_Node):
    """WaNoInt — an integer parameter (stored as float internally)."""

    def __init__(self, name: str, value: int = -10000000, **kwargs) -> None:
        super().__init__(name, **kwargs)
        self.value = int(value)

    def to_spec(self) -> Dict[str, Any]:
        return {"type": "int", "value": float(self.value), **self._common()}


class Bool(_Node):
    """WaNoBool — a boolean parameter."""

    def __init__(self, name: str, value: bool = False, **kwargs) -> None:
        super().__init__(name, **kwargs)
        self.value = bool(value)

    def to_spec(self) -> Dict[str, Any]:
        return {"type": "bool", "value": self.value, **self._common()}


class String(_Node):
    """WaNoString — a text parameter."""

    def __init__(
        self,
        name: str,
        value: str = "",
        *,
        dynamic_output: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(name, **kwargs)
        self.value = str(value)
        self.dynamic_output = dynamic_output

    def to_spec(self) -> Dict[str, Any]:
        spec: Dict[str, Any] = {
            "type": "string",
            "value": self.value,
            **self._common(),
        }
        if self.dynamic_output is not None:
            spec["dynamic_output"] = self.dynamic_output
        return spec


class File(_Node):
    """WaNoFile — a file reference."""

    def __init__(
        self,
        name: str,
        path: str = "",
        logical_filename: str = "",
        local: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(name, **kwargs)
        self.path = path
        self.logical_filename = logical_filename
        self.local = local

    def to_spec(self) -> Dict[str, Any]:
        return {
            "type": "file",
            "path": self.path,
            "logical_filename": self.logical_filename,
            "local": self.local,
            **self._common(),
        }


class Choice(_Node):
    """WaNoChoice / WaNoDropDown — a fixed-option selector."""

    def __init__(
        self,
        name: str,
        choices: Sequence[str],
        chosen: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(name, **kwargs)
        self.choices = list(choices)
        self.chosen = int(chosen)

    def to_spec(self) -> Dict[str, Any]:
        return {
            "type": "choice",
            "choices": self.choices,
            "chosen": self.chosen,
            **self._common(),
        }


class DynamicChoice(_Node):
    """WaNoDynamicDropDown — a choice populated at runtime from a collection."""

    def __init__(
        self,
        name: str,
        collection_path: str = "",
        subpath: str = "",
        chosen: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(name, **kwargs)
        self.collection_path = collection_path
        self.subpath = subpath
        self.chosen = int(chosen)

    def to_spec(self) -> Dict[str, Any]:
        return {
            "type": "dynamic_choice",
            "collection_path": self.collection_path,
            "subpath": self.subpath,
            "chosen": self.chosen,
            **self._common(),
        }


class Matrix(_Node):
    """WaNoMatrixFloat / WaNoMatrixString — a 2-D table of values."""

    def __init__(
        self,
        name: str,
        rows: int = 0,
        cols: int = 0,
        *,
        col_header: Optional[Sequence[str]] = None,
        row_header: Optional[Sequence[str]] = None,
        data_text: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(name, **kwargs)
        self.rows = int(rows)
        self.cols = int(cols)
        self.col_header = list(col_header) if col_header is not None else None
        self.row_header = list(row_header) if row_header is not None else None
        self.data_text = data_text

    def to_spec(self) -> Dict[str, Any]:
        spec: Dict[str, Any] = {
            "type": "matrix",
            "rows": self.rows,
            "cols": self.cols,
            **self._common(),
        }
        if self.col_header is not None:
            spec["col_header"] = self.col_header
        if self.row_header is not None:
            spec["row_header"] = self.row_header
        if self.data_text is not None:
            spec["data_text"] = self.data_text
        return spec


class NoneNode(_Node):
    """WaNone — a no-op placeholder element."""

    def to_spec(self) -> Dict[str, Any]:
        return {"type": "none", **self._common()}


class ThreeRandom(_Node):
    """WaNoThreeRandomLetters — a random-string generator field."""

    def __init__(self, name: str, value: str = "", **kwargs) -> None:
        super().__init__(name, **kwargs)
        self.value = str(value)

    def to_spec(self) -> Dict[str, Any]:
        return {"type": "three_random", "value": self.value, **self._common()}


# ---------------------------------------------------------------------------
# Container nodes
# ---------------------------------------------------------------------------


class Box(_Node):
    """WaNoBox / WaNoGroup / WaNoTabs — a named dict-like container.

    Children are passed as positional arguments so composition reads
    naturally::

        Box("Settings",
            Float("temperature", value=300.0),
            Int("steps", value=1000),
        )
    """

    def __init__(
        self,
        name: str,
        *children: _Node,
        style: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(name, **kwargs)
        self.children: List[_Node] = list(children)
        self.style = style

    def to_spec(self) -> Dict[str, Any]:
        spec: Dict[str, Any] = {
            "type": "dict",
            "children": [c.to_spec() for c in self.children],
            **self._common(),
        }
        if self.style is not None:
            spec["style"] = self.style
        return spec


class SwitchOption:
    """A single named option inside a :class:`Switch` node."""

    def __init__(self, switch_name: str, node: _Node) -> None:
        self.switch_name = switch_name
        self.node = node

    def to_spec(self) -> Dict[str, Any]:
        return {"switch_name": self.switch_name, "spec": self.node.to_spec()}


class Switch(_Node):
    """WaNoSwitch — selects one of several sub-models at runtime.

    Example::

        Switch(
            "algorithm",
            SwitchOption("dft", Box("DFT", Float("cutoff", value=300.0))),
            SwitchOption("mp2", Box("MP2", Int("n_excited", value=5))),
            switch_path="Settings.method",
        )
    """

    def __init__(
        self,
        name: str,
        *options: SwitchOption,
        switch_path: str = "",
        **kwargs,
    ) -> None:
        super().__init__(name, **kwargs)
        self.switch_path = switch_path
        self.options: List[SwitchOption] = list(options)

    def to_spec(self) -> Dict[str, Any]:
        return {
            "type": "switch",
            "switch_path": self.switch_path,
            "options": [o.to_spec() for o in self.options],
            **self._common(),
        }


class MultipleOf(_Node):
    """WaNoMultipleOf — a user-extensible list of structured items.

    Parameters
    ----------
    name:
        Element name.
    template:
        Sequence of ``_Node`` instances describing the shape of each item.
    items:
        Optional pre-populated items, each a sequence of ``_Node`` instances
        whose types match *template*.  Omit to start empty.

    Example::

        MultipleOf(
            "molecules",
            template=[String("name"), Float("mass")],
            items=[
                [String("name", value="H2O"), Float("mass", value=18.015)],
                [String("name", value="CO2"), Float("mass", value=44.01)],
            ],
        )
    """

    def __init__(
        self,
        name: str,
        template: Sequence[_Node],
        items: Optional[Sequence[Sequence[_Node]]] = None,
        **kwargs,
    ) -> None:
        super().__init__(name, **kwargs)
        self.template: List[_Node] = list(template)
        self.items: List[List[_Node]] = [list(item) for item in (items or [])]

    def to_spec(self) -> Dict[str, Any]:
        return {
            "type": "multipleof",
            "template": {"children": [c.to_spec() for c in self.template]},
            "items": [
                {"children": [c.to_spec() for c in item]} for item in self.items
            ],
            **self._common(),
        }


# ---------------------------------------------------------------------------
# Root node
# ---------------------------------------------------------------------------


class Root:
    """Builder for the top-level WaNo (``<WaNoTemplate>``).

    Children are passed as positional arguments::

        Root(
            "MyWaNo",
            Box("Settings", Float("T", value=300.0)),
            exec_command="run.sh",
            output_files=["results.yml"],
            input_files=[("template.sh", "scripts/template.sh")],
        ).to_model()
    """

    def __init__(
        self,
        name: str,
        *children: _Node,
        exec_command: str = "",
        output_files: Optional[Sequence[str]] = None,
        input_files: Optional[Sequence[Tuple[str, str]]] = None,
        metas: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.children: List[_Node] = list(children)
        self.exec_command = exec_command
        self.output_files: List[str] = list(output_files or [])
        # input_files: sequence of (logical_filename, path) tuples
        self.input_files: List[Tuple[str, str]] = list(input_files or [])
        self.metas: Dict[str, Any] = dict(metas or {})

    def to_spec(self) -> Dict[str, Any]:
        return {
            "type": "root",
            "name": self.name,
            "exec_command": self.exec_command,
            "output_files": self.output_files,
            "input_files": [
                {"logical_filename": lf, "path": p}
                for lf, p in self.input_files
            ],
            "metas": self.metas,
            "children": [c.to_spec() for c in self.children],
        }

    def to_model(self):
        """Construct and return a live ``WaNoModelRoot``."""
        from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

        return WaNoModelRoot.from_spec(self.to_spec())
