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
from io import StringIO
import os
import pkg_resources
import re
import sys

import importlib
#pyboard = importlib.import_module(".circuitpython.tests.pyboard",
#                                  package="rosiepi")

from tests import pyboard

from rosiepi.rosie import find_circuitpython
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
    return os.path.join(find_circuitpython(), "tests")


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
                        f"line {line_no} in '{test_file}'",
                    ]
                    raise SyntaxWarning(" ".join(exc_msg))
    #print(interactions)
    return interactions


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


class TestObject():
    """ Container to hold test information.

    :param: str test_file: Path to the test file
    """

    def __init__(self, test_file):
        if not os.path.exists(test_file):
            raise FileNotFoundError(f"'{test_file}' was not found.")
        path_split = os.path.split(test_file)
        self.test_dir = path_split[0]
        self.test_file = path_split[1]
        self.interactions = parse_test_interactions(test_file)
        self.repl_session = ""
        self.test_result = None


class TestResultStream(StringIO):
    """ Container for handling test result output, sending to
        both the stdout (print) and retaining the stream for
        logging and database usage.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def write(self, data, quiet=True):
        """ Override StringIO's write command so that we can also
            print to stdout.
        """
        if isinstance(data, bytes):
            data = str(data, encoding="utf-8")

        if not quiet:
            print(data)

        if data[-1:] != "\n":
            data = data + "\n"
        super().write(data)

class TestController():
    """ Main class to handle testing operations.

    :param: board: The name of the board to run tests on. Must match
                   an available board in `circuitpython/tools/cpboard.py`.
    :param: build_ref: A reference to the tag/commit to test. This will
                       usually be generated by the GitHub Checks API.
    """
    def __init__(self, board, build_ref):
        self.state = "init"
        self.run_date = datetime.datetime.now().strftime("%d-%b-%Y,%H:%M:%S%Z")
        self.build_ref = build_ref
        self.board_name = board
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        init_msg = [
            "="*25 + " RosiePi " + "="*26,
            "Initiating rosiepi...",
            "-"*60,
            f" - Date/Time: {self.run_date}",
            f" - Test commit: {build_ref}",
            f" - Test board: {board}",
            "="*60,
            f"Connecting to: {board}",
            "-"*60
        ]
        self.log = TestResultStream(initial_value="\n".join(init_msg))

        try:
            self.board = pyboard.CPboard.from_try_all(board)
            init_msg = [
                "Connected!",
                "Board info:",
                f" - Serial Number: {self.board.serial_number}",
                f" - Disk Drive: {self.board.disk.path}",
                "="*60,
            ]
            self.log.write("\n".join(init_msg))
            self.state = "board_connected"
        except RuntimeError as conn_err:
            err_msg = [
                f"Failed to connect to: {self.board_name}",
                conn_err.args[0],
                "="*60,
                "Closing RosiePi"
            ]
            self.log.write("\n".join(err_msg))
            self.state = "error"

    def start_test(self):
        self.state = "starting_fw_prep"
        self.log.write("Preparing Firmware...")
        self.log.write("-"*60)
        try:
            self.fw_build_dir = cirpy_actions.build_fw(self.board_name, self.build_ref, self.log)
            self.log.write("="*60)

            self.log.write(f"Updating Firmware on: {self.board_name}")
            cirpy_actions.update_fw(
                self.board,
                os.path.join(self.fw_build_dir, "firmware.uf2"),
                self.log
            )
            self.log.write("="*60)
        except RuntimeError as fw_err:
            err_msg = [
                f"Failed update firmware on: {self.board_name}",
                fw_err.args[0],
                "="*60,
                "Closing RosiePi"
            ]
            self.log.write("\n".join(err_msg), quiet=True)
            self.state = "error"
            #raise RuntimeError("\n".join(err_msg)) from None
        #print(self.board.firmware.info)

        if self.state != "error":
            self.state = "gather_tests"
            self.log.write("Gathering tests to run...")
            self.tests = self.gather_tests()
            init_msg = [
                "The following tests will be run:",
                " - " + ", ".join([test.test_file for test in self.tests]),
                "="*60,
            ]
            self.log.write("\n".join(init_msg))

            self.state = "running_tests"
            self.run_tests()
            self.log.write("="*60)

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
        this_test_passed = True

        with self.board as board:
            board.repl.session = b""

            for test in self.tests:
                # we likely had a REPL reset, so make sure we're
                # past the "press any key" prompt.
                board.repl.execute(b"\x01", wait_for_response=True)

                this_test_passed = True

                self.log.write(f"Starting test: {test.test_file}")

                test_file_path = os.path.join(test.test_dir, test.test_file)
                test_cmds = []

                with open(test_file_path, 'r') as current_test:
                    test_cmds = current_test.readlines()

                for line_no, line in enumerate(test_cmds, start=1):
                    if line == "\n":
                        continue

                    self.log.write(
                        "running line: ({0}) {1}".format(line_no,
                                                         line.rstrip('\n'))
                    )

                    try:
                        if line_no in test.interactions:
                            action = test.interactions[line_no]["action"]
                            value = test.interactions[line_no]["value"]
                            #print(f"ACTION: {action}; VALUE: {value}")
                            if action == "output":
                                self.log.write(
                                    f"- Testing for output of: {value}"
                                )

                                try:
                                    result = exec_line(board, line)
                                except Exception as exc:
                                    raise pyboard.CPboardError(exc) from Exception

                                result = str(result,
                                             encoding="utf-8").rstrip("\r\n")
                                if result != value:
                                    this_test_passed = False

                                self.log.write(" - Passed!")

                            elif action == "input":
                                self.log.write(f"- Sending input: {value}")

                                try:
                                    exec_line(board, line, echo=False)
                                    exec_line(board, value, input=True)
                                except Exception as exc:
                                    raise pyboard.CPboardError(exc) from Exception

                            elif action == "verify":
                                self.log.write(f"- Verifying with: {value}")

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
                                    #self.log.write(ver_func)

                                    exec_line(board, line)
                                    result = ver_func(board)
                                    if not result:
                                        raise pyboard.CPboardError(
                                            f"'{value}' test failed."
                                        )
                                except Exception as exc:
                                    raise pyboard.CPboardError(exc) from Exception

                                self.log.write(" - Passed!")

                        else:
                            board.repl.execute(line)

                    except pyboard.CPboardError as line_err:
                        this_test_passed = False
                        err_args = [str(arg) for arg in line_err.args]
                        err_msg = [
                            "Test Failed!",
                            " - Last code executed: '{}'".format(line.strip('\n')),
                            f" - Line: {line_no}",
                            f" - Exception: {''.join(err_args)}",
                        ]
                        self.log.write("\n".join(err_msg))
                        break

                    if this_test_passed != True:
                        break

                test.test_result = this_test_passed
                self.tests_run += 1
                test.repl_session = board.repl.session
                #print(board.repl.session)
                self.log.write("-"*60)
                board.repl.reset()

        for test in self.tests:
            if test.test_result == None:
                continue
            elif test.test_result == True:
                self.tests_passed += 1
            elif test.test_result == False:
                self.tests_failed += 1

        end_msg = [
            f"Ran {self.tests_run} of {total_tests} tests.",
            f"Passed: {self.tests_passed}",
            f"Failed: {self.tests_failed}",
        ]
        self.log.write("\n".join(end_msg))


    @property
    def result(self):
        """ Cummulative result of all tests run.
        """
        result = True
        if self.state != "error":
            if self.tests_run < len(self.tests):
                result = False
            else:
                failed = [test for test in self.tests if test.test_result == False]
                if failed:
                    result = False
        else:
            result = False

        return result

def main():
    cli_args = cli_parser.parse_args()
    #cirpy_actions.check_local_clone()
    tc = TestController(cli_args.board, cli_args.build_ref)
    if tc.state != "error":
        tc.start_test()

    #print(tc.result)
    #print()
    #print("tc's stream log:")
    print(tc.log.getvalue())
