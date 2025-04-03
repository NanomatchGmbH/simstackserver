import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from SimStackServer.WaNo.AbstractWaNoModel import OrderedDictIterHelper
from SimStackServer.WaNo.WaNoModels import WaNoModelDictLike, WaNoModelListLike


from SimStackServer.WaNo.WaNoTreeWalker import (
    PathCollector,
    WaNoTreeWalker,
    ViewCollector,
    subdict_skiplevel,
    subdict_skiplevel_to_type,
    subdict_skiplevel_path_version,
    subdict_skiplevel_to_aiida_type,
)


# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Import the class under test.
# Adjust the import path to match where PathCollector actually lives.


class TestPathCollector(unittest.TestCase):
    def setUp(self):
        # Create a fresh collector for each test
        self.collector = PathCollector()

    def test_init_starts_empty(self):
        self.assertEqual(self.collector.paths, [])
        self.assertEqual(self.collector.path_to_value, {})

    def test_assemble_paths_none(self):
        result = self.collector.assemble_paths(None)
        self.assertIsNone(result)
        # No path is appended if None is passed
        self.assertEqual(self.collector.paths, [])

    def test_assemble_paths_nonempty(self):
        twpath = ["root", "child"]
        result = self.collector.assemble_paths(twpath)
        # The function returns the same twpath
        self.assertEqual(result, twpath)
        # The collector stores a string-joined version
        self.assertIn("root.child", self.collector.paths)
        self.assertEqual(len(self.collector.paths), 1)

    def test_assemble_paths_and_values_no_abspath(self):
        # Simulate call_info with a nestdictmod_paths mock
        call_info = {"nestdictmod_paths": MagicMock()}
        # If abspath is None, the method should short-circuit
        call_info["nestdictmod_paths"].abspath = None

        data = "my_data"
        self.collector.assemble_paths_and_values(data, call_info)
        # No entry added if abspath is None
        self.assertEqual(self.collector.path_to_value, {})

    def test_assemble_paths_and_values_valid_abspath(self):
        call_info = {"nestdictmod_paths": MagicMock()}
        call_info["nestdictmod_paths"].abspath = ["root", "child"]
        data = "my_data"

        self.collector.assemble_paths_and_values(data, call_info)
        # Should store "root.child" -> "my_data"
        self.assertIn("root.child", self.collector.path_to_value)
        self.assertEqual(self.collector.path_to_value["root.child"], "my_data")

    def test_assemble_paths_and_type_no_abspath(self):
        call_info = {"nestdictmod_paths": MagicMock()}
        call_info["nestdictmod_paths"].abspath = None
        data = "type_info"

        self.collector.assemble_paths_and_type(data, call_info)
        # Again, no entry added if abspath is None
        self.assertEqual(self.collector.path_to_value, {})

    def test_assemble_paths_and_type_valid_abspath(self):
        call_info = {"nestdictmod_paths": MagicMock()}
        call_info["nestdictmod_paths"].abspath = ["section", "item", 42]
        data = "type_info"

        self.collector.assemble_paths_and_type(data, call_info)
        # Should store "section.item.42" -> "type_info"
        self.assertIn("section.item.42", self.collector.path_to_value)
        self.assertEqual(self.collector.path_to_value["section.item.42"], "type_info")


