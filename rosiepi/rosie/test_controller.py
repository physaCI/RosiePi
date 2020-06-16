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
from io import StringIO
import os

import pytest

from tests import pyboard

from rosiepi.rosie import find_circuitpython
from . import cirpy_actions

from .pytest_rosie import RosieTestController

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

class TestResultStream(StringIO):
    """ Container for handling test result output, sending to
        both the stdout (print) and retaining the stream for
        logging and database usage.
    """
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
        self.tests_collected = 0
        self.tests_passed = 0
        self.tests_failed = 0
        init_msg = [
            #"-"*60,
            "Initiating rosiepi...",
            f" - Date/Time: {self.run_date}",
            f" - Test commit: {build_ref}",
            f" - Test board: {board}",
            f" - Connecting to: {board}...",
        ]
        self.log = TestResultStream()
        self.log.write("\n".join(init_msg))

        try:
            kwargs = {
                'wait': 20,
            }
            self.board = pyboard.CPboard.from_try_all(board, **kwargs)
            init_msg = [
                f"   - Serial Number: {self.board.serial_number}",
                f"   - Disk Drive: {self.board.disk.path}",
            ]
            self.log.write("\n".join(init_msg))
            self.state = "board_connected"
        except RuntimeError as conn_err:
            err_msg = [
                f"Failed to connect to: {self.board_name}",
                conn_err.args[0],
                "Closing RosiePi"
            ]
            self.log.write("\n".join(err_msg))
            self.state = "error"
        self.log.write("-"*60)

    def start_test(self):
        self.state = "starting_fw_prep"
        self.log.write(
            f"Preparing Firmware..."
        )
        #self.log.write("-"*60)

        try:
            self.fw_build_dir = cirpy_actions.build_fw(self.board_name, self.build_ref, self.log)
            self.log.write("="*60)

            self.log.write(f"Updating Firmware on: {self.board_name}")
            cirpy_actions.update_fw(
                self.board,
                self.board_name,
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

        self.log.write("-"*60)

        if self.state != "error":
            self.state = "running_tests"
            self.run_tests()

    def run_tests(self):
        """ Runs the tests in self.tests.
        """

        rosie_tests_dir = os.path.join(cp_tests_dir(),
                                       "circuitpython",
                                       "rosie_tests")

        pytest.main([rosie_tests_dir], plugins=[RosieTestController(self)])

def main():
    cli_args = cli_parser.parse_args()
    #cirpy_actions.check_local_clone()
    tc = TestController(cli_args.board, cli_args.build_ref)
    if tc.state != "error":
        tc.start_test()

    #print(tc.result)
    #print()
    print("test log:")
    print(tc.log.getvalue())

    #print(f"{tc.tests_collected}: {tc.tests_passed} / {tc.tests_failed}")
