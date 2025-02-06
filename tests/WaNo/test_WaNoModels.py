from SimStackServer.WaNo.WaNoModels import WaNoItemStringModel, WaNoThreeRandomLetters
from xml.etree.ElementTree import fromstring


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
