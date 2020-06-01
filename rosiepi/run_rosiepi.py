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

import pathlib

ACTIVATE_THIS = f'{pathlib.Path().home()}/rosie_pi/rosie_venv/bin/activate_this.py'
with open(ACTIVATE_THIS) as file_:
    exec(file_.read(), dict(__file__=ACTIVATE_THIS)) # pylint: disable=exec-used

# pylint: disable=wrong-import-position
import argparse
import dataclasses
import datetime
import logging
import json
import traceback

from configparser import ConfigParser
from socket import gethostname

import requests

from .rosie import test_controller

# pylint: disable=invalid-name
rosiepi_logger = logging.getLogger(__name__)

cli_parser = argparse.ArgumentParser(description="RosieApp")
cli_parser.add_argument(
    "commit",
    help="Commit of circuitpython firmware to build"
)
cli_parser.add_argument(
    "check_run_id",
    help="ID of the check run that requested the test"
)


# TODO: update to adafruit github
GIT_URL_COMMIT = "https://github.com/sommersoft/circuitpython/commit/"

_STATIC_CONFIG_FILE = pathlib.Path("/etc/opt/physaci_sub/conf.ini")

class PhysaCIConfig():
    """ Container class for holding local configuration results. """

    def __init__(self):
        self.config = ConfigParser(allow_no_value=True, default_section="local")
        read_config = self.config.read(_STATIC_CONFIG_FILE)
        if not read_config:
            raise RuntimeError("Failed to read physaCI subscription info.")

        self.config_location = self.config.get("local", "config_file",
                                               fallback=_STATIC_CONFIG_FILE)
        if self.config_location != _STATIC_CONFIG_FILE.resolve():
            alt_conf_file = pathlib.Path(self.config_location)
            read_config = self.config.read([_STATIC_CONFIG_FILE, alt_conf_file])

    @property
    def physaci_url(self):
        """ URL to send physaCI requests. """
        return self.config.get("local", "physaci_url")

    @property
    def physaci_api_key(self):
        """ API key to send with physaCI requests. """
        return self.config.get("physaci", "api_access_key")

    @property
    def supported_boards(self):
        """ The boards connected to this RosiePi node. """
        boards = self.config.get("rosie_pi", "boards")
        board_list = boards.split(", ")
        return board_list

@dataclasses.dataclass
class GitHubData():
    """ Dataclass to contain data formatted to update the GitHub
        check run.
    """
    conclusion: str = ""
    completed_at: str = ""
    output: dict = dataclasses.field(default_factory=dict)

# pylint: disable=too-few-public-methods
@dataclasses.dataclass
class NodeTestData():
    """ Dataclass to contain test data stored by physaCI. """
    board_tests: list = dataclasses.field(default_factory=list)

class TestResultPayload():
    """ Container to hold the test result payload """

    def __init__(self):
        self.github_data = GitHubData()
        self.node_test_data = NodeTestData()

    @property
    def payload_json(self):
        """ Format the contents into a JSON string. """
        payload_dict = {
            "github_data": dataclasses.asdict(self.github_data),
            "node_test_data": dataclasses.asdict(self.node_test_data)
        }

        return json.dumps(payload_dict)

def markdownify_results(results, results_url):
    """ Puts test results into a Markdown table for use with
        the GitHub Check Run API for the output text.

        :param: results: Iterable of dicts with info.
    """

    mdown = [
        "| Board | Result | Tests Passed | Tests Failed |",
        "| :---: | :---: | :---: | :---: |"
    ]

    for board in results:
        board_mdown = [
            "",
            board["board_name"],
            board["outcome"],
            board["tests_passed"],
            board["tests_failed"],
            "",
        ]
        mdown.append("|".join(board_mdown))

    mdown.extend([
        "",
        f"Full test log(s) available [here]({results_url})."
    ])

    return "\n".join(mdown)


