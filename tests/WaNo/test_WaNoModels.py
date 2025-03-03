import copy
import json
import os
import pathlib
from json import JSONDecodeError
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from _pytest.python_api import raises
from jsonschema.exceptions import ValidationError

from SimStackServer.Util.Exceptions import SecurityError
from SimStackServer.WaNo.WaNoModels import (
    WaNoItemStringModel,
    WaNoThreeRandomLetters,
    WaNoItemIntModel,
    WaNoItemBoolModel,
    WaNoNoneModel,
    WaNoItemFloatModel,
    WaNoItemFileModel,
    WaNoChoiceModel,
    WaNoSwitchModel,
    WaNoModelDictLike,
    MultipleOfModel,
    WaNoItemScriptFileModel,
    WaNoModelRoot,
    WaNoParseError,
    WaNoMatrixModel,
)
from xml.etree.ElementTree import fromstring

from SimStackServer.WaNo.WaNoModels import mkdir_p


def test_mkdir_p(tmpdir):
    new_dir = tmpdir + "/" + "testdir"
    mkdir_p(new_dir)
    assert pathlib.Path(new_dir).exists()

    mkdir_p(new_dir)

    with pytest.raises(OSError):
        mkdir_p("/norightstomkthis")


def test_WaNoItemIntModel():
    wiim = WaNoItemIntModel()
    xml = fromstring(
        """
                <WaNoInt name="key">2</WaNoInt>
            """
    )
    wiim.parse_from_xml(xml)
    assert wiim.get_data() == 2
    wiim.set_data(3)
    assert wiim.get_data() == 3
    assert wiim.get_secure_schema() == {"key": {"type": "number"}}
    assert wiim.get_delta_to_default() == 3
    wiim.apply_delta(4)
    assert wiim.get_data() == 4
    assert wiim.changed_from_default() is True
    assert wiim.get_type_str() == "Int"
    wiim.set_data(13)
    wiim.update_xml()
    assert wiim.xml.text == "13"
    assert repr(wiim) == "13"
    wiim._do_import = True
    assert wiim.changed_from_default() is True


def test_WaNoItemFloatModel():
    wifm = WaNoItemFloatModel()
    xml = fromstring(
        """
                <WaNoFloat name="key">2.0</WaNoFloat>
            """
    )
    wifm.parse_from_xml(xml)
    assert wifm.changed_from_default() is False
    assert wifm.get_data() == 2.0
    wifm.set_data(3.0)
    old_xml = wifm.xml.text
    wifm.update_xml()
    new_xml = wifm.xml.text
    assert new_xml == "3.0"
    assert old_xml != new_xml
    assert wifm.get_data() == 3.0
    assert wifm.get_secure_schema() == {"key": {"type": "number"}}
    assert wifm.get_delta_to_default() == 3.0
    wifm.apply_delta(4.0)
    assert wifm.get_data() == 4.0
    assert wifm.changed_from_default() is True
    assert wifm.get_type_str() == "Float"
    assert repr(wifm) == "4.0"
    wifm._do_import = True
    assert wifm.changed_from_default() is True


def test_WaNoItemBoolModel():
    wibm = WaNoItemBoolModel()
    xml = fromstring(
        """
                <WaNoBool name="key">False</WaNoBool>
            """
    )
    xml_lower_true = fromstring(
        """
                <WaNoBool name="key">true</WaNoBool>
            """
    )
    xml_lower_false = fromstring(
        """
                <WaNoBool name="key">false</WaNoBool>
            """
    )
    wibm.parse_from_xml(xml)
    assert wibm.get_data() is False
    wibm.set_data(True)
    assert wibm.get_data() is True
    assert wibm.get_secure_schema() == {"key": {"type": "boolean"}}
    assert wibm.get_delta_to_default() is True
    wibm.apply_delta(False)
    assert wibm.get_data() is False
    wibm.set_data(True)
    assert wibm.changed_from_default() is True
    assert wibm.get_type_str() == "Boolean"
    wibm.set_data(False)
    wibm.update_xml()
    assert wibm.xml.text == "False"
    wibm.set_data(True)
    wibm.update_xml()
    assert wibm.xml.text == "True"

    wibm.parse_from_xml(xml_lower_true)
    assert wibm.get_data() is True
    wibm.parse_from_xml(xml_lower_false)
    assert wibm.get_data() is False


def test_WaNoItemStringModel():
    wism = WaNoItemStringModel()
    xml = fromstring(
        """
        <WaNoString name="key">content</WaNoString>
    """
    )
    wism.parse_from_xml(xml)
    assert wism.get_data() == "content"
    wism.set_data("newcontent")
    old_xml = copy.deepcopy(wism.xml.text)
    wism.update_xml()
    new_xml = wism.xml.text
    assert new_xml != old_xml
    assert new_xml == "newcontent"
    assert wism.get_data() == "newcontent"
    assert wism.get_delta_to_default() == "newcontent"
    result = wism.get_secure_schema()
    assert result == {"key": {"type": "string"}}
    assert repr(wism) == "'newcontent'"
    assert wism.changed_from_default() is True
    assert wism.get_type_str() == "String"


def test_WaNoItemScriptFileModel():
    wm = WaNoItemScriptFileModel()
    xml = fromstring(
        """
            <WaNoScriptV2 name="Script" logical_filename="input.script">input.script</WaNoScriptV2>
        """
    )
    wm.parse_from_xml(xml)
    assert wm.get_type_str() == "File"
    # assert wm.get_as_text()
    # wm.render()
    # wm.save_text()
    # wm.get_path()


