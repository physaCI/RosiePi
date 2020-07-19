# The MIT License (MIT)
#
# Copyright (c) 2020 Michael Schroeder
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

import platform

import pytest

class RosieTestController():
    """ pytest plugin for interacting with a target board with RosiePi.
    """

    def __init__(self, test_controller):
        self._controller = test_controller

    def pytest_sessionstart(self):
        """ pytest fixture to inject pytest environment info into the RosiePi
            log stream.
        """
        info_msg = (
            f"pytest session starts -- Python {platform.python_version()} -- "
            f"pytest {pytest.__version__}"
        )
        self._controller.log.write(info_msg)

    def pytest_sessionfinish(self, session, exitstatus):
        """ pytest fixture to update the final pass/fail numbers to the
            RosiePi test controller instance.
        """
        self._controller.tests_passed = (
            session.testscollected - session.testsfailed
        )
        self._controller.tests_failed = session.testsfailed
        self._controller._result = exitstatus

    def pytest_collectreport(self, report):
        """ pytest fixture to update the number of tests collected to
            the RosiePi test controller instance.
        """
        if report.nodeid:
            self._controller.tests_collected += len(report.result)


    def pytest_collection_finish(self):
        """ pytest fixutre to inject the number of tests collected into
            the RosiePi log stream.
        """
        self._controller.log.write(
            f"Collected {self._controller.tests_collected} tests\n\n"
        )

    #def pytest_report_collectionfinish(self, startdir):
    #    """ pytest fixutre to inject the root directory into the RosiePi log.
    #    """
    #    self._controller.log.write(f"root dir: {startdir}")

    def pytest_runtest_logreport(self, report):
        """ pytest fixture to inject each test's location, outcome, and
            duration into the RosiePi log stream.
        """
        if report.when == "call":
            call_line = (
                f"{report.outcome.upper():<8} "
                f"{report.nodeid} "
                f"({report.duration:.2f} secs)"
            )

            if report.outcome == "failed":
                trace_lines = str(report.longrepr.reprtraceback)
                trace_lines = [f"--> {line}" for line in trace_lines.split("\n")]
                call_line = "\n{call}\n{trace}\n\n".format(
                    call=call_line,
                    trace="\n".join(trace_lines)
                )

            self._controller.log.write(call_line)

    @pytest.fixture()
    def board_name(self):
        """ Fixture that provides the current board's name.
        """
        return self._controller.board_name

    @pytest.fixture()
    def board(self):
        """ Fixture that provides the current board interface.
        """
        with self._controller.board as board:
            board.repl.reset()
        return self._controller.board
