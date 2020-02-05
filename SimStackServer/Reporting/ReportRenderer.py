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
    def __init__(self, report_filename, export_dictionaries):
        self._parse_report(report_filename)
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

    def _parse_report(self, report_filename):
        with open(report_filename,'rt') as infile:
            self._report_template = infile.read()

    def render(self):
        tm = Template(self._report_template)
        outstring = tm.render(**self._export_dictionaries)
        return outstring
    
    @staticmethod
    def render_everything():
        if not os.path.isfile("report_template.html"):
            return

        export_dictionaries = {}
        if os.path.isfile("output_config.ini"):
            export_dictionaries["output_config"] = "output_config.ini"
        if os.path.isfile("output_dict.yml"):
            export_dictionaries["output_dict"] = "output_dict.yml"

        a = ReportRenderer("report_template.html", export_dictionaries)
        report = a.render()
        with open("report.html",'wt') as outfile:
            outfile.write(report)

if __name__ == '__main__':
    ReportRenderer.render_everything()



    


