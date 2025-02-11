import copy
import os

from _pytest.python_api import raises

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
)
from xml.etree.ElementTree import fromstring


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
    assert wiim.get_secure_schema() == {"key": {"type": "int"}}
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
    wifm.set_data("inputs/molecule.pdb")
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


def test_WaNoSwitch():
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
    # ToDo: set root to enable set_path and decommission
    # wm.set_root(res)
    # wm.set_path("update.path")
    # wm.decommission()


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


def test_MultipleOf():
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
        this_item = item.model_to_dict(outdict)
    assert outdict == {
        "test_float": {
            "Type": "Float",
            "content": "1.0",
            "data": "1.0",
            "name": "test_float",
        },
        "test_string": {"Type": "String", "content": '"Hello"', "name": "test_string"},
    }
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
    # requires root
    # wm.add_item()
    # assert wm.number_of_multiples() == 2
    wm.delete_item()
    assert wm.number_of_multiples() == 1
    assert wm.get_type_str() == "MultipleOf"
    all_data = wm.get_data()
    all_data.append(all_data[0])
    wm.set_data(all_data)
    assert wm.number_of_multiples() == 2
    assert wm.get_delta_to_default() == 2
    assert wm.changed_from_default() is True
    wm.set_parent_visible(True)
    wm.set_visible(True)
    wm.update_xml()


# def test_WaNoModelRoot():
#    xml = fromstring(
#        """
#            <WaNoRoot name="DummyRoot">
#                <WaNoInt name="dummy_int">0</WaNoInt>
#            </WaNoRoot>
#        """
#    )
#    wm = WaNoModelRoot(explicit_xml=xml)
#    this_xml_return = wm.parse_from_xml()
#    assert this_xml_return is None
#    sec_schema = wm.get_secure_schema()
#    print()
