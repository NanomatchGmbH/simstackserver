#!/usr/bin/env python3
import configparser
import yaml
import os
import sys

from jinja2 import Template


class ReportRenderer():
    """
    Very lightweight report renderer. Every WaNo may have a report, which is a HTML body element 
    """
    render_string = """
<!DOCTYPE html>
<html>
<title>%s</title>
<style> type="text/css">
%s
</style>
<body>
%s
</body>
</html>
"""
    def __init__(self, html_parts, export_dictionaries):
        self._body = None
        self._style = ""
        self._title = None
        self._parse_html_parts(html_parts)

        self._export_dictionaries = {}
        for dict_name, filename in export_dictionaries.items():
            if filename.endswith(".ini"):
                content = configparser.ConfigParser(strict = False)
                with open(filename, 'rt') as infile:
                    content_string = "[DEFAULT]\n" + infile.read()
                content.read_string(content_string)
                content = self._config_as_dict(content)
            elif filename.endswith(".yml"):
                with open(filename, 'rt') as infile:
                   content = yaml.safe_load(infile)
            self._export_dictionaries[dict_name] = content
            

    @staticmethod
    def _config_as_dict(config):
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

    def _parse_html_parts(self, html_parts):

        assert "body" in html_parts, "Every report requires a body"
        assert "title" in html_parts, "Every report requires a title"
        self._title = html_parts["title"]
        bodyfilename = html_parts["body"]

        with open(bodyfilename,'rt') as infile:
            self._body = infile.read()

        if "style" in html_parts:
            stylefilename = html_parts["style"]
            with open(stylefilename,'rt') as infile:
                self._style = infile.read()

    def render(self):
        torender = self.render_string%(self._title,self._style,self._body)
        tm = Template(torender)
        outstring = tm.render(**self._export_dictionaries)
        return outstring
    
    @staticmethod
    def render_everything():
        html_parts_dict = {}
        if not os.path.isfile("report_template.body"):
            return

        html_parts_dict["body"] = "report_template.body"
        title = os.path.basename(os.path.dirname(os.path.realpath(".")))

        html_parts_dict["title"] = title
        if os.path.isfile("report_style.css"):
            html_parts_dict["style"] = "report_style.css"


        export_dictionaries = {}
        if os.path.isfile("output_config.ini"):
            export_dictionaries["output_config"] = "output_config.ini"
        if os.path.isfile("output_dict.yml"):
            export_dictionaries["output_dict"] = "output_dict.yml"

        a = ReportRenderer(html_parts_dict, export_dictionaries)
        report = a.render()

        with open("report.html",'wt') as outfile:
            outfile.write(report)

if __name__ == '__main__':
    ReportRenderer.render_everything()



    


