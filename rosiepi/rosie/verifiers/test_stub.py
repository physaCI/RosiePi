# test stub for import machinery with 'test_controller'

from .. import test_controller as tc

def foo(board):
    """ lets see if we can get this to interact with the
        board.
    """

    result = str(tc.exec_line(board, "print(dir(board))"), encoding="utf-8")
    #print("result:", result)
    result_list = result.strip("\r\n[]").split(", ")
    #print(result_list)
    d_pins = [pin.strip("'") for pin in result_list if pin.startswith("'D")]
    #print("D pins:", d_pins)

    cmd = "import digitalio"
    tc.exec_line(board, cmd, echo=False)
    test_passed = True
    for pin_no in d_pins:
        var_name = "{}_pin".format(pin_no)
        cmd = "{} = digitalio.DigitalInOut(board.{})".format(var_name, pin_no)
        tc.exec_line(board, cmd, echo=False)
        pin_dir = tc.exec_line(board, "print({}.direction)".format(var_name))
        #print("pin: {} - direction: {}".format(pin_no, pin_dir))
        # should be 'digitalio.Direction.INPUT'
        match = "digitalio.Direction.INPUT"
        if str(pin_dir, encoding="utf8").rstrip("\r\n") != match:
            test_passed = False
            break

    return test_passed

def bar():
    pass