def test_WaNoFileModel(tmpdir):
    wifm = WaNoItemFileModel()
    xml = fromstring(
        """
        <WaNoFile logical_filename="molecule_test.pdb" name="molecule_pdb">molecule.pdb</WaNoFile>
        """
    )
    wifm.parse_from_xml(xml)
    assert wifm.get_data() == "molecule.pdb"
    wifm.set_data("molecule_2.pdb")
    assert wifm.get_data() == "molecule_2.pdb"
    old_xml = copy.deepcopy(wifm.xml.text)
    wifm.update_xml()
    new_xml = wifm.xml.text
    assert new_xml != old_xml
    assert new_xml == "molecule_2.pdb"
    with raises(SecurityError):
        wifm.get_secure_schema()
    assert wifm.get_local() is True
    wifm.set_local(False)
    assert wifm.get_local() is False
    wifm.set_local(True)
    assert wifm.get_type_str() == "File"
    assert wifm.get_rendered_wano_data() == "molecule_test.pdb"
    assert wifm.get_delta_to_default() == "local://molecule_2.pdb"
    wifm.apply_delta("global://molecule_3.pdb")
    assert wifm.get_data() == "molecule_3.pdb"
    assert wifm.get_local() is False
    assert wifm.changed_from_default() is True
    assert repr(wifm) == "'molecule_3.pdb'"
    assert wifm.cached_logical_name() == "unset"
    my_outdict = {}
    wifm.model_to_dict(my_outdict)
    assert my_outdict == {
        "Type": "File",
        "content": "molecule_3.pdb",
        "logical_name": "unset",
        "name": "molecule_pdb",
    }
    wifm.set_local(True)
    wifm.set_visible(False)
    assert wifm.render({}, "./", "./") == "molecule_test.pdb"
    wifm.set_visible(True)
    testmol = Path(__file__).parent / "inputs" / "molecule.pdb"
    wifm.set_data(str(testmol))
    dest_file = tmpdir + "/inputs/molecule_test.pdb"
    assert wifm.render({}, "./", tmpdir) == "molecule_test.pdb"
    assert os.path.exists(dest_file)


def test_WaNoChoice():
    wm = WaNoChoiceModel()
    xml = fromstring(
        """
        <WaNoChoice name="Interpreter">
           <Entry id="0">Bash</Entry>
           <Entry id="1" chosen="true">Python</Entry>
           <Entry id="2">Perl</Entry>
        </WaNoChoice>
        """
    )
    wm.parse_from_xml(xml)
    assert wm.get_data() == "Python"
    wm.chosen = 4
    assert wm.get_data() == "Bash"
    wm.chosen = 1
    assert wm.get_type_str() == "String"
    assert wm.__getitem__("someitem") is None
    wm.set_chosen(2)
    wm.update_xml()
    assert wm.get_data() == "Perl"
    assert wm.changed_from_default() is True
    assert wm.get_delta_to_default() == "Perl"
    wm.apply_delta("Python")
    assert wm.get_data() == "Python"
    old_xml = copy.deepcopy(wm.xml)
    wm.update_xml()
    new_xml = wm.xml
    for iter_id, child in enumerate(old_xml.iter("Entry")):
        if "chosen" in child.attrib:
            old_id = iter_id
            break
    for iter_id, child in enumerate(new_xml.iter("Entry")):
        if "chosen" in child.attrib:
            new_id = iter_id
            break
    assert old_id == 2
    assert new_id == 1
    assert wm.get_secure_schema() == {
        "Interpreter": {"enum": ["Bash", "Python", "Perl"]}
    }


def test_WaNoSwitch(capsys):
    wm = WaNoSwitchModel()
    xml = fromstring(
        """
        <WaNoSwitch switch_path="switch.path" name="MySwitch">
            <WaNoString name="test_var" switch_name="switch_string">"Hello"</WaNoString>
            <WaNoFloat name="test_var" switch_name="switch_float">2.0</WaNoFloat>
        </WaNoSwitch>
        """
    )
    wm.parse_from_xml(xml)

    parent_xml = fromstring(
        """
        <WaNoDictBox name="ParentXML">
        </WaNoDictBox>
        """
    )
    wm_parent = WaNoModelDictLike()
    wm_parent.parse_from_xml(parent_xml)
    # Do some checks before assigning a delta to run into some options of the checks
    assert wm.get_selected_id() == 0
    assert wm.get_data() == "unset"
    assert wm.get_type_str() == "unset"
    # ToDo: set a view so we can check line 677. What object is wm._view ?
    # wm.set_view(0)

    wano_list_data = [item.get_data() for item in wm.wano_list]
    wano_list_reversed_data = [item.get_data() for item in wm.__reversed__()]
    wano_item_data = [item.get_data() for (i, item) in wm.items()]

    assert wano_list_data == ['"Hello"', 2.0]
    assert wano_list_reversed_data == [2.0, '"Hello"']
    assert wano_item_data == ['"Hello"', 2.0]
    assert wm.listlike is True
    assert wm.dictlike is False
    wm.apply_delta(0)
    assert wm.changed_from_default() is True
    assert wm.get_secure_schema() == {
        "oneOf": [{"test_var": {"type": "string"}}, {"test_var": {"type": "number"}}]
    }
    assert wm.get_selected_id() == 0
    assert wm.get_type_str() == "String"
    mockview = MagicMock()
    mockview.init_from_model.return_value is None
    wm.set_view(mockview)
    wm.apply_delta(1)
    assert wm.get_selected_id() == 1
    assert wm.get_type_str() == "Float"
    assert wm.get_data() == 2.0
    assert wm.get_delta_to_default() == 1
    wm.set_parent(wm_parent)
    res = wm.get_parent()
    assert res.get_secure_schema() == {
        "ParentXML": {
            "additionalProperties": False,
            "properties": {},
            "required": [],
            "type": "object",
        }
    }
    wano_list_iter = wm.__iter__()

    data_list = ['"Hello"', 2.0]
    for i in wano_list_iter:
        assert i.get_data() in data_list

    mockroot = MagicMock()
    mock_root_value = MagicMock()
    mock_root_value.get_data.return_value = "switch_float"
    mockroot.get_value.return_value = mock_root_value
    mockroot.register_callback.return_value = None
    mockroot.unregister_callback.return_value = None
    wm.set_root(mockroot)

    wm._evaluate_switch_condition("changed_path")
    wm._evaluate_switch_condition("force")
    # make throw key error
    wm._switch_name_list = ["fake_key", "fake_data", "switch_string", "switch_float"]

    wm._evaluate_switch_condition("force")
    captured = capsys.readouterr()
    assert captured.out.startswith("This will")

    wm.set_path("update.path")
    wm.decommission()


