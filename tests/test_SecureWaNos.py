import logging
import os
import pathlib
import tempfile
import shutil
from unittest.mock import patch, MagicMock

import pytest

from SimStackServer.SecureWaNos import SecureModeGlobal, SecureWaNos
from SimStackServer.Util.Exceptions import SecurityError


class TestSecureModeGlobal:
    def setup_method(self):
        # Reset secure mode for each test
        SecureModeGlobal._secure_mode = False

    def test_secure_mode_default(self):
        # Test default secure mode is False
        assert SecureModeGlobal.get_secure_mode() is False

    def test_set_secure_mode(self):
        # Test setting secure mode
        SecureModeGlobal.set_secure_mode()
        assert SecureModeGlobal.get_secure_mode() is True


class TestSecureWaNos:
    @pytest.fixture
    def tmpdir(self) -> tempfile.TemporaryDirectory:
        with tempfile.TemporaryDirectory() as mydir:
            yield mydir

    @pytest.fixture
    def tmppath(self, tmpdir):
        yield pathlib.Path(tmpdir)

    def setup_method(self):
        # Reset singleton state
        SecureWaNos._instance = None

        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()

        # Create a mock WaNo file
        self.setup_test_wanos()

    def teardown_method(self):
        # Clean up the temporary directory
        shutil.rmtree(self.test_dir)

    def setup_test_wanos(self):
        # Create a test WaNo XML file
        wano_xml = """<?xml version="1.0" encoding="UTF-8"?>
<WaNoTemplate>
    <WaNoMeta>
        <WaNoName>TestWaNo</WaNoName>
        <WaNoVersion>1.0</WaNoVersion>
        <WaNoDescription>Test WaNo for unit tests</WaNoDescription>
    </WaNoMeta>
    <WaNoRoot>
        <WaNoFloat name="testFloat" description="Test float parameter">1.0</WaNoFloat>
    </WaNoRoot>
</WaNoTemplate>
"""

        # Create test WaNo directory
        test_wano_dir = os.path.join(self.test_dir, "TestWaNo")
        os.makedirs(test_wano_dir, exist_ok=True)

        # Create test WaNo file
        with open(os.path.join(test_wano_dir, "TestWaNo.xml"), "w") as f:
            f.write(wano_xml)

    def test_singleton_pattern(self, tmpdir, capsys, caplog):
        # Test that instances are the same
        # with patch("SimStackServer.SecureWaNos.Config") as mock_config:
        with pytest.raises(SecurityError):
            instance1 = SecureWaNos.get_instance()
            assert isinstance(instance1, SecureWaNos)
        mock_appdirs = MagicMock()
        mock_appdirs.user_config_dir = tmpdir

        newpath = pathlib.Path(tmpdir) / "secure_wanos"
        os.mkdir(newpath)
        subpath = pathlib.Path(tmpdir) / "secure_wanos" / "sub_path"
        os.mkdir(subpath)

        mock_root = MagicMock()
        with patch(
            "SimStackServer.SimStackServerMain.SimStackServer.get_appdirs"
        ) as mock_SSS, patch(
            "SimStackServer.SecureWaNos.WaNoListEntry_from_folder_or_zip",
            return_value="tada",
        ), patch(
            "SimStackServer.SecureWaNos.wano_constructor",
            return_value=(mock_root, None),
        ):
            mock_SSS.return_value = mock_appdirs

            with caplog.at_level(logging.INFO):
                instance2 = SecureWaNos.get_instance()
                assert isinstance(instance2, SecureWaNos)
            assert "Parsing secure" in caplog.text