class TestViewCollector(unittest.TestCase):
    def setUp(self):
        self.collector = ViewCollector()

    def test_initial_state(self):
        """Check that initial attributes are set correctly."""
        self.assertEqual(self.collector.get_views_by_path(), {})
        self.assertIsNone(self.collector._wano_model_root)
        self.assertEqual(self.collector._start_path, [])

    def test_setters(self):
        """Test set_wano_model_root and set_start_path."""
        mock_root = MagicMock(name="MockWaNoModelRoot")
        self.collector.set_wano_model_root(mock_root)
        self.assertIs(self.collector._wano_model_root, mock_root)

        test_path = ["some", "nested", "path"]
        self.collector.set_start_path(test_path)
        self.assertEqual(self.collector._start_path, test_path)

    def test_get_mypath_treewalker_none_abspath(self):
        """
        If abspath is None, we expect an empty tuple for mypath
        and no error thrown.
        """
        call_info = {
            "nestdictmod_paths": MagicMock(abspath=None),
            "nestdictmod": MagicMock(name="MockNestDictMod"),
        }
        mypath, tw = self.collector._get_mypath_treewalker(call_info)
        self.assertEqual(mypath, ())
        self.assertIs(tw, call_info["nestdictmod"])

    def test_get_mypath_treewalker_valid_abspath(self):
        """
        If abspath is not None, mypath is that path as a tuple.
        """
        call_info = {
            "nestdictmod_paths": MagicMock(abspath=["root", "child"]),
            "nestdictmod": MagicMock(name="MockNestDictMod"),
        }
        mypath, tw = self.collector._get_mypath_treewalker(call_info)
        self.assertEqual(mypath, ("root", "child"))
        self.assertIs(tw, call_info["nestdictmod"])

    def test_root_setter_subdict_with_set_root_attr(self):
        """If subdict has set_root, call it with our _wano_model_root."""
        mock_root = MagicMock(name="MockRoot")
        self.collector.set_wano_model_root(mock_root)

        subdict = MagicMock()
        call_info = {}

        self.collector.root_setter_subdict(subdict, call_info)
        subdict.set_root.assert_called_once_with(mock_root)

    def test_root_setter_data_with_attr(self):
        """Similarly, if 'data' has set_root, we call it."""
        mock_root = MagicMock(name="MockRoot")
        self.collector.set_wano_model_root(mock_root)

        data = MagicMock()
        call_info = {}

        self.collector.root_setter_data(data, call_info)
        data.set_root.assert_called_once_with(mock_root)

    def test_path_setter_subdict_no_set_path(self):
        """If subdict has no set_path attribute, do nothing."""
        self.collector.set_start_path(["prefix"])
        subdict = MagicMock(spec=[])  # no set_path
        call_info = {
            "nestdictmod_paths": MagicMock(abspath=None),
            "nestdictmod": MagicMock(),
        }
        self.collector.path_setter_subdict(subdict, call_info)
        # No calls expected
        self.assertFalse(hasattr(subdict, "set_path"))

    def test_path_setter_subdict_valid_path(self):
        """If subdict has set_path, we join start_path + abspath as a dotted string."""
        self.collector.set_start_path(["prefix"])
        subdict = MagicMock()
        call_info = {
            "nestdictmod_paths": MagicMock(abspath=["level1", "level2"]),
            "nestdictmod": MagicMock(),
        }
        self.collector.path_setter_subdict(subdict, call_info)
        subdict.set_path.assert_called_once_with("prefix.level1.level2")

    def test_assemble_views_skip_ordered_dict_iter_helper(self):
        """
        If subdict is an OrderedDictIterHelper, return None immediately.
        Patch it so we can make subdict an instance of it.
        """
        subdict = OrderedDictIterHelper()
        call_info = {"nestdictmod_paths": MagicMock(), "nestdictmod": MagicMock()}

        assert self.collector.assemble_views(subdict, call_info) is None

    def test_assemble_views_normal_subdict(self):
        """
        If subdict is not an OrderedDictIterHelper, we create a view, store it,
        call subdict.set_view(vc), vc.set_model(subdict), etc.
        """
        # Make sure abspath is not None so _get_mypath_treewalker returns something
        call_info = {
            "nestdictmod_paths": MagicMock(abspath=["root", 123]),
            "nestdictmod": MagicMock(),
        }

        # subdict mocks
        mock_view_class = MagicMock(name="MockViewClass")
        mock_view_instance = MagicMock(name="MockViewInstance")
        mock_view_class.return_value = mock_view_instance

        subdict = MagicMock()
        subdict.get_view_class.return_value = mock_view_class

        result = self.collector.assemble_views(subdict, call_info)
        self.assertIsNone(result)

        # We expect the key in _views_by_path to be ("root", 123)
        self.assertIn(("root", 123), self.collector.get_views_by_path())
        self.assertIs(
            self.collector.get_views_by_path()[("root", 123)], mock_view_instance
        )
        # Check calls
        subdict.set_view.assert_called_once_with(mock_view_instance)
        mock_view_instance.set_model.assert_called_once_with(subdict)

    def test_skip_level_is_ordered_dict_iter_helper(self):
        """
        If myobject is an instance of OrderedDictIterHelper, _skip_level() returns True.
        We'll mock the class so we can test that logic easily.
        """
        helper_instance = OrderedDictIterHelper()
        self.assertTrue(self.collector._skip_level(helper_instance))
        self.assertFalse(self.collector._skip_level(MagicMock()))

    def test_assemble_views_parenter_skip_ordered_dict_iter_helper(self):
        """
        If subdict is an OrderedDictIterHelper, return None immediately.
        """
        with patch(
            "SimStackServer.WaNo.WaNoTreeWalker.OrderedDictIterHelper", create=True
        ) as mock_iter_helper:
            subdict = mock_iter_helper()
            call_info = {
                "nestdictmod_paths": MagicMock(abspath=["root"]),
                "nestdictmod": MagicMock(),
            }

            result = self.collector.assemble_views_parenter(subdict, call_info)
            self.assertIsNone(result)

    def test_assemble_views_parenter_normal(self):
        """
        If subdict is normal, we find the parent, skip levels if needed, then set vc's parent.
        """
        call_info = {
            "nestdictmod_paths": MagicMock(abspath=["root", "child"]),
            "nestdictmod": MagicMock(),
        }
        # subdict mock
        subdict = MagicMock()
        subdict.view = MagicMock(name="SubdictView")

        # We'll mock tw.resolve(...) to return a fake parent
        fake_parent = MagicMock()
        fake_parent.view = MagicMock(name="ParentView")
        call_info["nestdictmod"].resolve.side_effect = [fake_parent, fake_parent]

        self.collector.assemble_views_parenter(subdict, call_info)
        # We expect subdict.view.set_parent(fake_parent.view)
        subdict.view.set_parent.assert_called_once_with(fake_parent.view)

    def test_data_visitor_view_assembler_ordered_dict_iter_helper(self):
        """
        Return data immediately if it is an OrderedDictIterHelper.
        """
        data = OrderedDictIterHelper()
        call_info = {
            "nestdictmod_paths": MagicMock(abspath=["abc"]),
            "nestdictmod": MagicMock(),
        }
        result = self.collector.data_visitor_view_assembler(data, call_info)
        self.assertIs(result, data)
        self.assertEqual(self.collector.get_views_by_path(), {})

    def test_data_visitor_view_assembler_normal(self):
        """
        If data is normal, we create a view, store it, set_view, set_model, etc.
        """
        call_info = {
            "nestdictmod_paths": MagicMock(abspath=["abc"]),
            "nestdictmod": MagicMock(),
        }
        data = MagicMock()
        mock_view_class = MagicMock(name="MockViewClass")
        mock_view_instance = MagicMock(name="MockViewInstance")
        data.get_view_class.return_value = mock_view_class
        mock_view_class.return_value = mock_view_instance

        result = self.collector.data_visitor_view_assembler(data, call_info)
        self.assertIs(result, data)
        self.assertIn(("abc",), self.collector.get_views_by_path())
        self.assertIs(self.collector.get_views_by_path()[("abc",)], mock_view_instance)
        data.set_view.assert_called_once_with(mock_view_instance)
        mock_view_instance.set_model.assert_called_once_with(data)

    def test_data_visitor_view_parenter_ordered_dict_iter_helper(self):
        """If data is OrderedDictIterHelper, return it immediately."""
        with patch(
            "SimStackServer.WaNo.WaNoTreeWalker.OrderedDictIterHelper", create=True
        ) as mock_iter_helper:
            data = mock_iter_helper()
            call_info = {
                "nestdictmod_paths": MagicMock(abspath=["one"]),
                "nestdictmod": MagicMock(),
            }
            result = self.collector.data_visitor_view_parenter(data, call_info)
            self.assertIs(result, data)

    def test_data_visitor_view_parenter_normal(self):
        """
        If abspath is not empty, find the parent, skip levels if needed, then
        set the current data's view parent.
        """
        call_info = {
            "nestdictmod_paths": MagicMock(abspath=["root", "child"]),
            "nestdictmod": MagicMock(),
        }
        data = MagicMock()
        data.view = MagicMock(name="DataView")

        fake_parent = MagicMock()
        fake_parent.view = MagicMock(name="ParentView")
        call_info["nestdictmod"].resolve.side_effect = [fake_parent, fake_parent]

        result = self.collector.data_visitor_view_parenter(data, call_info)
        self.assertIs(result, data)
        data.view.set_parent.assert_called_once_with(fake_parent.view)

    def test_data_visitor_model_parenter_ordered_dict_iter_helper(self):
        """If data is OrderedDictIterHelper, return it."""
        with patch(
            "SimStackServer.WaNo.WaNoTreeWalker.OrderedDictIterHelper", create=True
        ) as mock_iter_helper:
            data = mock_iter_helper()
            call_info = {
                "nestdictmod_paths": MagicMock(abspath=["root"]),
                "nestdictmod": MagicMock(),
            }
            result = self.collector.data_visitor_model_parenter(data, call_info)
            self.assertIs(result, data)

    def test_data_visitor_model_parenter_normal(self):
        """
        If abspath is not empty, find the parent (skipping levels), then set data's parent.
        """
        call_info = {
            "nestdictmod_paths": MagicMock(abspath=["root", "child"]),
            "nestdictmod": MagicMock(),
        }
        data = MagicMock()
        fake_parent = MagicMock(name="Parent")
        call_info["nestdictmod"].resolve.side_effect = [fake_parent, fake_parent]

        result = self.collector.data_visitor_model_parenter(data, call_info)
        self.assertIs(result, data)
        data.set_parent.assert_called_once_with(fake_parent)

    def test_assemble_model_parenter_skip_ordereddictiterhelper(self):
        """Return None if subdict is an OrderedDictIterHelper."""
        with patch(
            "SimStackServer.WaNo.WaNoTreeWalker.OrderedDictIterHelper", create=True
        ) as mock_iter_helper:
            subdict = mock_iter_helper()
            call_info = {
                "nestdictmod_paths": MagicMock(abspath=["any"]),
                "nestdictmod": MagicMock(),
            }
            result = self.collector.assemble_model_parenter(subdict, call_info)
            self.assertIsNone(result)

    def test_assemble_model_parenter_normal(self):
        """
        If subdict is normal, find parent (skipping levels), then subdict.set_parent(parent).
        """
        call_info = {
            "nestdictmod_paths": MagicMock(abspath=["foo", "bar"]),
            "nestdictmod": MagicMock(),
        }
        subdict = MagicMock()
        fake_parent = MagicMock(name="Parent")
        call_info["nestdictmod"].resolve.side_effect = [fake_parent, fake_parent]

        result = self.collector.assemble_model_parenter(subdict, call_info)
        self.assertIsNone(result)
        subdict.set_parent.assert_called_once_with(fake_parent)