def test_WaNoModelDictLike():
    wm = WaNoModelDictLike()
    # ToDo: I don't see why with the comments I don't get into line 97
    xml = fromstring(
        """
        <!-- comment -->
        <WaNoDictBox name="ParentXML">
            <!--comment-->
            <WaNoString name="test_string" >Hello</WaNoString>
            <WaNoFloat name="test_float" >2.0</WaNoFloat>
        </WaNoDictBox>
        """
    )

    wm = WaNoModelDictLike()
    wm.parse_from_xml(xml)
    assert wm.wano_dict["test_string"].get_data() == "Hello"
    assert wm.wano_dict["test_float"].get_data() == 2.0

    dict_keys = ["test_string", "test_float"]
    dict_values = ["Hello", 2.0]

    assert wm.dictlike is True
    for key in wm.keys():
        assert key in dict_keys

    for value in wm.values():
        assert value.get_data() in dict_values
    for value in wm.values():
        assert value.get_data() in dict_values

    for item in wm.items():
        assert item[0] in dict_keys and item[1].get_data() in dict_values
        assert wm.__getitem__(item[0]) == item[1]

    it = wm.__iter__()
    firstkey = next(it)
    assert firstkey == dict_keys[0]

    assert wm.changed_from_default() is False

    mydict = wm.get_data()
    for key in mydict.keys():
        assert key in dict_keys

    mydict["test_float_add"] = copy.deepcopy(wm.get_data()["test_float"])
    wm.set_data(mydict)
    assert len([key for key in wm.keys()]) == 3
    prev_xml = wm.xml.text
    wm.update_xml()
    new_xml = wm.xml.text
    assert prev_xml == new_xml  # ToDo: Double check if this should do anything

    sec_scheme = wm.get_secure_schema()
    assert sec_scheme == {
        "ParentXML": {
            "additionalProperties": False,
            "properties": {
                "test_float": {"type": "number"},
                "test_string": {"type": "string"},
            },
            "required": ["test_string", "test_float", "test_float_add"],
            "type": "object",
        }
    }

    assert wm.get_type_str() == "Dict"

    this_is_visible = copy.deepcopy(wm._isvisible)
    wm.set_visible(not this_is_visible)
    assert wm._isvisible is not this_is_visible

    parent_xml = fromstring(
        """
        <WaNoDictBox name="ParentXML">
        </WaNoDictBox>
        """
    )
    wm_parent = WaNoModelDictLike()
    wm_parent.parse_from_xml(parent_xml)

    wm.set_visible(True)
    wm.set_parent(wm_parent)
    assert wm._parent_visible is True
    wm.set_parent_visible(False)
    assert wm._parent_visible is False
    wm.decommission()


def test_WaNoModelDictLike_sec_schema():
    xml_switches = fromstring(
        """
        <WaNoDictBox name="ParentXML">
            <WaNoSwitch switch_path="switch.path" name="MySwitch">
                <WaNoString name="test_var" switch_name="switch_string">"Hello"</WaNoString>
                <WaNoFloat name="test_var" switch_name="switch_float">2.0</WaNoFloat>
            </WaNoSwitch>
            <WaNoSwitch switch_path="switch.path.2" name="MySwitch2">
                <WaNoString name="test_var" switch_name="switch_string">"Hello"</WaNoString>
                <WaNoFloat name="test_var" switch_name="switch_float">2.0</WaNoFloat>
            </WaNoSwitch>
        </WaNoDictBox>
        """
    )

    xml_switch_single = fromstring(
        """
        <WaNoDictBox name="ParentXML">
            <WaNoSwitch switch_path="switch.path" name="MySwitch">
                <WaNoString name="test_var" switch_name="switch_string">"Hello"</WaNoString>
                <WaNoFloat name="test_var" switch_name="switch_float">2.0</WaNoFloat>
            </WaNoSwitch>
        </WaNoDictBox>
        """
    )
    wm_switch_single = WaNoModelDictLike()
    wm_switch_single.parse_from_xml(xml_switch_single)
    sec_scheme = wm_switch_single.get_secure_schema()
    assert sec_scheme == {
        "ParentXML": {
            "additionalProperties": False,
            "oneOf": [
                {"test_var": {"type": "string"}},
                {"test_var": {"type": "number"}},
            ],
            "properties": {},
            "required": [],
            "type": "object",
        }
    }

    wm_switches = WaNoModelDictLike()
    wm_switches.parse_from_xml(xml_switches)
    with pytest.raises(NotImplementedError):
        wm_switches.get_secure_schema()


