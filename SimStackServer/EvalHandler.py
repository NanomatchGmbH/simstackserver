
def eval_numpyexpression(expression):
    """
    Allows eval with numpy imports. Simply guarantees that numpy will always be imported
    e
    :return:
    """
    import numpy as np
    return eval(expression)