class TestWaNoTreeWalker(unittest.TestCase):
    def test_isdict(self):
        assert WaNoTreeWalker._isdict("test") is False
        mock_dict = MagicMock()
        mock_dict.dictlike = True
        assert WaNoTreeWalker._isdict(mock_dict) is True
        assert WaNoTreeWalker._isdict(WaNoModelDictLike()) is True

    def test_islist(self):
        assert WaNoTreeWalker._islist("test") is False
        mock_dict = MagicMock()
        mock_dict.listlike = True
        assert WaNoTreeWalker._islist(mock_dict) is True
        assert WaNoTreeWalker._islist(WaNoModelListLike()) is True


class TestWaNoTreeWalkerFileFunctions(unittest.TestCase):
    def test_subdict_skiplevel_none_found(self):
        """If subdict has no 'content' or 'TABS', return None immediately."""
        subdict = {"some_other_key": 42}
        call_info = {}
        result = subdict_skiplevel(subdict, call_info)
        self.assertIsNone(result)

    @patch("SimStackServer.WaNo.WaNoTreeWalker.NestDictMod")
    def test_subdict_skiplevel_content(self, mock_nestdictmod):
        """If subdict['content'] exists, we create a NestDictMod and call walker."""
        fake_content = {"a": 1}
        subdict = {"content": fake_content}
        call_info = {
            "path_visitor_function": MagicMock(name="pvf"),
            "subdict_visitor_function": MagicMock(name="svf"),
            "data_visitor_function": MagicMock(name="dvf"),
        }

        # Mock the NestDictMod instance & walker
        mock_tw_instance = MagicMock(name="MockNestDictModInstance")
        mock_nestdictmod.return_value = mock_tw_instance
        fake_walker_result = "walker_result"
        mock_tw_instance.walker.return_value = fake_walker_result

        result = subdict_skiplevel(subdict, call_info)

        # Check we used content in NestDictMod
        mock_nestdictmod.assert_called_once_with(fake_content)
        # Check walker was called with the right arguments
        mock_tw_instance.walker.assert_called_once_with(
            capture=True,
            path_visitor_function=call_info["path_visitor_function"],
            subdict_visitor_function=call_info["subdict_visitor_function"],
            data_visitor_function=call_info["data_visitor_function"],
        )
        self.assertEqual(result, fake_walker_result)

    @patch("SimStackServer.WaNo.WaNoTreeWalker.NestDictMod")
    def test_subdict_skiplevel_tabs(self, mock_nestdictmod):
        """If subdict['content'] is missing but subdict['TABS'] exists, use 'TABS'."""
        fake_tabs = {"something": "here"}
        subdict = {"TABS": fake_tabs}
        call_info = {
            "path_visitor_function": MagicMock(),
            "subdict_visitor_function": MagicMock(),
            "data_visitor_function": MagicMock(),
        }
        mock_tw_instance = MagicMock()
        mock_nestdictmod.return_value = mock_tw_instance
        mock_tw_instance.walker.return_value = "tabs_walker"

        result = subdict_skiplevel(subdict, call_info)
        self.assertEqual(result, "tabs_walker")
        mock_nestdictmod.assert_called_once_with(fake_tabs)

    def test_subdict_skiplevel_to_type_none_found(self):
        """Similar to subdict_skiplevel, but also checks no Type or known basetype."""
        subdict = {}
        call_info = {}
        result = subdict_skiplevel_to_type(subdict, call_info)
        self.assertIsNone(result)

    @patch("SimStackServer.WaNo.WaNoTreeWalker.NestDictMod")
    def test_subdict_skiplevel_to_type_content_basetype(self, mock_nestdictmod):
        """
        If 'Type' is one of the base types, we override newsubdict with subdict['Type'].
        For example, subdict['Type'] = 'String' => newsubdict = 'String' (the string itself).
        """
        subdict = {"content": {"a": 1}, "Type": "String"}
        call_info = {
            "path_visitor_function": MagicMock(),
            "subdict_visitor_function": MagicMock(),
            "data_visitor_function": MagicMock(),
        }

        mock_tw_instance = MagicMock()
        mock_nestdictmod.return_value = mock_tw_instance
        mock_tw_instance.walker.return_value = "typed_walker"

        result = subdict_skiplevel_to_type(subdict, call_info)
        # Because 'String' is in ["Int","Boolean","Float","String","File","FString"],
        # newsubdict = subdict["Type"] => 'String'
        mock_nestdictmod.assert_called_once_with("String")
        self.assertEqual(result, "typed_walker")

    @patch("SimStackServer.WaNo.WaNoTreeWalker.NestDictMod")
    def test_subdict_skiplevel_to_type_tabs_no_type_key(self, mock_nestdictmod):
        """If subdict doesn't contain 'Type' but has TABS, we use TABS for newsubdict."""
        fake_tabs = {"some_tabs": True}
        subdict = {"TABS": fake_tabs}
        call_info = {
            "path_visitor_function": MagicMock(),
            "subdict_visitor_function": MagicMock(),
            "data_visitor_function": MagicMock(),
        }

        mock_tw_instance = MagicMock()
        mock_nestdictmod.return_value = mock_tw_instance
        mock_tw_instance.walker.return_value = "tabs_result"

        result = subdict_skiplevel_to_type(subdict, call_info)
        self.assertEqual(result, "tabs_result")
        mock_nestdictmod.assert_called_once_with(fake_tabs)

    def test_subdict_skiplevel_path_version(self):
        """Test the simple string replacement logic."""
        # e.g. if inpath starts with "TABS.", we remove that

        self.assertEqual(
            subdict_skiplevel_path_version("TABS.root.child"), "root.child"
        )

        self.assertEqual(
            subdict_skiplevel_path_version("root.content.child"), "rootchild"
        )
        # If both appear
        self.assertEqual(
            subdict_skiplevel_path_version("TABS.root.content.child"), "rootchild"
        )
        # If neither appear
        self.assertEqual(
            subdict_skiplevel_path_version("something.else"), "something.else"
        )

    @patch("SimStackServer.WaNo.WaNoTreeWalker.NestDictMod")
    @patch("SimStackServer.WaNo.WaNoTreeWalker.orm", create=True)
    def test_subdict_skiplevel_to_aiida_type_none_found(
        self, mock_orm, mock_nestdictmod
    ):
        """If we find neither 'content' nor 'TABS' nor do we match a known Type => return None."""
        subdict = {}
        call_info = {}
        aiida_files_by_relpath = {}
        result = subdict_skiplevel_to_aiida_type(
            subdict, call_info, aiida_files_by_relpath
        )
        self.assertIsNone(result)
        mock_nestdictmod.assert_not_called()

    @patch("SimStackServer.WaNo.WaNoTreeWalker.NestDictMod")
    def test_subdict_skiplevel_to_aiida_type_basetype_nonfile(self, mock_nestdictmod):
        """
        If 'Type' is in the known basetypes but not 'File', we create an ORM object from
        subdict['content'] and pass it to NestDictMod.
        """
        # Mock out the AiiDA classes we expect
        mock_orm = MagicMock()
        mock_orm.Float = MagicMock(name="AiiDAFloat")
        mock_orm.Bool = MagicMock(name="AiiDABool")
        mock_orm.Str = MagicMock(name="AiiDAStr")
        mock_orm.Int = MagicMock(name="AiiDAInt")
        mock_orm.SinglefileData = MagicMock(name="AiiDASinglefileData")

        subdict = {"Type": "Float", "content": 3.14}
        call_info = {
            "path_visitor_function": MagicMock(),
            "subdict_visitor_function": MagicMock(),
            "data_visitor_function": MagicMock(),
        }
        aiida_files_by_relpath = {}

        mock_tw_instance = MagicMock()
        mock_nestdictmod.return_value = mock_tw_instance
        mock_tw_instance.walker.return_value = "aiida_walker_result"

        mock_aiida = MagicMock(name="mock_aiida")
        mock_aiida.orm = mock_orm

        with patch.dict(sys.modules, {"aiida": mock_aiida}):
            result = subdict_skiplevel_to_aiida_type(
                subdict, call_info, aiida_files_by_relpath
            )

        # We expect to have called Float(3.14)
        mock_orm.Float.assert_called_once_with(3.14)
        # That becomes newsubdict
        mock_nestdictmod.assert_called_once_with(mock_orm.Float.return_value)
        self.assertEqual(result, "aiida_walker_result")

    @patch("SimStackServer.WaNo.WaNoTreeWalker.NestDictMod")
    def test_subdict_skiplevel_to_aiida_type_file(self, mock_nestdictmod):
        """If 'Type' == 'File', we use SinglefileData & look up the object in aiida_files_by_relpath."""
        # Mock SinglefileData
        mock_orm = MagicMock()
        mock_orm.SinglefileData = MagicMock(name="AiiDASinglefileData")

        subdict = {"Type": "File", "logical_name": "example.txt"}
        call_info = {
            "path_visitor_function": MagicMock(),
            "subdict_visitor_function": MagicMock(),
            "data_visitor_function": MagicMock(),
        }
        # Suppose we have a pre-stored file object in the dictionary
        file_mock = MagicMock(name="ExampleFileObj")
        aiida_files_by_relpath = {"example.txt": file_mock}

        mock_tw_instance = MagicMock()
        mock_nestdictmod.return_value = mock_tw_instance
        mock_tw_instance.walker.return_value = "file_walker_result"

        mock_aiida = MagicMock(name="mock_aiida")
        mock_aiida.orm = mock_orm

        with patch.dict(sys.modules, {"aiida": mock_aiida}):
            result = subdict_skiplevel_to_aiida_type(
                subdict, call_info, aiida_files_by_relpath
            )

        # Because Type == 'File', we pick up the object from aiida_files_by_relpath
        # instead of calling SinglefileData(...) with subdict["content"].
        mock_orm.SinglefileData.assert_not_called()  # We skip creation, use existing file obj
        mock_nestdictmod.assert_called_once_with(file_mock)
        self.assertEqual(result, "file_walker_result")
