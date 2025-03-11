from SimStackServer.EvalHandler import eval_numpyexpression  # adjust the import path accordingly

def test_eval_numpyexpression_array():
    result = eval_numpyexpression("4+2")
    assert result == 6