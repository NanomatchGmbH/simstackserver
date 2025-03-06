import os
import pathlib
import sys
import json
from unittest.mock import MagicMock, patch

import pytest

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from SimStackServer.Util.ClusterSettings import (
    get_clustersettings_filename_from_folder,
    remove_clustersettings_from_folder,
    get_cluster_settings_from_folder,
    save_cluster_settings_to_folder,
)
from SimStackServer.WorkflowModel import Resources


@pytest.fixture
def tmppath(tmpdir):
    yield pathlib.Path(tmpdir)


@pytest.fixture
def cluster_settings(tmppath):
    clusters = {
        "cluster1": {
            "host": "host1.example.com",
            "port": 22,
            "username": "user1",
            "queue": "queue1",
            "scheduler": "slurm",
        },
        "cluster2": {
            "host": "host2.example.com",
            "port": 22,
            "username": "user2",
            "queue": "queue2",
            "scheduler": "pbs",
        },
    }
    for key, value in clusters.items():
        with open(tmppath / f"{key}.clustersettings", "w") as of:
            json.dump(value, of, indent=2)
    yield clusters


@pytest.fixture
def emptypath(tmppath):
    targetdir = tmppath / "empty"
    if not targetdir.exists():
        os.mkdir(targetdir)
    yield targetdir

def test_get_clustersettings_filename_from_folder(tmppath, cluster_settings):
    clustername = [key for key in cluster_settings.keys()][0]
    result = get_clustersettings_filename_from_folder(tmppath, clustername)
    assert result == tmppath / f"{clustername}.clustersettings"

def test_remove_clustersettings_from_folder(tmppath, cluster_settings):
    clustername = [key for key in cluster_settings.keys()][0]
    mock_gcfff = MagicMock()
    mock_gcfff.unlink.return_value = None
    with patch("SimStackServer.Util.ClusterSettings.get_clustersettings_filename_from_folder", return_value = mock_gcfff):
        remove_clustersettings_from_folder(tmppath, clustername)
    mock_gcfff.unlink.assert_called_once()


def test_get_cluster_settings_from_folder(tmppath,emptypath,cluster_settings):
    assert get_cluster_settings_from_folder(emptypath) == {}
    assert [k for k in get_cluster_settings_from_folder(tmppath).keys()] == [k for k in cluster_settings.keys()]

def test_save_cluster_settings_to_folder(tmppath, cluster_settings):
    loaded_cluster_settings = get_cluster_settings_from_folder(tmppath)
    new_path = tmppath / "new_folder"
    if not new_path.exists():
        os.mkdir(new_path)
    save_cluster_settings_to_folder(new_path, loaded_cluster_settings)
    for key in cluster_settings.keys():
        file = new_path / f"{key}.clustersettings"
        assert file.exists()
