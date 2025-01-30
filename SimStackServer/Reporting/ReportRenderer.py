import configparser
from os.path import join
from typing import Any

import yaml
import os

from jinja2 import Template


def _config_as_dict(config: configparser.ConfigParser) -> dict[str, Any]:
    """
    Converts a ConfigParser object into a dictionary.

    The resulting dictionary has sections as keys which point to a dict of the
    sections options as key => value pairs.
    """
    the_dict = {}
    for section in config.sections():
        the_dict[section] = {}
        for key, val in config.items(section):
            the_dict[section][key] = val
    return the_dict


class ReportRenderer:
    """
    Very lightweight report renderer. Every WaNo may have a report, which is a HTML body element
    """

    render_string = """
<!DOCTYPE html>
<html>
<title>%s</title>
<style type="text/css">
%s
</style>
<body>
%s
</body>
</html>
"""

    def __init__(self, export_dictionaries: dict[str, Any]):
        """
        Class to read wano export dictionaries and render a report from the info inside.

        export_dictinaries: Filenames of the dictionaries containing the wano export variables.

        # Example export_dictionaries variable filled with data
        export_dictionaries = {
            "output_config": "output_config.ini",
            "output_dict": "output_dict.yml",
            "wano": "rendered_wano.yml",
        }
        """
        self._body_html = None
        self._export_dictionaries = {}
        for dict_name, filename in export_dictionaries.items():
            if filename.endswith(".ini"):
                content = configparser.ConfigParser(strict=False)
                with open(filename, "rt") as infile:
                    content_string = "[global]\n" + infile.read()
                content.read_string(content_string)
                content = _config_as_dict(content)
            elif filename.endswith(".yml"):
                with open(filename, "rt") as infile:
                    content = yaml.safe_load(infile)
            self._export_dictionaries[dict_name] = content

    def consolidate_export_dictionaries(self):
        """
        Consolidates all export dictionaries into a single dictionary.

        Returns:
            dict: A dictionary containing all key-value pairs from the export dictionaries.
        """
        outdict = {}
        for indict in self._export_dictionaries.values():
            outdict.update(indict)
        return outdict

    @staticmethod
    def _parse_html_parts(html_parts: dict[str, str]) -> tuple[str, str, str]:
        """
        Parses the HTML parts dictionary to extract the title, body, and style.

        Args:
            html_parts (dict[str, str]): A dictionary containing the HTML parts with keys:
                - 'title': The title of the report.
                - 'body': The filename of the body content.
                - 'style': The filename of the CSS style (optional).

        Returns:
            tuple[str, str, str]: A tuple containing the title, body content, and style content.
        """
        style = ""
        assert "body" in html_parts, "Every report requires a body"
        assert "title" in html_parts, "Every report requires a title"
        title = html_parts["title"]
        bodyfilename = html_parts["body"]

        with open(bodyfilename, "rt") as infile:
            body = infile.read()

        if "style" in html_parts:
            stylefilename = html_parts["style"]
            with open(stylefilename, "rt") as infile:
                style = infile.read()
        return title, body, style

    def render(self, html_parts: dict[str, str]) -> str:
        """
        Renders the report using the provided HTML parts.

        Args:
            html_parts (dict[str, str]): A dictionary containing the HTML parts with keys:
                - 'title': The title of the report.
                - 'body': The filename of the body content.
                - 'style': The filename of the CSS style (optional).

        Returns:
            str: The rendered HTML report as a string.
        """
        title, body, style = self._parse_html_parts(html_parts)
        torender = self.render_string % (title, style, body)
        tm = Template(torender)
        outstring = tm.render(**self._export_dictionaries)
        tmbody = Template(body)
        body_only_render = tmbody.render(**self._export_dictionaries)
        self._body_html = body_only_render
        return outstring

    def get_body(self) -> str | None:
        """
        Returns the body part of the rendered report as a string.

        Returns:
            str | None: The body HTML as a string, or None if the report was not rendered yet.
        """
        return self._body_html

    @staticmethod
    def render_everything(basepath: str, do_render: bool = True):
        """
        Renders the report using the provided basepath.

        Args:
            basepath (str): A string representing the base directory containing three optional files:
                            - `output_config.ini`
                            - `output_dict.yml`
                            - `rendered_wano.yml`
            do_render (bool): A flag to indicate whether to perform the rendering. Defaults to True.

        Returns:
            ReportRenderer: An instance of the ReportRenderer class.
        """
        export_dictionaries = {}
        oci = join(basepath, "output_config.ini")

        if os.path.isfile(oci):
            export_dictionaries["output_config"] = oci
        ody = join(basepath, "output_dict.yml")
        if os.path.isfile(ody):
            export_dictionaries["output_dict"] = ody
        wanof = join(basepath, "rendered_wano.yml")
        if os.path.isfile(wanof):
            export_dictionaries["wano"] = wanof
        report_renderer = ReportRenderer(export_dictionaries)
        if do_render:
            html_parts_dict = {}
            rtb = join(basepath, "report_template.body")
            if not os.path.isfile(rtb):
                return

            html_parts_dict["body"] = rtb
            title = os.path.basename(os.path.dirname(os.path.realpath(basepath)))

            html_parts_dict["title"] = title
            rsc = join(basepath, "report_style.css")
            if os.path.isfile(rsc):
                html_parts_dict["style"] = rsc

            report = report_renderer.render(html_parts_dict)

            with open(join(basepath, "report.html"), "wt") as outfile:
                outfile.write(report)
        return report_renderer
