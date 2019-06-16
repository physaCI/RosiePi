 # The MIT License (MIT)
 #
 # Copyright (c) 2019 Michael Schroeder
 #
 # Permission is hereby granted, free of charge, to any person obtaining a copy
 # of this software and associated documentation files (the "Software"), to deal
 # in the Software without restriction, including without limitation the rights
 # to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 # copies of the Software, and to permit persons to whom the Software is
 # furnished to do so, subject to the following conditions:
 #
 # The above copyright notice and this permission notice shall be included in
 # all copies or substantial portions of the Software.
 #
 # THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 # IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 # FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 # AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 # LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 # OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 # THE SOFTWARE.
 #

import argparse
import datetime
import inspect
import os
import pkg_resources
import re
import sys

import importlib
pyboard = importlib.import_module(".circuitpython.tests.pyboard",
                                  package="rosiepi")

from . import cirpy_actions

cli_parser = argparse.ArgumentParser(description="rosiepi Test Controller")
cli_parser.add_argument(
    "board",
    help="Name of the board to run test(s) on."
)
cli_parser.add_argument(
    "build_ref",
    default=None,
    help="Tag or commit to build CircuitPython from."
)


def cp_tests_dir():
    return pkg_resources.resource_filename("rosiepi", "circuitpython/tests")


def parse_test_interactions(test_file):
    """ Method to parse a test file, and return the necessary
        interaction information.

    :param: str test_file: Path to the file to parse.

    Test interactions are annotated as comments in the test file.
    Interaction markups should be placed one line above the expected
    interaction, and must consist of only a single line. The current
    available markups are as follows:
        - `#$ input=`: Denotes that the next line requires an input
                       to the REPL.
        - `#$ output=`: Denotes what the next line's output in the
                        REPL should be.
        - `#$ verify=`: Denotes a function that exists inside RosiePi
                        to use for verification. The function should
                        be prefixed with the module that contains it.

    For example:
    ... code: python

        #$ input=4
        result = input()

        #$ output=4
        print(result)

        with digitalio.DigitalInOut(board.D0) as mypin:
            #$ verify=pin_tests.assert_pin_high
            mypin.switch_to_output(value=True)
            #$ input=\r\n
            input() # only proceed if previous verify passed
    """
    has_action = re.compile(r"^\#\$\s(input|output|verify)\=(.+$)")
    interactions = {}
    with open(test_file, 'r') as file:
        for line_no, line in enumerate(file.readlines(), start=1):
            check_line = has_action.match(line)
            if check_line:
                # interaction key should be the line after the marker
                # so add 1 to the current line number
                interactions[(line_no + 1)] = {"action": check_line.group(1),
                                         "value": check_line.group(2)}
            else:
                if line.startswith("#$"):
                    exc_msg = [
                        "Improper interaction syntax on",
                        "line {0} in '{1}'".format(line_no, test_file)
                    ]
                    raise SyntaxWarning(" ".join(exc_msg))
    #print(interactions)
    return interactions


class TestObject():
    """ Container to hold test information.

    :param: str test_file: Path to the test file
    """

    def __init__(self, test_file):
        if not os.path.exists(test_file):
            raise FileNotFoundError("'{}' was not found.".format(test_file))
        path_split = os.path.split(test_file)
        self.test_dir = path_split[0]
        self.test_file = path_split[1]
        self.interactions = parse_test_interactions(test_file)
        self.repl_session = ""

def exec_line(board, command, input=False, echo=True):
    if not isinstance(board, pyboard.CPboard):
        raise ValueError("'board' argument must be of 'pyboard.CPBoard' type.")
    tail_char = b"\x04"
    if input:
        tail_char = b"\r\n"
    board.repl.write(command)
    board.repl.write(tail_char)
    if not input:
        board.repl.read_until(b"OK")
        if echo:
            output = board.repl.read_until(b"\x04")
            output = output[:-1]

            error = board.repl.read_until(b"\x04")
            error = error[:-1]
            if error:
                raise BaseException(error)
            return output
    else:
        board.repl.read_until(bytes(command, encoding="utf8"))

