import os
import pathlib
import sys
import tempfile

import pytest
from unittest.mock import patch, MagicMock

from SimStackServer.WaNo.MiscWaNoTypes import WaNoListEntry
from SimStackServer.WaNo.WaNoFactory import (
    WaNoFactory,
    wano_constructor,
    wano_constructor_helper,
    wano_without_view_constructor_helper,
)
from SimStackServer.WaNo.WaNoModels import WaNoItemFloatModel

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


class TestWaNoFactory:
    @pytest.fixture
    def tmpdir(self) -> tempfile.TemporaryDirectory:
        with tempfile.TemporaryDirectory() as mydir:
            yield mydir

    @pytest.fixture
    def tmppath(self, tmpdir):
        yield pathlib.Path(tmpdir)

    def test_get_model_class(self):
        mc = WaNoFactory.get_model_class("WaNoFloat")
        assert mc is WaNoItemFloatModel

        with pytest.raises(KeyError):
            mc = WaNoFactory.get_model_class("not_existing_type")

    def test_get_qt_view_class(self):
        # Test getting view class
        view_class = WaNoFactory.get_qt_view_class("WaNoFloat")
        assert view_class is None
        mock_bool = MagicMock(name="WaNoItemBoolView")
        mock_import = MagicMock()
        mock_import.WaNoItemBollView = mock_bool
        with patch.dict(sys.modules, {"simstack.view.WaNoViews": mock_import}):
            view_class = WaNoFactory.get_qt_view_class("WaNoBool")
            assert view_class._mock_name == "WaNoItemBoolView"

    def test_wano_constructor(self, tmppath):
        my_wano_list_entry = WaNoListEntry(
            name="My Entry", folder=pathlib.Path("/some/folder"), icon=None
        )

        def mock_wch(a):
            return a, "fake_view"

        with patch(
            "SimStackServer.WaNo.WaNoModels.WaNoModelRoot"
        ) as mock_wano_model_root:
            fake_root_instance = MagicMock(name="FakeWaNoModelRoot")
            fake_root_instance.set_view_class.return_value = None
            mock_wano_model_root.return_value = fake_root_instance
            wmr, rootview = wano_constructor(my_wano_list_entry, model_only=True)
            assert rootview is None

            mock_bool = MagicMock(name="WaNoItemBoolView")
            mock_import = MagicMock()
            mock_import.WaNoItemBollView = mock_bool
            with patch.dict(sys.modules, {"simstack.view.WaNoViews": mock_import}):
                with patch(
                    "SimStackServer.WaNo.WaNoFactory.wano_constructor_helper",
                    side_effect=mock_wch,
                ):
                    wmr, rootview = wano_constructor(my_wano_list_entry)
                    assert wmr == fake_root_instance
                    assert rootview == "fake_view"

    def test_wano_construtor_helper(self, tmpdir):
        with patch(
            "SimStackServer.WaNo.WaNoFactory.ViewCollector"
        ) as mock_view_collector:
            with patch(
                "SimStackServer.WaNo.WaNoFactory.WaNoTreeWalker"
            ) as mock_tree_walker:
                fake_view_collector_instance = MagicMock(name="fake_vc")
                fake_view_collector_instance.set_start_path.return_value = None
                fake_view_collector_instance.set_wano_model_root.return_value = None
                fake_root_view = MagicMock(name="fake_rootview")
                fake_root_view.set_parent.return_value = None
                fake_root_view.get_root.return_value = None
                fake_root_view.init_from_model.return_value = None
                fake_view_collector_instance.get_views_by_path.return_value = {
                    (): fake_root_view
                }
                mock_view_collector.return_value = fake_view_collector_instance

                fake_treewalker_instance = MagicMock(name="fake_newtw")
                fake_treewalker_instance.walker.return_value = None
                mock_tree_walker.return_value = fake_treewalker_instance
                with patch.dict(
                    sys.modules,
                    {"PySide6": MagicMock(), "PySide6.QtWidgets": MagicMock()},
                ):
                    # Now any references to QtWidgets inside wano_constructor_helper
                    # will use 'mock_qt' instead of the real PySide6.QtWidgets.

                    # Optionally configure mock_qt. For example:
                    wmr, rootview = wano_constructor_helper(fake_root_view)
                    assert wmr == fake_root_view
                    fake_root_view.set_parent.assert_called_once()
                    fake_root_view.init_from_model.assert_called()

    def test_wano_without_view_constructor_helper(self):
        with patch(
            "SimStackServer.WaNo.WaNoFactory.ViewCollector"
        ) as mock_view_collector:
            with patch(
                "SimStackServer.WaNo.WaNoFactory.WaNoTreeWalker"
            ) as mock_tree_walker:
                fake_view_collector_instance = MagicMock(name="fake_vc")
                fake_view_collector_instance.set_start_path.return_value = None
                fake_view_collector_instance.set_wano_model_root.return_value = None
                mock_view_collector.return_value = fake_view_collector_instance
                fake_root_view = MagicMock(name="fake_rootview")
                fake_root_view.set_parent.return_value = None
                fake_root_view.get_root.return_value = None

                fake_treewalker_instance = MagicMock(name="fake_newtw")
                fake_treewalker_instance.walker.return_value = None
                mock_tree_walker.return_value = fake_treewalker_instance

                assert (
                    wano_without_view_constructor_helper(fake_root_view)
                    == fake_root_view
                )
                fake_treewalker_instance.walker.assert_called()
                fake_view_collector_instance.set_wano_model_root.assert_called_once()
