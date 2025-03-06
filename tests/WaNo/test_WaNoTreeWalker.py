import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from SimStackServer.WaNo.WaNoTreeWalker import (
    PathCollector,
    WaNoTreeWalker,
    ViewCollector
)


class TestPathCollector:
    
    def test_collect_empty(self):
        # Test collecting from empty data
        collector = PathCollector()
        result = collector.collect({})
        
        # Should return empty list
        assert result == []
    
    def test_collect_simple_dict(self):
        # Test collecting from simple dictionary
        collector = PathCollector()
        data = {
            "key1": "value1",
            "key2": 123,
            "key3": True
        }
        
        result = collector.collect(data)
        
        # Should return paths with values
        assert len(result) == 3
        assert ("key1", "value1") in result
        assert ("key2", 123) in result
        assert ("key3", True) in result
    
    def test_collect_nested_dict(self):
        # Test collecting from nested dictionary
        collector = PathCollector()
        data = {
            "key1": "value1",
            "nested": {
                "key2": "value2",
                "key3": 123
            }
        }
        
        result = collector.collect(data)
        
        # Should return paths with values
        assert len(result) == 3
        assert ("key1", "value1") in result
        assert ("nested/key2", "value2") in result
        assert ("nested/key3", 123) in result
    
    def test_collect_with_lists(self):
        # Test collecting from data with lists
        collector = PathCollector()
        data = {
            "key1": "value1",
            "list": [
                {"item1": "value2"},
                {"item2": "value3"}
            ]
        }
        
        result = collector.collect(data)
        
        # Should return paths with values including list indices
        assert len(result) == 3
        assert ("key1", "value1") in result
        assert ("list/0/item1", "value2") in result
        assert ("list/1/item2", "value3") in result
    
    def test_assemble_path(self):
        # Test path assembly
        collector = PathCollector()
        
        # Test empty path
        assert collector.assemble_path([]) == ""
        
        # Test simple path
        assert collector.assemble_path(["key"]) == "key"
        
        # Test nested path
        assert collector.assemble_path(["parent", "child"]) == "parent/child"
        
        # Test path with integer (list index)
        assert collector.assemble_path(["list", 0, "item"]) == "list/0/item"


class TestWaNoTreeWalker:
    
    def test_isdict(self):
        # Test _isdict static method
        assert WaNoTreeWalker._isdict({}) is True
        assert WaNoTreeWalker._isdict({"key": "value"}) is True
        assert WaNoTreeWalker._isdict([]) is False
        assert WaNoTreeWalker._isdict("string") is False
        assert WaNoTreeWalker._isdict(123) is False
    
    def test_islist(self):
        # Test _islist static method
        assert WaNoTreeWalker._islist([]) is True
        assert WaNoTreeWalker._islist([1, 2, 3]) is True
        assert WaNoTreeWalker._islist({}) is False
        assert WaNoTreeWalker._islist("string") is False
        assert WaNoTreeWalker._islist(123) is False
    
    def test_walk_simple_dict(self):
        # Test walking a simple dictionary
        data = {
            "key1": "value1",
            "key2": "value2"
        }
        
        # Create a mock callback function
        mock_callback = MagicMock()
        
        # Walk the data
        walker = WaNoTreeWalker()
        walker.walk(data, mock_callback)
        
        # Verify callback was called for each entry
        assert mock_callback.call_count == 2
        mock_callback.assert_any_call("key1", "value1", ["key1"])
        mock_callback.assert_any_call("key2", "value2", ["key2"])
    
    def test_walk_nested_dict(self):
        # Test walking a nested dictionary
        data = {
            "key1": "value1",
            "nested": {
                "key2": "value2"
            }
        }
        
        # Create a mock callback function
        mock_callback = MagicMock()
        
        # Walk the data
        walker = WaNoTreeWalker()
        walker.walk(data, mock_callback)
        
        # Verify callback was called for each entry
        assert mock_callback.call_count == 2
        mock_callback.assert_any_call("key1", "value1", ["key1"])
        mock_callback.assert_any_call("key2", "value2", ["nested", "key2"])
    
    def test_walk_with_lists(self):
        # Test walking data with lists
        data = {
            "key1": "value1",
            "list": [
                {"item1": "value2"},
                {"item2": "value3"}
            ]
        }
        
        # Create a mock callback function
        mock_callback = MagicMock()
        
        # Walk the data
        walker = WaNoTreeWalker()
        walker.walk(data, mock_callback)
        
        # Verify callback was called for each entry
        assert mock_callback.call_count == 3
        mock_callback.assert_any_call("key1", "value1", ["key1"])
        mock_callback.assert_any_call("item1", "value2", ["list", 0, "item1"])
        mock_callback.assert_any_call("item2", "value3", ["list", 1, "item2"])


class TestViewCollector:
    
    def test_init(self):
        # Test initialization
        collector = ViewCollector()
        
        # Initial attributes should be empty
        assert collector.views == {}
        assert collector.root is None
    
    def test_set_root(self):
        # Test setting root view
        collector = ViewCollector()
        mock_root = MagicMock()
        
        collector.set_root(mock_root)
        
        # Root should be set
        assert collector.root == mock_root
    
    def test_add_view(self):
        # Test adding a view
        collector = ViewCollector()
        mock_view = MagicMock()
        path = "test/path"
        
        collector.add_view(path, mock_view)
        
        # View should be added to views dictionary
        assert collector.views[path] == mock_view
    
    def test_set_parent_with_root(self):
        # Test setting parent for a view when root exists
        collector = ViewCollector()
        
        # Create mock views
        mock_root = MagicMock()
        mock_child = MagicMock()
        
        # Set root and add child view
        collector.set_root(mock_root)
        collector.add_view("parent/child", mock_child)
        
        # Set parent for child view
        collector.set_parent()
        
        # Child should be added to root's layout
        mock_child.setParent.assert_called_once_with(mock_root)
    
    def test_set_parent_with_nested_paths(self):
        # Test setting parent with nested paths
        collector = ViewCollector()
        
        # Create mock views
        mock_root = MagicMock()
        mock_parent = MagicMock()
        mock_child = MagicMock()
        
        # Set root and add views
        collector.set_root(mock_root)
        collector.add_view("parent", mock_parent)
        collector.add_view("parent/child", mock_child)
        
        # Set parent for all views
        collector.set_parent()
        
        # Parent should be added to root's layout
        mock_parent.setParent.assert_called_once_with(mock_root)
        
        # Child should be added to parent's layout
        mock_child.setParent.assert_called_once_with(mock_parent)