@patch(
    "SimStackServer.WaNo.WaNoModels.WaNoItemFloatModel.get_secure_schema",
    return_value=None,
)
def test_WaNoModelDictLike_no_schema_child(mocK_get_secure_schema):
    wm = WaNoModelDictLike()
    # ToDo: I don't see why with the comments I don't get into line 97
    xml = fromstring(
        """
        <WaNoDictBox name="ParentXML">
            <WaNoString name="test_string" >Hello</WaNoString>
            <WaNoFloat name="test_float" >2.0</WaNoFloat>
        </WaNoDictBox>
        """
    )
    wm.parse_from_xml(xml)
    with raises(NotImplementedError):
        wm.get_secure_schema()


def test_WaNoMatrixModel():
    wm = WaNoMatrixModel()

    xml = fromstring(
        """
        <WaNoMatrixModel name="MyMatrix" rows="2" cols="2">
        </WaNoMatrixModel>
        """
    )
    wm.parse_from_xml(xml)


def test_WaNoMatrixModel_no_text():
    """
    Verify that parse_from_xml correctly initializes storage with empty strings
    when <WaNoMatrixModel> has no text content.
    """
    wm = WaNoMatrixModel()
    xml = fromstring(
        """
        <WaNoMatrixModel name="MyMatrix" rows="2" cols="2"/>
        """
    )
    wm.parse_from_xml(xml)

    # Basic checks
    assert wm.rows == 2
    assert wm.cols == 2

    # With no text in the XML, the code sets up an empty matrix of "".
    assert wm.storage == [["", ""], ["", ""]]
    assert wm._default == [["", ""], ["", ""]]
    assert wm.col_header is None
    assert wm.row_header is None
    assert not wm.changed_from_default()


def test_WaNoMatrixModel_headers():
    """
    Verify that row_header and col_header are parsed correctly.
    """
    wm = WaNoMatrixModel()
    xml = fromstring(
        """
        <WaNoMatrixModel name="MyMatrix" rows="2" cols="2"
                         row_header="R1;R2" col_header="C1;C2">
        </WaNoMatrixModel>
        """
    )
    wm.parse_from_xml(xml)
    assert wm.rows == 2
    assert wm.cols == 2
    # Should parse row_header and col_header from attributes
    assert wm.row_header == ["R1", "R2"]
    assert wm.col_header == ["C1", "C2"]
    assert wm.storage[1][1] == ""


def test_WaNoMatrixModel_with_text():
    """
    Verify that parse_from_xml calls _fromstring if XML has text,
    thus properly populating storage with typed values.
    """
    wm = WaNoMatrixModel()

    # Example text: a 2x2 matrix with numeric and string data
    matrix_text = '[ [1, "Hello"], [2.5, "World"] ]'

    xml = fromstring(
        f"""
        <WaNoMatrixModel name="MyMatrix" rows="2" cols="2">
            {matrix_text}
        </WaNoMatrixModel>
        """
    )
    wm.parse_from_xml(xml)

    expected_storage = [[1.0, "Hello"], [2.5, "World"]]
    assert wm.storage == expected_storage
    assert wm._default == expected_storage  # after parse, _default is a deep copy

    # Test that changed_from_default is false initially
    assert not wm.changed_from_default()

    assert (
        wm.__getitem__("randomitem") == '[ [  1.0 , "Hello" ] , [  2.5 , "World" ] ] '
    )
    assert wm.get_data() == '[ [  1.0 , "Hello" ] , [  2.5 , "World" ] ] '
    assert wm.get_type_str() is None


def test_WaNoMatrixModel_set_data_and_delta():
    """
    Check that set_data modifies the matrix, and that changed_from_default,
    get_delta_to_default, and apply_delta behave correctly.
    """
    wm = WaNoMatrixModel()

    xml = fromstring(
        """
        <WaNoMatrixModel name="MyMatrix" rows="2" cols="2">
            [ [1, 2], [3, 4] ]
        </WaNoMatrixModel>
        """
    )
    wm.parse_from_xml(xml)

    # Initially, _default matches storage
    assert wm.storage == [[1.0, 2.0], [3.0, 4.0]]
    assert not wm.changed_from_default()

    # Modify one cell
    wm.set_data(0, 1, 99)
    assert wm.storage == [[1.0, 99.0], [3.0, 4.0]]
    # Now it should differ from _default
    assert wm.changed_from_default()

    # We can inspect the delta string
    delta = wm.get_delta_to_default()
    # e.g., "[ [ 1.0 , 99.0 ] , [ 3.0 , 4.0 ] ]"
    # The exact formatting depends on _tostring logic
    assert "99.0" in delta

    # If we re-apply the old default (undo changes) => storage = default => no changes
    default_str = wm._tostring(wm._default)  # The original matrix
    wm.apply_delta(default_str)
    assert not wm.changed_from_default()
    assert wm.storage == wm._default