class TestController():
    """ Main class to handle testing operations.

    :param: board: The name of the board to run tests on. Must match
                   an available board in `circuitpython/tools/cpboard.py`.
    :param: build_ref: A reference to the tag/commit to test. This will
                       usually be generated by the GitHub Checks API.
    """
    def __init__(self, board, build_ref):
        self.run_date = datetime.datetime.now().strftime("%d-%b-%Y,%H:%M:%S%Z")
        init_msg = [
            "="*25 + " RosiePi " + "="*26,
            "Initiating rosiepi...",
            "-"*60,
            " - Date/Time: {}".format(self.run_date),
            " - Test commit: {}".format(build_ref),
            " - Test board: {}".format(board),
            "="*60,
            "Connecting to: {}".format(board),
            "-"*60
        ]
        print("\n".join(init_msg))

        self.build_ref = build_ref
        try:
            self.board = pyboard.CPboard.from_try_all(board)
        except RuntimeError as conn_err:
            err_msg = [
                "Failed to connect to: {}".format(board),
                conn_err.args[0],
                "="*60,
                "Closing RosiePi"
            ]
            raise RuntimeError("\n".join(err_msg)) from None
        init_msg = [
            "Connected!",
            "Board info:",
            " - Serial Number: {}".format(self.board.serial_number),
            " - Disk Drive: {}".format(self.board.disk.path),
            "="*60,
        ]
        print("\n".join(init_msg))

        print("Preparing Firmware...")
        print("-"*60)
        self.fw_build_dir = cirpy_actions.build_fw(board, build_ref)
        print("="*60)

        print("Updating Firmware on: {}".format(board))
        cirpy_actions.update_fw(self.board, os.path.join(self.fw_build_dir,
                                                         "firmware.uf2"))
        print("="*60)

        #print(self.board.firmware.info)

        print("Gathering tests to run...")
        self.tests = self.gather_tests()
        init_msg = [
            "These following tests will be run:",
            " - " + ", ".join([test.test_file for test in self.tests]),
            "="*60,
        ]
        print("\n".join(init_msg))

        self.run_tests()
        print("="*60)

    def gather_tests(self):
        """ Gathers all tests in `circuitpython/tests/circuitpython/rosie_tests`
            and returns a list of `TestObject`s.
        """
        rosie_tests_dir = os.path.join(cp_tests_dir(),
                                       "circuitpython",
                                       "rosie_tests")
        test_files = []
        for test in os.scandir(rosie_tests_dir):
            # TODO: implement exclusions by board
            if test.path.endswith(".py"):
                test_files.append(TestObject(test.path))

        return test_files


    def run_tests(self):
        """ Runs the tests in self.tests.
        """
        total_tests = len(self.tests)
        tests_run = 0
        tests_passed = 0
        tests_failed = 0
        this_test_passed = True
        with self.board as board:
            board.repl.session = b""
            for test in self.tests:
                # we likely had a REPL reset, so make sure we're
                # past the "press any key" prompt.
                board.repl.execute(b"\x01", async=True)
                this_test_passed = True
                print("Starting test: {}".format(test.test_file))
                test_file_path = os.path.join(test.test_dir, test.test_file)
                test_cmds = []
                with open(test_file_path, 'r') as current_test:
                    test_cmds = current_test.readlines()
                for line_no, line in enumerate(test_cmds, start=1):
                    if line == "\n":
                        continue
                    print("running line: ({}) {}".format(line_no, line.rstrip("\n")))
                    try:
                        if line_no in test.interactions:
                            action = test.interactions[line_no]["action"]
                            value = test.interactions[line_no]["value"]
                            #print("ACTION: {}; VALUE: {}".format(action, value))
                            if action == "output":
                                print("- Testing for output of: {}".format(value))
                                try:
                                    result = exec_line(board, line)
                                except Exception as exc:
                                    raise pyboard.CPboardError(exc) from Exception

                                result = str(result,
                                             encoding="utf-8").rstrip("\r\n")
                                if result != value:
                                    this_test_passed = False
                                print(" - Passed!")
                            elif action == "input":
                                print("- Sending input: {}".format(value))
                                try:
                                    exec_line(board, line, echo=False)
                                    exec_line(board, value, input=True)
                                except Exception as exc:
                                    raise pyboard.CPboardError(exc) from Exception
                            elif action == "verify":
                                print("- Verifying with: {}".format(value))
                                try:
                                    # import the referenced module
                                    module_name, func_name = value.split(".")
                                    imprt_stmt = [".verifiers.", module_name]
                                    verifier = importlib.import_module(
                                        "".join(imprt_stmt),
                                        package="rosiepi.rosie"
                                    )
                                    # now get the function object using inspect
                                    # so that we can dynamically run it.
                                    ver_func = [
                                        func[1] for func in
                                        inspect.getmembers(verifier)
                                        if func[0] == func_name
                                    ][0]
                                    #print(ver_func)
                                    exec_line(board, line)
                                    result = ver_func(board)
                                    if not result:
                                        raise pyboard.CPboardError(
                                            "'{}' test failed.".format(value)
                                        )
                                except Exception as exc:
                                    raise pyboard.CPboardError(exc) from Exception
                                print(" - Passed!")
                        else:
                            board.repl.execute(line)
                    except pyboard.CPboardError as line_err:
                        this_test_passed = False
                        err_args = [str(arg) for arg in line_err.args]
                        err_msg = [
                            "Test Failed!",
                            " - Last code executed: '{}'".format(line.strip("\n")),
                            " - Line: {}".format(line_no),
                            " - Exception: {}".format("".join(err_args)),
                        ]
                        print("\n".join(err_msg))
                        break
                    #finally:
                    #    print(board.repl.session)
                    if this_test_passed != True:
                        break

                if this_test_passed:
                    tests_passed += 1
                else:
                    tests_failed += 1
                tests_run += 1
                test.repl_session = board.repl.session
                print(board.repl.session)
                print("-"*60)
                board.repl.reset()

        end_msg = [
            "Ran {run} of {total} tests.".format(run=tests_run, total=total_tests),
            " - Passed: {}".format(tests_passed),
            " - Failed: {}".format(tests_failed)
        ]
        print("\n".join(end_msg))

def main():
    cli_args = cli_parser.parse_args()
    #cirpy_actions.check_local_clone()
    tc = TestController(cli_args.board, cli_args.build_ref)
