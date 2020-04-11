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
import json
import pathlib
import requests

from configparser import ConfigParser
from socket import gethostname

from .logger import rosiepi_logger
from .rosie import find_circuitpython, test_controller

cli_parser = argparse.ArgumentParser(description="RosieApp")
cli_parser.add_argument(
    "commit",
    help="Commit of circuitpython firmware to build"
)
cli_parser.add_argument(
    "check_run_id",
    help="ID of the check run that requested the test"
)


GIT_URL_COMMIT = "https://github.com/adafruit/circuitpython/commit/"

_STATIC_CONFIG_FILE = pathlib.Path("/etc/opt/physaci_sub/conf.ini")

class PhysaCIConfig():
    """ Container class for holding local configuration results.
    """

    def __init__(self):
        self.config = ConfigParser(allow_no_value=True, default_section="local")
        read_config = self.config.read(_STATIC_CONFIG_FILE)
        if not read_config:
            raise RuntimeError("Failed to read physaCI subscription info.")

        self.config_location = self.config.get("local", "config_file",
                                               fallback=_STATIC_CONFIG_FILE)
        if self.config_location != _STATIC_CONFIG_FILE.resolve():
            alt_conf_file = pathlib.Path(self.config_location)
            read_config = self.config.read([_STATIC_CONFIG_FILE, alt_conf_file],
                                           default_section="local")

    @property
    def physaci_url(self):
        return self.config.get("local", "physaci_url")

    @property
    def physaci_api_key(self):
        return self.config.get("physaci", "api_access_key")

    @property
    def supported_boards(self):
        return self.config.get("rosie_pi", "boards")

def process_rosie_log(log):
    rosie_log = []
    subsection = []
    for line in log.split("\n"):
        if line.count("=") < 25:
            if line.count("-") < 60:
                subsection.append(line)
            else:
                continue
        else:
            rosie_log.append(subsection)
            subsection = []

    return rosie_log

def markdownify_results(results):
    """ Puts test results into a Markdown table for use with
        the GitHub Check Run API for the output text.

        :param: results: Iterable of dicts with info.
    """

    mdown = [
        "| Board | Result | Tests Passed | Tests Failed",
        "| :---: | :---: | :---: | :---: |"
    ]

    for board in results:
        board_mdown = [
            board["name"],
            board["outcome"],
            board["tests_passed"],
            board["tests_failed"],
        ]
        mdown.append(board_mdown)

    return "\n".join(mdown)


def run_rosie(commit, boards):
    """ Runs rosiepi for each board.
        Returns results as a JSON for sending to GitHub.

        :param: commit: The commit of circuitpython to pass to rosiepi.
        :param: boards: The boards connected to the RosiePi node to run tests
                        on. Supplied by the node's config file.
    """

    app_conclusion = ""
    app_completed_at = None

    summary_params = {
        "commit_title": commit[:5],
        "commit_url": "".join([GIT_URL_COMMIT, commit]),
        "rosie_version": "0.1", #rosiepi_version,
    }

    app_output = {
        "title": "RosiePi",
        "summary": app_output_summary,
        "text": "",
    }

    board_tests = []

    rosiepi_logger.info("Starting tests...")

    for board in boards:
        board_results = {
            "board_name": board,
            "outcome": None,
            "tests_passed": 0,
            "tests_failed": 0,
            "rosie_log": "",
        }
        rosie_test = test_controller.TestController(board, commit)

        # check if connection to board was successful
        if rosie_test.state != "error":
            rosie_test.start_test()
        else:
            board_results["outcome"] = "Error"
            #print(rosie_test.log.getvalue())
            app_conclusion = "failure"

        # now check the result of each board test
        if rosie_test.result: # everything passed!
            board_results["outcome"] = "Passed"
            if app_conclusion != "failure":
                app_conclusion = "success"
        else:
            if rosie_test.state != "error":
                board_results["outcome"] = "Failed"
            else:
                board_results["outcome"] = "Error"
            app_conclusion = "failure"

        board_results["tests_passed"] = rosie_test.tests_passed
        board_results["tests_failed"] = rosie_test.tests_failed
        board_results["rosie_log"] = rosie_test.log.getvalue()
        board_tests.append(board_results)

    app_output["text"] = markdownify_results(board_tests)

    app_completed_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "github_data": {
            "conclusion": app_conclusion,
            "completed_at": app_completed_at,
            "output": app_output,
        },
        "node_test_data": {
            "board_tests": board_tests
        }
    }
    #print("payload:", payload)
    json_payload = json.dumps(payload)
    print(json_payload)

    rosiepi_logger.info("Tests completed...")

    return json_payload

def send_results(check_run_id, physaci_config, results_payload):
    """ Send the results to physaCI.

        :param: check_run_id: The check run ID of the initiating check.
        :param: physaci_config: A ``PhysaCIConfig()`` instance
        :param: results_payload: A JSON string with the test results.
    """

    rosiepi_logger.info("Sending test results to physaCI.")

    phsyci_url = physaci_config.physaci_url + "/testresult/update"
    header = {"x-functions-key": physaci_config.physaci_api_key}
    payload = json.loads(results_payload)
    payload["node_name"] = gethostname()
    payload["check_run_id"] = check_run_id

    response = request.post(physaci_url, headers=header, json=payload)
    if not response.ok:
        rosiepi_logger.warning("Failed to send results to physaCI")
        raise RuntimeError(
            f"RosiePi failed to send results. Results payload: {results_payload}"
        )

    rosiepi_logger.info("Test results sent successfully.")

def main():
    cli_arg = cli_parser.parse_args()

    rosiepi_logger.info("Initiating RosiePi test(s).")
    rosiepi_logger.info(f"Testing commit: {cli_arg.commit}")
    rosiepi_logger.info(f"Check run id: {cli_arg.check_run_id}")

    config = PhysaCIConfig()

    rosie_results = run_rosie(cli_arg.commit, config.supported_boards)

    send_results(cli_arg.check_run_id, config, rosie_results)