def test_WaNoMatrixModel_update_xml():
    """
    Verify that update_xml sets the underlying XML text to the string form of storage.
    """
    wm = WaNoMatrixModel()
    xml = fromstring(
        """
        <WaNoMatrixModel name="MyMatrix" rows="2" cols="2">
            [ [ "A", "B"], [3, 4.5] ]
        </WaNoMatrixModel>
        """
    )
    wm.parse_from_xml(xml)

    # Make a small change
    wm.set_data(0, 0, "XYZ")
    wm.update_xml()
    # Now xml.text should reflect the new storage:
    assert "XYZ" in xml.text
    # Another check:
    assert "B" in xml.text
    assert "4.5" in xml.text


def test_WaNoMatrixModel_secure_schema():
    """
    Check that get_secure_schema returns the expected dictionary structure.
    """
    wm = WaNoMatrixModel()
    xml = fromstring(
        """
        <WaNoMatrixModel name="MyMatrix" rows="2" cols="2">
            [ [1, 2], [3, 4] ]
        </WaNoMatrixModel>
        """
    )
    wm.parse_from_xml(xml)

    schema = wm.get_secure_schema()
    assert isinstance(schema, dict)
    # "name" attribute was "MyMatrix" => the schema key should match
    assert "MyMatrix" in schema
    # We expect something like: {"type": "string", "pattern": r"\[\s*\[.+\]\s*\]"}
    assert schema["MyMatrix"]["type"] == "string"
    assert "pattern" in schema["MyMatrix"]


def test_WaNoModel_Syntaxerror():
    wm = WaNoMatrixModel()
    xml = fromstring(
        """
        <WaNoMatrixModel name="MyMatrix" rows="2" cols="2">
            1
        </WaNoMatrixModel>
        """
    )
    with raises(SyntaxError):
        wm.parse_from_xml(xml)


def test_WaNoThreeRandomLetters():
    wism = WaNoThreeRandomLetters()
    xml = fromstring(
        """
        <WaNoThreeRandomLetters name="key"/>
    """
    )
    wism.parse_from_xml(xml)
    assert len(wism.get_data()) == 3

    assert len(wism._generate_default_string()) == 3

    wism.set_data("newcontent")
    assert wism.get_data() == "new"
    assert wism.get_delta_to_default() == "new"
    # Check that existing content is not overwritten
    wism = WaNoThreeRandomLetters()
    xml = fromstring(
        """
        <WaNoThreeRandomLetters name="key">FIXEDCONTENT</WaNoThreeRandomLetters>
    """
    )
    wism.parse_from_xml(xml)
    assert repr(wism) == "'FIXEDCONTENT'"


def test_WaNoNoneModel():
    wm = WaNoNoneModel()
    xml = fromstring(
        """
                <WaNoNone name="key">False</WaNoNone>
            """
    )
    wm.parse_from_xml(xml)
    wm.set_data(None)
    wm.update_xml()
    assert wm.get_data() == ""
    assert wm.get_type_str() == "String"
    assert wm.changed_from_default() is False
    assert wm.get_secure_schema() == {"key": {"type": "string"}}
    assert repr(wm) == ""
    assert wm.__getitem__("someitem") is None


