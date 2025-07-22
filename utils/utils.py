import sys

def get_exc_line():
    _, _, exc_tb = sys.exc_info()
    return exc_tb.tb_lineno