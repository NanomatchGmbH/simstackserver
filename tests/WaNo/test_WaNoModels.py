from SimStackServer.WaNo.WaNoModels import (
    WaNoItemStringModel,
    WaNoThreeRandomLetters,
    WaNoItemIntModel,
    WaNoItemBoolModel,
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
    assert wism.get_data() == "newcontent"
    assert wism.get_delta_to_default() == "newcontent"
    result = wism.get_secure_schema()
    assert result == {"key": {"type": "string"}}
    assert repr(wism) == "'newcontent'"
    assert wism.changed_from_default() is True
    assert wism.get_type_str() == "String"


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
