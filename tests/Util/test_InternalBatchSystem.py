import os
import sys
from unittest.mock import patch

from SimStackServer.Util.InternalBatchSystem import InternalBatchSystem

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


class TestInternalBatchSystem:
    def setup_method(self):
        InternalBatchSystem._processfarm = None
        InternalBatchSystem._processfarm_thread = None

    def test_init(self):
        batch_system = InternalBatchSystem()
        assert batch_system.__dict__ == {}
        assert InternalBatchSystem._processfarm is None
        assert InternalBatchSystem._processfarm_thread is None

        dummy_thread = "dummy_thread"
        dummy_processfarm = "dummy_processfarm"

        InternalBatchSystem._processfarm = None
        InternalBatchSystem._processfarm_thread = None

        with patch(
            "threadfarm.processfarm.ProcessFarm.start_processfarm_as_thread",
            return_value=(dummy_thread, dummy_processfarm),
        ):
            pf, pf_thread = InternalBatchSystem.get_instance()
            assert pf_thread == dummy_thread
            assert pf == dummy_processfarm