def test_MultipleOf(tmpWaNoRoot):
    wm_with_switches = MultipleOfModel()
    xml_1_switch = fromstring(
        """
        <WaNoMultipleOf name="Molecules">
            <Element id="0">
               <WaNoString name="test_string">"Hello"</WaNoString>
               <WaNoFloat name="test_float">1.0</WaNoFloat>
               <WaNoSwitch switch_path="switch.path" name="MySwitch">
                 <WaNoString name="test_var" switch_name="switch_string">"Hello"</WaNoString>
                 <WaNoFloat name="test_var" switch_name="switch_float">2.0</WaNoFloat>
               </WaNoSwitch>
            </Element>
        </WaNoMultipleOf>
        """
    )
    xml_2_switch = fromstring(
        """
        <WaNoMultipleOf name="Molecules">
            <Element id="0">
               <WaNoString name="test_string">"Hello"</WaNoString>
               <WaNoFloat name="test_float">1.0</WaNoFloat>
               <WaNoSwitch switch_path="switch.path" name="MySwitch">
                 <WaNoString name="test_var" switch_name="switch_string">"Hello"</WaNoString>
                 <WaNoFloat name="test_var" switch_name="switch_float">2.0</WaNoFloat>
               </WaNoSwitch>
               <WaNoSwitch switch_path="switch2.path2" name="MySwitch2">
                 <WaNoString name="test_var" switch_name="switch_string">"Hello"</WaNoString>
                 <WaNoFloat name="test_var" switch_name="switch_float">2.0</WaNoFloat>
               </WaNoSwitch>
            </Element>
        </WaNoMultipleOf>
        """
    )
    wm_with_switches.parse_from_xml(xml_1_switch)
    assert wm_with_switches.get_secure_schema() == {
        "Molecules": {
            "items": {
                "additionalProperties": False,
                "oneOf": [
                    {"test_var": {"type": "string"}},
                    {"test_var": {"type": "number"}},
                ],
                "properties": {
                    "test_float": {"type": "number"},
                    "test_string": {"type": "string"},
                },
                "type": "object",
            },
            "required": ["test_string", "test_float"],
            "type": "array",
        }
    }
    wm_with_two_switches = MultipleOfModel()
    wm_with_two_switches.parse_from_xml(xml_2_switch)
    with raises(NotImplementedError):
        wm_with_two_switches.get_secure_schema()

    wm = MultipleOfModel()
    xml = fromstring(
        """
        <WaNoMultipleOf name="Molecules">
            <Element id="0">
               <WaNoString name="test_string">"Hello"</WaNoString>
               <WaNoFloat name="test_float">1.0</WaNoFloat>
            </Element>
        </WaNoMultipleOf>
        """
    )
    wm.parse_from_xml(xml)

    parent_xml = fromstring(
        """
        <WaNoDictBox name="ParentXML">
        </WaNoDictBox>
        """
    )
    wm_parent = WaNoModelDictLike()
    wm_parent.parse_from_xml(parent_xml)

    assert wm.numitems_per_add() == 2
    assert wm.listlike is True
    wm.set_parent(wm_parent)

    mockroot = MagicMock()
    mockroot.block_signals.return_value = True
    mockroot.detachanged_force.return_value = None
    wm.set_root(mockroot)
    dummy_model = MagicMock()
    dummy_model.set_parent.return_value = None
    dummy_root = MagicMock()
    with patch(
        "SimStackServer.WaNo.WaNoFactory.wano_constructor_helper",
        return_value=(dummy_model, dummy_root),
    ):
        for child in wm.xml:
            wm.parse_one_child(child, build_view=True)

    assert wm.get_parent().get_secure_schema() == {
        "ParentXML": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }
    }
    assert wm.get_secure_schema() == {
        "Molecules": {
            "items": {
                "additionalProperties": False,
                "properties": {
                    "test_float": {"type": "number"},
                    "test_string": {"type": "string"},
                },
                "type": "object",
            },
            "required": ["test_string", "test_float"],
            "type": "array",
        }
    }

    assert wm.number_of_multiples() == 1
    assert wm.last_item_check() is True
    outdict = {}
    for i, item in wm.items():
        item.model_to_dict(outdict)
    assert outdict == {
        "test_float": {
            "Type": "Float",
            "content": "1.0",
            "data": "1.0",
            "name": "test_float",
        },
        "test_string": {"Type": "String", "content": '"Hello"', "name": "test_string"},
    }

    outlist = []
    for i, item in wm.__reversed__():
        outlist.append(item)
    assert outlist == ["test_float"]

    assert wm.__len__() == 1
    this_child = None

    with patch(
        "SimStackServer.WaNo.WaNoFactory.wano_constructor_helper",
        return_value=(dummy_model, dummy_root),
    ):
        for child in wm.xml:
            this_child = wm.parse_one_child(child, build_view=True)
            break
        with patch.object(wm, "parse_one_child", return_value=this_child):
            mockview = MagicMock()
            mockview.init_from_model.return_value = None
            wm.set_view(mockview)
            wm.add_item()

            wm.apply_delta(4)
            assert wm.number_of_multiples() == 4
            wm.set_view(None)
            wm.apply_delta(6)
            assert wm.number_of_multiples() == 6
            wm.apply_delta(2)
            assert wm.number_of_multiples() == 2

    single_outdict = {}
    wm.__getitem__(0).model_to_dict(single_outdict)
    assert single_outdict == {
        "test_float": {
            "Type": "Float",
            "content": "1.0",
            "data": "1.0",
            "name": "test_float",
        },
        "test_string": {"Type": "String", "content": '"Hello"', "name": "test_string"},
    }
    single_outdict = {}
    wm.get_data()[0].model_to_dict(single_outdict)
    assert single_outdict == {
        "test_float": {
            "Type": "Float",
            "content": "1.0",
            "data": "1.0",
            "name": "test_float",
        },
        "test_string": {"Type": "String", "content": '"Hello"', "name": "test_string"},
    }

    # assert wm.__reversed__() == reversed(wm.get_data())

    wm.set_root(tmpWaNoRoot)
    this_root = wm.get_root()
    assert this_root.get_name() == "DummyRoot"

    # TODO: fix add_item()
    # wm.add_item()
    # assert wm.number_of_multiples() == 2
    assert wm.delete_item() is True
    assert wm.number_of_multiples() == 1
    assert wm.delete_item() is False
    assert wm.get_type_str() == "MultipleOf"
    all_data = wm.get_data()
    all_data.append(all_data[0])
    wm.set_data(all_data)
    assert wm.number_of_multiples() == 2
    assert wm.get_delta_to_default() == 2
    assert wm.changed_from_default() is True
    wm.delete_item()
    assert wm.number_of_multiples() == 1
    wm.set_parent_visible(True)
    wm.set_visible(True)
    wm.update_xml()
    wm.decommission()


