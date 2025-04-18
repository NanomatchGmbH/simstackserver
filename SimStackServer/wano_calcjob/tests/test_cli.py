""" Tests for command line interface.

"""
from aiida.manage.tests.unittest_classes import PluginTestCase


class TestDataCli(PluginTestCase):
    """Test verdi data cli plugin."""

    def setUp(self):
        from click.testing import CliRunner
        from aiida.plugins import DataFactory

        DiffParameters = DataFactory("wano")
        self.parameters = DiffParameters({"ignore-case": True})
        self.parameters.store()
        self.runner = CliRunner()

    def test_data_diff_list(self):
        """Test 'verdi data wano list'

        Tests that it can be reached and that it lists the node we have set up.
        """
        from wano_calcjob.cli import list_

        result = self.runner.invoke(list_, catch_exceptions=False)
        self.assertIn(str(self.parameters.pk), result.output)

    def test_data_diff_export(self):
        """Test 'verdi data wano export'

        Tests that it can be reached and that it shows the contents of the node
        we have set up.
        """
        from wano_calcjob.cli import export

        result = self.runner.invoke(
            export, [str(self.parameters.pk)], catch_exceptions=False
        )
        self.assertIn("ignore-case", result.output)
