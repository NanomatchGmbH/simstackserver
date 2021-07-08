import json
import pathlib
import zipfile
from dataclasses import dataclass
from typing import Any




@dataclass
class WaNoListEntry:
    name: str
    folder: pathlib.Path
    icon: Any

def get_wano_xml_path(myfolder: pathlib.Path, wano_name_override = None) -> pathlib.Path:
    if isinstance(myfolder, zipfile.Path):
        pp = pathlib.PurePath(str(myfolder))
        name = pp.name[:-4]
    else:
        name = myfolder.name
    meta_json = myfolder / "meta.json"
    if wano_name_override is not None:
        name = wano_name_override
    xmlabs = myfolder / (name + ".xml")

    try:
        if meta_json.exists():
            with meta_json.open("rt") as infile:
                metadict = json.load(infile)
                xmlfile = metadict["xml"]
                xmlabs = myfolder / xmlfile
    except KeyError as e:
        # Might be an old meta.json, might be something else, we fallback to default xml name
        pass

    return xmlabs