def test_WaNoModelRoot(
    tmpfileWaNoXml, tmpfileOutputIni, tmpfileOutputYaml, tmpdir, capsys
):
    xml_root_string = """
        <WaNoTemplate>
            <WaNoRoot name="DummyRoot">
                <WaNoInt name="dummy_int">0</WaNoInt>
            </WaNoRoot>
            <WaNoExecCommand>echo Hello</WaNoExecCommand>
            <WaNoOutputFiles>
                <WaNoOutputFile>output_config.ini</WaNoOutputFile>
                <WaNoOutputFile>output_dict.yml</WaNoOutputFile>
                <WaNoOutputFile>{{output_dict.yml}}</WaNoOutputFile>
            </WaNoOutputFiles>
            <WaNoInputFiles>
               <WaNoInputFile logical_filename="deposit_init.sh">deposit_init.sh</WaNoInputFile>
               <WaNoInputFile logical_filename="report_template.body">report_template.body</WaNoInputFile>
            </WaNoInputFiles>
            <WaNoMeta name="WaNoMeta"/>
        </WaNoTemplate>
    """

    xml_root_string_parser_error = """
            <WaNoTemplate>
                <WaNoRoot name="DummyRoot">
                    <WaNoInt name="dummy_int">0</WaNoInt>
                </WaNoRoot>
                <WaNoExecCommand>
                    <testchild/>
                </WaNoExecCommand>
            </WaNoTemplate>
        """

    with tmpfileWaNoXml.open("w") as f:
        f.write(xml_root_string_parser_error)

    current_directory = Path(tmpfileWaNoXml).parent

    with raises(WaNoParseError):
        wm = WaNoModelRoot(model_only=True, wano_dir_root=current_directory)

    with tmpfileWaNoXml.open("w") as f:
        f.write(xml_root_string)

    rr_mock = MagicMock()
    rr_mock.consolidate_export_dictionaries.return_value = {
        "key1": "value1",
        "key2": "value2",
    }
    with patch("SimStackServer.WaNo.WaNoModels.ReportRenderer", return_value=rr_mock):
        wm = WaNoModelRoot(model_only=True, wano_dir_root=current_directory)

    wm.parse_from_xml(xml_root_string)
    captured = capsys.readouterr()
    assert captured.out.strip() == "Fake Call"

    # ToDo The following does not work bc of simstack import in line 1006 not working. What is the correct import path for simstack.view?
    # mock_import_model = MagicMock()
    # mock_export_model = MagicMock()
    # with patch("SimStack.view.PropertyListView.ImportTableModel", return_value=mock_import_model):
    #   wm_2 = WaNoModelRoot(model_only=False, wano_dir_root=current_directory)

    mock_object = MagicMock()
    mock_object.load.return_value = None
    mock_object.make_default_list.return_value = None

    wm._exists_read_load(mock_object, pathlib.Path(tmpdir))
    mock_object.load.assert_called_once()
    wm._exists_read_load(mock_object, pathlib.Path(tmpdir + "/some_not_existing_dir"))
    mock_object.make_default_list.assert_called_once()

    mock_parent_wf = MagicMock()
    wm.set_parent_wf(mock_parent_wf)
    assert wm.get_parent_wf() == mock_parent_wf

    assert wm.get_name() == "DummyRoot"
    assert wm.get_type_str() == "WaNoRoot"
    assert wm.get_render_substitutions() == {}
    assert wm.get_new_resource_model().queue == "default"
    secure_schema = {
        "$id": "https://example.com/product.schema.json",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "description": "DummyRoot secure schema",
        "properties": {"dummy_int": {"type": "number"}},
        "required": ["dummy_int"],
        "title": "DummyRoot",
        "type": "object",
    }
    assert wm.get_secure_schema() == secure_schema
    wm.block_signals(True)
    assert wm.block_signals(False) is True
    with raises(ValueError):
        wm.verify_output_against_schema({})
    # ToDo: json validator has a problem with the schema with "type": "int" - maybe the get_secure_schema() is buggy
    wm.verify_against_secure_schema({"dummy_int": 1})
    with raises(ValidationError):
        wm.verify_against_secure_schema({"dummy_int": "1"})
    with raises(ValidationError):
        wm.verify_against_secure_schema({"dummy_int_2": 1})

    assert wm.get_import_model() is None
    assert wm.get_export_model() is None

    mock_template = MagicMock()
    mock_template.render.return_value = "myfile.dat"

    with raises(NotImplementedError):
        wm.save_xml(None)

    assert wm.get_all_variable_paths() == ["dummy_int", "key1", "key2"]
    assert wm.get_all_variable_paths(export=False) == ["dummy_int"]
    assert wm.get_paths_and_data_dict() == {"dummy_int": "0"}
    assert wm.get_extra_inputs_aiida() == ["deposit_init.sh", "report_template.body"]
    assert wm.get_paths_and_type_dict_aiida() == {"dummy_int": "Int"}
    # res4 = wm.get_valuedict_with_aiida_types()
    assert wm.get_dir_root().name == "WaNo"
    assert wm.get_metadata_dict() == {"folder": "WaNo", "name": "DummyRoot"}
    # ToDo: wano_walker_paths for dictlike and listlike
    assert wm.wano_walker_paths() == [("dummy_int", "Int")]

    # ToDo: Check if all these files need to be a fixture. Don't fully understand the difference
    tmp_path = pathlib.Path(tmpdir)
    importfile = tmp_path / "imports.yml"
    exportfile = tmp_path / "exports.yml"
    resourcesfile = tmp_path / "resources.yml"
    importfile.touch()
    exportfile.touch()
    resourcesfile.touch()
    mock_object = MagicMock()
    mock_object.load.return_value = None
    mock_object.make_default_list.return_value = None
    mock_object.get_contents.return_value = [["a"]]

    wm.import_model = mock_object
    wm.export_model = mock_object

    wm._read_export(tmp_path)

    validate_dict = {"dummy_int": 2}
    with raises(ValueError):
        wm.verify_output_against_schema(validate_dict)

    schema_file = tmp_path / "output_schema.json"
    schema_file.touch()
    with raises(JSONDecodeError):
        wm._read_output_schema(tmp_path)
    with open(schema_file, "w") as of:
        json.dump(secure_schema, of)
    wm._read_output_schema(tmp_path)
    assert wm._output_schema == secure_schema

    wm.verify_output_against_schema(validate_dict)
    validate_dict["invalid_entry"] = "invalid"
    with raises(ValidationError):
        wm.verify_output_against_schema(validate_dict)
    # wm._unregister_list = [["mykey", "myfunc", "mydep"]]
    # wm._register_list = [["mykey", "myfunc", "mydep"]]

    def mock_callback_with_path(path):
        return None

    wm._notifying = True
    wm.register_callback("cb_path", mock_callback_with_path, 1)
    assert ("cb_path", mock_callback_with_path, 1) in wm._register_list
    wm._notifying = False
    wm.register_callback("cb_path_2", mock_callback_with_path, 1)
    assert mock_callback_with_path in wm._datachanged_callbacks["cb_path_2"][1]
    wm.unregister_callback("cb_path_2", mock_callback_with_path, 1)
    assert ("cb_path_2", mock_callback_with_path, 1) not in wm._register_list
    wm._notifying = True
    assert wm.notify_datachanged("unset") is None
    wm._block_signals = True
    assert wm.notify_datachanged("unset") is None
    wm._block_signals = False
    wm._notifying = False
    wm.register_callback("cb_path_3", mock_callback_with_path, 1)
    wm.notify_datachanged("unset")
    captured = capsys.readouterr()
    assert captured.out.strip() == "Found unset in path unset"
    wm.notify_datachanged("cb_path_3")
    wm.notify_datachanged("force")

    wm.register_callback("cb_path_3", mock_callback_with_path, 1)
    wm._notifying = False
    wm.unregister_callback("cb_path_3", mock_callback_with_path, 1)

    with patch.object(wm, "register_callback", return_value=None):
        with patch.object(wm, "unregister_callback", return_value=None):
            wm._unregister_list = [["some", "thing", "tounregister"]]
            wm.notify_datachanged("unset")

    def mock_callback():
        return "None"

    wm.register_outputfile_callback(mock_callback)
    assert len(wm._outputfile_callbacks) == 1

    with patch("SimStackServer.WaNo.WaNoModels.Template", return_value=mock_template):
        assert wm.get_output_files(only_static=True) == [
            "output_config.ini",
            "output_dict.yml",
            "myfile.dat",
        ]
        wm.get_output_files(only_static=False)

    assert wm.get_changed_paths() == {}
    assert wm.get_changed_command_paths() == {}


