import pytest
import configparser

from SimStackServer.Reporting.ReportRenderer import _config_as_dict


@pytest.fixture
def example_config():
    config = configparser.ConfigParser()
    config.add_section("Section1")
    config.set("Section1", "key1", "value1")
    config.set("Section1", "key2", "value2")
    config.add_section("Section2")
    config.set("Section2", "keya", "valueA")
    config.set("Section2", "keyb", "valueB")
    return config


# Test function
def test_config_as_dict(example_config):
    result = _config_as_dict(example_config)
    expected = {
        "Section1": {"key1": "value1", "key2": "value2"},
        "Section2": {"keya": "valueA", "keyb": "valueB"},
    }
    assert result == expected
