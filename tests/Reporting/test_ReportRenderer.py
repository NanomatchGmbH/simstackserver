import shutil
from pathlib import Path

import pytest
import tempfile
import configparser

from SimStackServer.Reporting.ReportRenderer import _config_as_dict
from SimStackServer.Reporting.ReportRenderer import ReportRenderer


@pytest.fixture
def sample_reporting_input_dir():
    source_dir = Path(__file__).parent / "sample_report"
    with tempfile.TemporaryDirectory() as target_dir:
        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
        yield Path(target_dir)


@pytest.fixture
def sample_html_parts(sample_reporting_input_dir: Path):
    return {
        "title": "Test Report",
        "body": str(sample_reporting_input_dir / "report_template.body"),
        "style": str(sample_reporting_input_dir / "report_style.css"),
    }


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


def test_report_renderer_instantiation(sample_reporting_input_dir: Path):
    ReportRenderer.render_everything(sample_reporting_input_dir)
    with open(sample_reporting_input_dir / "report.html") as infile:
        report = infile.read()

    result_report = """
<!DOCTYPE html>
<html>
<title>tmp</title>
<style type="text/css">
TESTSTYLEHERE

</style>
<body>
Test1=Test1
local1=local1
global1=global1
wano1=wano1

</body>
</html>"""
    assert report == result_report


def test_report_renderer_get_body(sample_reporting_input_dir: Path):
    report_renderer = ReportRenderer.render_everything(sample_reporting_input_dir)
    body_html = report_renderer.get_body()
    expected_body = """Test1=Test1
local1=local1
global1=global1
wano1=wano1"""
    assert body_html == expected_body


def test_report_renderer_get_body_None(sample_reporting_input_dir: Path):
    report_renderer = ReportRenderer({})
    assert report_renderer.get_body() is None


def test_report_renderer_render(sample_reporting_input_dir: Path):
    report_renderer = ReportRenderer.render_everything(
        sample_reporting_input_dir, do_render=False
    )
    html_parts = {
        "title": "Test Report",
        "body": sample_reporting_input_dir / "report_template.body",
        "style": sample_reporting_input_dir / "report_style.css",
    }
    rendered_report = report_renderer.render(html_parts)
    expected_report = """
<!DOCTYPE html>
<html>
<title>Test Report</title>
<style type="text/css">
TESTSTYLEHERE

</style>
<body>
Test1=Test1
local1=local1
global1=global1
wano1=wano1

</body>
</html>
"""
    assert rendered_report.strip() == expected_report.strip()


def test_parse_html_parts(sample_reporting_input_dir: Path, sample_html_parts):
    title, body, style = ReportRenderer._parse_html_parts(sample_html_parts)

    assert title == "Test Report"
    with open(sample_reporting_input_dir / "report_template.body", "rt") as infile:
        expected_body = infile.read()
    assert body == expected_body

    with open(sample_reporting_input_dir / "report_style.css", "rt") as infile:
        expected_style = infile.read()
    assert style == expected_style


def test_consolidate_export_dictionaries(sample_reporting_input_dir: Path):
    report_renderer = ReportRenderer.render_everything(
        sample_reporting_input_dir, do_render=False
    )
    consolidated_dict = report_renderer.consolidate_export_dictionaries()
    expected_dict = {
        "global": {"global1key": "global1"},
        "local": {"local1key": "local1"},
        "Test1Key": "Test1",
        "wano1key": "wano1",
    }
    assert consolidated_dict == expected_dict
