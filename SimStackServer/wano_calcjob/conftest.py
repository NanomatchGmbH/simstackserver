"""pytest fixtures for simplified testing."""
import pytest

pytest_plugins = ["aiida.manage.tests.pytest_fixtures"]


@pytest.fixture(scope="function", autouse=True)
def clear_database_auto(clear_database):  # pylint: disable=unused-argument
    """Automatically clear database in between tests."""


@pytest.fixture(scope="function")
def wano_code(aiida_local_code_factory):
    """Get a wano code."""
    # Tomorrow:
    # 1.) Think of something here. The good news: There is something like a local code factory
    # 2.) Write the output parser by parsing the output dict things
    # 3.) Assemble the expected files and write them back according to the output spec - maybe we need to query them according
    #     to the WaNo, if not done yet.
    # 4.)

    wano_code = aiida_local_code_factory(
        executable="wano-deptest-exec", entry_point="wano"
    )
    return wano_code


@pytest.fixture(scope="session")
def generate_parser():
    """Fixture to load a parser class for testing parsers."""

    def _generate_parser(entry_point_name):
        """Fixture to load a parser class for testing parsers.
        :param entry_point_name: entry point name of the parser class
        :return: the `Parser` sub class
        """
        from aiida.plugins import ParserFactory

        return ParserFactory(entry_point_name)

    return _generate_parser
