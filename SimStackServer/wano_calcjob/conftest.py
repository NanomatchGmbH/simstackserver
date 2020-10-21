"""pytest fixtures for simplified testing."""
from __future__ import absolute_import
import pytest
pytest_plugins = ['aiida.manage.tests.pytest_fixtures']


@pytest.fixture(scope='function', autouse=True)
def clear_database_auto(clear_database):  # pylint: disable=unused-argument
    """Automatically clear database in between tests."""


@pytest.fixture(scope='function')
def wano_code(aiida_local_code_factory):
    """Get a wano code.
    """
    # Tomorrow:
    # 1.) Think of something here. The good news: There is something like a local code factory
    # 2.) Write the output parser by parsing the output dict things
    # 3.) Assemble the expected files and write them back according to the output spec - maybe we need to query them according
    #     to the WaNo, if not done yet.
    # 4.)


    wano_code = aiida_local_code_factory(executable='diff', entry_point='wano')
    return wano_code
