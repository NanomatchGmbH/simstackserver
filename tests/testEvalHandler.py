import unittest


from SimStackServer.EvalHandler import eval_numpyexpression


class TestEvalHandler(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_eval_handler(self):
        b = 4
        for a in eval_numpyexpression("np.arange(4,7)"):
            assert a == b
            b += 1
        assert b == 7
