import json
from glob import glob
import os
from os.path import join
from io import StringIO
with open("setup_template.json",'rt') as infile:
    my = json.load(infile)
    assert "entry_points" in my

with open("wano_calcjob/calculations.py.template", 'rt') as infile:
    calcpytemplate = infile.read()

calcpy = StringIO()
calcpy.write(calcpytemplate)
def get_per_class_template(wanoname, wanodir, wanoxml):
    classtemplate = """class %sCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "%s", "%s.xml")
    _parser_name = "%s"
class %sParser(WaNoCalcJobParser):
    _calcJobClass = %sCalcJob

""" %(wanoname, wanodir, wanoxml, wanoname, wanoname, wanoname)
    return classtemplate

def get_exec_template(wanoname):
    mydir = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
    exec_template = """verdi code setup -Y local -L %s -P %s  --on-computer  -D %s  --remote-abs-path %s --prepend-text "echo \\"Starting %s\\"" --append-text "echo \\"%s finished\\"" """ %(wanoname, "arithmetic.add", wanoname, join(mydir, "wano-aiida-exec"), wanoname, wanoname)
    return exec_template

"""
    "entry_points": {
        "aiida.data": [
        ],
        "aiida.calculations": [
            "Deposit3 = wano_calcjob.calculations:DepositCalcJob"
        ],
        "aiida.parsers": [
            "Deposit3 = wano_calcjob.calculations:DepositParser"
        ],
        "aiida.cmdline.data": [
        ]
    },
"""

def read_wano_name(inxml):
    #Placeholder - we still need to parse the name from the wano xml
    return inxml

entry_points = {}
for field in ["data", "calculations", "parsers", "cmdline.data"]:
    entry_points["aiida.%s"%field] = []
for mydir in glob("wano_repo/*"):
    dirname = os.path.basename(mydir)
    if os.path.isdir(mydir):
        xmlname = join(mydir, dirname + ".xml")
        if os.path.exists(xmlname):
            #wano_name = read_wano_name(xmlname)
            wano_name = dirname
            calcname = "%s = wano_calcjob.calculations:%sCalcJob"%(wano_name, wano_name)
            parsername = "%s = wano_calcjob.calculations:%sParser"%(wano_name, wano_name)
            entry_points["aiida.calculations"].append(calcname)
            entry_points["aiida.parsers"].append(parsername)
            myclass = get_per_class_template(wano_name, mydir[10:], dirname)
            calcpy.write(myclass)

my["entry_points"] = entry_points
with open("setup.json",'wt') as outfile:
    json.dump(my, outfile, indent=4)

calcpy.flush()
with open("wano_calcjob/calculations.py", "wt") as outfile:
    outfile.write(calcpy.getvalue())

with open("register_calcjobs.sh", 'wt') as execsh:
    execsh.write(get_exec_template("wano-default-exec"))
