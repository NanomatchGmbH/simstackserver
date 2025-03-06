import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from SimStackServer.WaNo.WaNoFactory import (
    get_model_class,
    get_qt_view_class,
    wano_constructor,
    wano_constructor_helper,
    wano_without_view_constructor_helper
)


class TestWaNoFactory:
    
    def test_get_model_class(self):
        # Test getting models for different WaNo types
        int_model = get_model_class("int")
        assert int_model.__name__ == "WaNoInt"
        
        float_model = get_model_class("float")
        assert float_model.__name__ == "WaNoFloat"
        
        string_model = get_model_class("string")
        assert string_model.__name__ == "WaNoString"
    
    def test_get_model_class_invalid_type(self):
        # Test error handling for invalid WaNo type
        with pytest.raises(KeyError):
            get_model_class("nonexistent_type")
    
    @patch('importlib.import_module')
    def test_get_qt_view_class(self, mock_import):
        # Setup mock for import_module
        mock_module = MagicMock()
        mock_module.WaNoIntView = MagicMock()
        mock_import.return_value = mock_module
        
        # Test getting view class
        view_class = get_qt_view_class("int")
        
        # Verify correct module was imported and class returned
        mock_import.assert_called_once_with("SimStackServer.WaNo.view.WaNoIntView")
        assert view_class == mock_module.WaNoIntView
    
    @patch('importlib.import_module')
    def test_get_qt_view_class_fallback(self, mock_import):
        # Setup mock for import_module to fail first time
        mock_import.side_effect = [ImportError, MagicMock()]
        
        # Test getting view class with fallback
        with pytest.raises(ImportError):
            get_qt_view_class("customtype")
        
        # Verify both import attempts were made
        assert mock_import.call_count == 2
    
    @patch('SimStackServer.WaNo.WaNoFactory.get_model_class')
    @patch('SimStackServer.WaNo.WaNoFactory.get_qt_view_class')
    def test_wano_constructor_with_view(self, mock_get_view, mock_get_model):
        # Setup mocks
        mock_model_class = MagicMock()
        mock_model_instance = MagicMock()
        mock_model_class.return_value = mock_model_instance
        mock_get_model.return_value = mock_model_class
        
        mock_view_class = MagicMock()
        mock_view_instance = MagicMock()
        mock_view_class.return_value = mock_view_instance
        mock_get_view.return_value = mock_view_class
        
        # Test constructor with view
        model, view = wano_constructor("int", "test_name", "test_desc", model_only=False)
        
        # Verify correct classes were retrieved and instantiated
        mock_get_model.assert_called_once_with("int")
        mock_get_view.assert_called_once_with("int")
        assert model == mock_model_instance
        assert view == mock_view_instance
    
    @patch('SimStackServer.WaNo.WaNoFactory.get_model_class')
    @patch('SimStackServer.WaNo.WaNoFactory.get_qt_view_class')
    def test_wano_constructor_model_only(self, mock_get_view, mock_get_model):
        # Setup mocks
        mock_model_class = MagicMock()
        mock_model_instance = MagicMock()
        mock_model_class.return_value = mock_model_instance
        mock_get_model.return_value = mock_model_class
        
        # Test constructor with model only
        model, view = wano_constructor("int", "test_name", "test_desc", model_only=True)
        
        # Verify only model class was retrieved
        mock_get_model.assert_called_once_with("int")
        mock_get_view.assert_not_called()
        assert model == mock_model_instance
        assert view is None
    
    @patch('SimStackServer.WaNo.WaNoFactory.get_model_class')
    @patch('SimStackServer.WaNo.WaNoFactory.get_qt_view_class')
    def test_wano_constructor_helper(self, mock_get_view, mock_get_model):
        # Setup mocks
        mock_model_class = MagicMock()
        mock_model_instance = MagicMock()
        mock_model_class.return_value = mock_model_instance
        mock_get_model.return_value = mock_model_class
        
        mock_view_class = MagicMock()
        mock_view_instance = MagicMock()
        mock_view_class.return_value = mock_view_instance
        mock_get_view.return_value = mock_view_class
        
        # Test constructor helper
        model, view = wano_constructor_helper("int", "test_name", "test_desc", None, None)
        
        # Verify correct classes were retrieved and instantiated
        mock_get_model.assert_called_once_with("int")
        mock_get_view.assert_called_once_with("int")
        assert model == mock_model_instance
        assert view == mock_view_instance
    
    @patch('SimStackServer.WaNo.WaNoFactory.get_model_class')
    def test_wano_without_view_constructor_helper(self, mock_get_model):
        # Setup mocks
        mock_model_class = MagicMock()
        mock_model_instance = MagicMock()
        mock_model_class.return_value = mock_model_instance
        mock_get_model.return_value = mock_model_class
        
        # Test constructor helper without view
        model = wano_without_view_constructor_helper("int", "test_name", "test_desc", None)
        
        # Verify only model class was retrieved
        mock_get_model.assert_called_once_with("int")
        assert model == mock_model_instance