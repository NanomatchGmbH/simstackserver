import pathlib

from SimStackServer.WorkflowModel import Resources


___clustersettings_file_ending = ".clustersettings"


def get_clustersettings_filename_from_folder(
    folder: pathlib.Path, clustername: str
) -> pathlib.Path:
    global ___clustersettings_file_ending
    return folder / f"{clustername}{___clustersettings_file_ending}"


def remove_clustersettings_from_folder(folder: pathlib.Path, clustername: str) -> None:
    filename = get_clustersettings_filename_from_folder(folder, clustername)
    filename.unlink(missing_ok=True)


def get_cluster_settings_from_folder(folder: pathlib.Path):
    global ___clustersettings_file_ending
    outdict = {}
    for file in folder.iterdir():
        if not file.is_file():
            continue
        elif not str(file).endswith(___clustersettings_file_ending):
            continue
        else:
            name = file.stem
            r = Resources()
            r.from_json(file)
            outdict[name] = r
    return outdict


def save_cluster_settings_to_folder(
    folder: pathlib.Path, clustersettings: dict[str, Resources]
):
    global ___clustersettings_file_ending
    for name, resources in clustersettings.items():
        outpath = get_clustersettings_filename_from_folder(folder, name)
        resources.to_json(outpath)
