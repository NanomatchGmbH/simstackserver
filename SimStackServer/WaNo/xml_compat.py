#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
XML → WaNoSpec translation layer.

This is the ONLY module in the WaNo subsystem that should import lxml or
xmltodict for WaNo XML parsing.  Everything else works with plain dict specs.
"""
import pathlib
from typing import Any, Dict, List

import xmltodict

# ---------------------------------------------------------------------------
# Tag → spec-type mapping
# ---------------------------------------------------------------------------

XML_TAG_TO_SPEC_TYPE: Dict[str, str] = {
    "WaNoFloat": "float",
    "WaNoMatrixFloat": "matrix",
    "WaNoMatrixString": "matrix",
    "WaNoInt": "int",
    "WaNoString": "string",
    "WaNoBox": "dict",
    "WaNoDictBox": "dict",
    "WaNoInviBox": "dict",
    "WaNoSwitch": "switch",
    "WaNoGroup": "dict",
    "WaNoBool": "bool",
    "WaNoFile": "file",
    "WaNoChoice": "choice",
    "WaNoDropDown": "choice",
    "WaNoMultipleOf": "multipleof",
    "WaNoScriptV2": "string",
    "WaNoDynamicDropDown": "dynamic_choice",
    "WaNoTabs": "dict",
    "WaNone": "none",
    "WaNoThreeRandomLetters": "three_random",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_regular_element(el) -> bool:
    """Return True for normal XML elements, False for comments / PIs.

    Works with both lxml and stdlib ElementTree elements.
    """
    try:
        from lxml import etree as _etree

        if isinstance(el, (_etree.CommentBase, _etree._Comment)):
            return False
    except (ImportError, AttributeError):
        pass
    # stdlib ElementTree: comments / PIs have a callable .tag
    if callable(getattr(el, "tag", None)):
        return False
    return True


def _common_fields(xml_el) -> Dict[str, Any]:
    """Extract fields present on every WaNo model element."""
    spec: Dict[str, Any] = {"name": xml_el.attrib.get("name", "unnamed")}
    if desc := xml_el.attrib.get("description"):
        spec["description"] = desc
    if vc := xml_el.attrib.get("visibility_condition"):
        spec["visibility_condition"] = vc
        spec["visibility_var_path"] = xml_el.attrib.get("visibility_var_path", "")
    if imp := xml_el.attrib.get("import_from"):
        spec["import_from"] = imp
    if fd := xml_el.attrib.get("force_disable"):
        spec["force_disable"] = fd.lower() == "true"
    return spec


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def element_to_spec(xml_el) -> Dict[str, Any]:
    """Convert any WaNo XML element to a spec dict.

    Works with both lxml elements and stdlib ElementTree elements.
    The returned dict is JSON-serialisable.
    """
    tag = xml_el.tag
    spec_type = XML_TAG_TO_SPEC_TYPE[tag]
    spec: Dict[str, Any] = {"type": spec_type}
    spec.update(_common_fields(xml_el))

    if spec_type == "float":
        text = xml_el.text
        spec["value"] = float(text) if (text and text.strip()) else -100.0

    elif spec_type == "int":
        text = xml_el.text
        spec["value"] = float(text) if (text and text.strip()) else -10000000.0

    elif spec_type in ("string", "three_random"):
        spec["value"] = xml_el.text or ""
        if "dynamic_output" in xml_el.attrib:
            spec["dynamic_output"] = xml_el.attrib["dynamic_output"]

    elif spec_type == "bool":
        text = (xml_el.text or "false").strip().lower()
        spec["value"] = text == "true"

    elif spec_type == "file":
        spec["path"] = xml_el.text or ""
        spec["logical_filename"] = xml_el.attrib.get("logical_filename", "")
        local_attr = xml_el.attrib.get("local", "True")
        spec["local"] = local_attr.lower() == "true"

    elif spec_type == "choice":
        choices: List[str] = []
        chosen = 0
        for entry in xml_el.iter("Entry"):
            if not _is_regular_element(entry):
                continue
            idx = int(entry.attrib.get("id", len(choices)))
            choices.append(entry.text or "")
            if entry.attrib.get("chosen", "").lower() == "true":
                chosen = idx
        spec["choices"] = choices
        spec["chosen"] = chosen

    elif spec_type == "dynamic_choice":
        spec["collection_path"] = xml_el.attrib.get("collection_path", "")
        spec["subpath"] = xml_el.attrib.get("subpath", "")
        spec["chosen"] = int(xml_el.attrib.get("chosen", "0"))

    elif spec_type == "matrix":
        spec["rows"] = int(xml_el.attrib.get("rows", "0"))
        spec["cols"] = int(xml_el.attrib.get("cols", "0"))
        if "col_header" in xml_el.attrib:
            spec["col_header"] = xml_el.attrib["col_header"].split(";")
        if "row_header" in xml_el.attrib:
            spec["row_header"] = xml_el.attrib["row_header"].split(";")
        text = xml_el.text
        spec["data_text"] = text if (text and text.strip()) else None

    elif spec_type == "dict":
        spec["children"] = [
            element_to_spec(child)
            for child in xml_el
            if _is_regular_element(child)
        ]
        if "style" in xml_el.attrib:
            spec["style"] = xml_el.attrib["style"]

    elif spec_type == "switch":
        spec["switch_path"] = xml_el.attrib.get("switch_path", "")
        options = []
        for child in xml_el:
            if not _is_regular_element(child):
                continue
            options.append(
                {
                    "switch_name": child.attrib.get("switch_name", ""),
                    "spec": element_to_spec(child),
                }
            )
        spec["options"] = options

    elif spec_type == "multipleof":
        items_xml = [c for c in xml_el if _is_regular_element(c)]
        if items_xml:
            spec["template"] = {
                "children": [
                    element_to_spec(c)
                    for c in items_xml[0]
                    if _is_regular_element(c)
                ]
            }
        else:
            spec["template"] = {"children": []}
        spec["items"] = [
            {
                "children": [
                    element_to_spec(c) for c in item if _is_regular_element(c)
                ]
            }
            for item in items_xml
        ]

    elif spec_type == "none":
        pass  # No extra fields beyond common ones

    return spec


def root_xml_to_spec(xml_root) -> Dict[str, Any]:
    """Convert a WaNo ``<WaNoTemplate>`` root element to a spec dict.

    Raises ``ValueError`` if ``WaNoExecCommand`` contains child elements
    (preserving the original ``WaNoParseError`` check).
    """
    from lxml import etree

    output_files: List[str] = []
    for child in xml_root.findall("./WaNoOutputFiles/WaNoOutputFile"):
        output_files.append(child.text or "")

    input_files: List[Dict[str, str]] = []
    for child in xml_root.findall("./WaNoInputFiles/WaNoInputFile"):
        input_files.append(
            {
                "logical_filename": child.attrib.get("logical_filename", ""),
                "path": child.text or "",
            }
        )

    metas: Dict = {}
    meta_el = xml_root.find("./WaNoMeta")
    if meta_el is not None:
        metas = xmltodict.parse(etree.tostring(meta_el))

    exec_cmd_el = xml_root.find("WaNoExecCommand")
    if exec_cmd_el is None:
        exec_command = ""
    else:
        for _child in exec_cmd_el:
            # Preserve the original WaNoParseError semantics: raise here so
            # callers in WaNoModels.py can catch and wrap it.
            raise ValueError(
                "Another XML element was found in WaNoExecCommand. "
                "(This can be comments or open-and-close tags.) "
                "This is not supported."
            )
        exec_command = exec_cmd_el.text or ""

    wano_root_el = xml_root.find("WaNoRoot")
    name = (
        wano_root_el.attrib.get("name", "unnamed")
        if wano_root_el is not None
        else "unnamed"
    )

    children = []
    if wano_root_el is not None:
        for child in wano_root_el:
            if _is_regular_element(child):
                children.append(element_to_spec(child))

    return {
        "type": "root",
        "name": name,
        "exec_command": exec_command,
        "output_files": output_files,
        "input_files": input_files,
        "metas": metas,
        "children": children,
    }


def xml_file_to_spec(xml_path: pathlib.Path) -> Dict[str, Any]:
    """Load a WaNo XML file from disk and return a spec dict."""
    from lxml import etree

    with xml_path.open("rt") as f:
        xml_root = etree.parse(f).getroot()
    return root_xml_to_spec(xml_root)