@pytest.fixture
def WaNoModelListLike():
    # You'd typically import it from your module:
    from SimStackServer.WaNo.WaNoModels import WaNoModelListLike

    return WaNoModelListLike


def test_WaNoModelListLike(WaNoModelListLike):
    wm_style = WaNoModelListLike()
    xml = fromstring(
        """
        <WaNoModelListLike name="list" style="mystyle">
            <WaNoString name="test_string">"Hello"</WaNoString>
            <WaNoFloat name="test_float">1.0</WaNoFloat>
        </WaNoModelListLike>
    """
    )
    wm_style.parse_from_xml(xml)
    assert wm_style.style == "mystyle"

    wm = WaNoModelListLike()
    xml_nostyle = fromstring(
        """
        <WaNoModelListLike name="list">
            <WaNoString name="test_string">"Hello"</WaNoString>
            <WaNoFloat name="test_float">1.0</WaNoFloat>
        </WaNoModelListLike>
    """
    )
    wm.parse_from_xml(xml_nostyle)
    assert wm.style == ""

    assert wm.listlike is True

    assert wm.__len__() == 2, "Expected 2 submodels in wano_list"

    # Check the first is a WaNoStringModel, with the correct 'name' and contents
    first_model = wm[0]
    assert isinstance(first_model, WaNoItemStringModel)
    assert first_model.name == "test_string"
    # Depending on how WaNoStringModel works, we might check its storage or actual value
    # e.g., if it has 'value' or 'storage' attribute or similar:
    # assert first_model.some_internal_field == "Hello"

    # Check the second is a WaNoFloatModel
    second_model = wm[1]
    assert isinstance(second_model, WaNoItemFloatModel)
    assert second_model.name == "test_float"

    # children_data = ["Hello", 1.0]

    assert wm.get_type_str() is None
    for item in wm.items():
        # ToDo: I don't get why this does not work. It should!
        # assert item[1].get_data() in children_data
        assert isinstance(item[1], WaNoItemStringModel) or isinstance(
            item[1], WaNoItemFloatModel
        )

    for item in wm.wanos():
        # ToDo: I don't get why this does not work. It should!
        # assert item[1].get_data() in children_data
        assert isinstance(item[1], WaNoItemStringModel) or isinstance(
            item[1], WaNoItemFloatModel
        )

    wm.set_visible(True)
    wm.set_parent_visible(True)
    assert wm._parent_visible is True
    for item in wm.wanos():
        assert item[1]._parent_visible is True

    wm.set_parent_visible(False)
    assert wm._parent_visible is False
    for item in wm.wanos():
        assert item[1]._parent_visible is False

    assert wm.changed_from_default() is False

    assert wm.update_xml() is None

    assert wm.decommission() is None

    with raises(NotImplementedError):
        wm.get_secure_schema()
