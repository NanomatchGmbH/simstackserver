#!/usr/bin/env python3
import configparser
from os.path import join

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
    def __init__(self, export_dictionaries):
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

    def consolidate_export_dictionaries(self):
        outdict = {}
        for indict in self._export_dictionaries.values():
            outdict.update(indict)
        return outdict

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

    @staticmethod
    def _parse_html_parts(html_parts):
        style = ""
        assert "body" in html_parts, "Every report requires a body"
        assert "title" in html_parts, "Every report requires a title"
        title = html_parts["title"]
        bodyfilename = html_parts["body"]

        with open(bodyfilename,'rt') as infile:
            body = infile.read()

        if "style" in html_parts:
            stylefilename = html_parts["style"]
            with open(stylefilename,'rt') as infile:
                style = infile.read()
        return title, body, style

    def render(self, html_parts):
        title, body, style = self._parse_html_parts(html_parts)
        torender = self.render_string%(title,style,body)
        tm = Template(torender)
        outstring = tm.render(**self._export_dictionaries)
        return outstring
    
    @staticmethod
    def render_everything(basepath, do_render = True):


        export_dictionaries = {}
        oci = join(basepath, "output_config.ini")

        if os.path.isfile(oci):
            export_dictionaries["output_config"] = oci
        ody = join(basepath, "output_dict.yml")
        if os.path.isfile(ody):
            export_dictionaries["output_dict"] = ody

        a = ReportRenderer(export_dictionaries)
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

            report = a.render(html_parts_dict)

            with open(join(basepath,"report.html"),'wt') as outfile:
                outfile.write(report)
        return a

if __name__ == '__main__':
    ReportRenderer.render_everything(".")



    