def run_rosie(commit, check_run_id, boards, payload):
    """ Runs rosiepi for each board.
        Returns results as a JSON for sending to GitHub.

        :param: commit: The commit of circuitpython to pass to rosiepi.
        :param: check_run_id: The ID of the GitHub Check Run
        :param: boards: The boards connected to the RosiePi node to run tests
                        on. Supplied by the node's config file.
        :param: payload: The ``TestResultPayload`` container to hold
                         incremental result data.
    """

    app_conclusion = ""

    summary_params = {
        "commit_title": commit[:5],
        "commit_url": "".join([GIT_URL_COMMIT, commit]),
    }

    app_output_summary = [
        "Ran tests on: ",
        f"[{summary_params['commit_title']}]",
        f"({summary_params['commit_url']})",
        "\n\n",
        "RosiePi job ran on node: ",
        f"{gethostname()}",
    ]

    payload.github_data.output.update(
        {
            "title": "RosiePi",
            "summary": "".join(app_output_summary),
            "text": "",
        }
    )

    rosiepi_logger.info("Starting tests...")

    for board in boards:
        board_results = {
            "board_name": board,
            "outcome": None,
            "tests_passed": 0,
            "tests_failed": 0,
            "rosie_log": "",
        }

        try:
            rosie_test = test_controller.TestController(board, commit)

            # check if connection to board was successful
            if rosie_test.state != "error":
                rosie_test.start_test()
            else:
                board_results["outcome"] = "Error"
                #print(rosie_test.log.getvalue())
                app_conclusion = "failure"

        except Exception: # pylint: disable=broad-except
            rosie_test.log.write(traceback.format_exc())
            break

        finally:
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

            board_results["tests_passed"] = str(rosie_test.tests_passed)
            board_results["tests_failed"] = str(rosie_test.tests_failed)
            board_results["rosie_log"] = rosie_test.log.getvalue()
            payload.node_test_data.board_tests.append(board_results)

    payload.github_data.conclusion = app_conclusion

    payload.github_data.completed_at = (
        datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    results_url = (
        f"https://www.physaci.com/job?node{gethostname()}&job-id{check_run_id}"
    )

    payload.github_data.output.update(
        {
            "text": markdownify_results(
                payload.node_test_data.board_tests,
                results_url
            )
        }
    )

    rosiepi_logger.info("Tests completed...")

def send_results(check_run_id, physaci_config, results_payload):
    """ Send the results to physaCI.

        :param: check_run_id: The check run ID of the initiating check.
        :param: physaci_config: A ``PhysaCIConfig()`` instance
        :param: results_payload: A JSON string with the test results.
    """

    rosiepi_logger.info("Sending test results to physaCI.")

    physaci_url = physaci_config.physaci_url + "/testresult/update"
    header = {"x-functions-key": physaci_config.physaci_api_key}
    payload = json.loads(results_payload)
    payload["node_name"] = gethostname()
    payload["check_run_id"] = check_run_id

    response = requests.post(physaci_url, headers=header, json=payload)
    if not response.ok:
        rosiepi_logger.warning(
            "Failed to send results to physaCI.\n"
            "Response code: %s\n"
            "Response: %s",
            response.status_code,
            response.text
        )
        raise RuntimeError(
            f"RosiePi failed to send results. Results payload: {results_payload}"
        )

    rosiepi_logger.info("Test results sent successfully.")

def main():
    """ Run RosiePi tests. """
    cli_arg = cli_parser.parse_args()

    commit = cli_arg.commit
    check_run_id = cli_arg.check_run_id

    rosiepi_logger.info("Initiating RosiePi test(s).")
    rosiepi_logger.info("Testing commit: %s", commit)
    rosiepi_logger.info("Check run id: %s", check_run_id)

    config = PhysaCIConfig()

    payload = TestResultPayload()

    run_rosie(commit, check_run_id, config.supported_boards, payload)

    send_results(check_run_id, config, payload.payload_json)
