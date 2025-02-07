import copy

from _pytest.python_api import raises

from SimStackServer.Util.Exceptions import SecurityError
from SimStackServer.WaNo.WaNoModels import (
    WaNoItemStringModel,
    WaNoThreeRandomLetters,
    WaNoItemIntModel,
    WaNoItemBoolModel,
    WaNoItemFloatModel,
    WaNoItemFileModel,
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


def test_WaNoItemFloatModel():
    wifm = WaNoItemFloatModel()
    xml = fromstring(
        """
                <WaNoFloat name="key">2.0</WaNoFloat>
            """
    )
    wifm.parse_from_xml(xml)
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


def test_WaNoItemBoolModel():
    wibm = WaNoItemBoolModel()
    xml = fromstring(
        """
                <WaNoBool name="key">False</WaNoBool>
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


def test_WaNoFileModel():
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
    # ToDo check if needed:
    # wifm.render(rendered_wano, submitdir)


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
