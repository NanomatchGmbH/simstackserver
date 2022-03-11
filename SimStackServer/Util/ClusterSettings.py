import pathlib

from SimStackServer.WorkflowModel import Resources


def get_cluster_settings_from_folder(folder: pathlib.Path):
    outdict = {}
    for file in folder.iterdir():
        if not file.is_file():
            continue
        else:
            name = file.stem
            r = Resources()
            r.from_json(file)
            outdict[name] = r
    return outdict

def save_cluster_settings_to_folder(folder: pathlib.Path, clustersettings: dict):
    for name, resources in clustersettings.items():
        outpath = folder/ f"{name}.json"
        resources.to_json(outpath)