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

import logging
import os
import pathlib
import subprocess
import time

import sh
from sh.contrib import git

rosiepi_logger = logging.getLogger(__name__) # pylint: disable=invalid-name

_AVAILABLE_PORTS = ["atmel-samd", "nrf"]

def clone_commit(cirpy_dir, commit):
    """ Clones the `circuitpython` repository, fetches the commit, then
        checks out the repo at that ref.
    """
    working_dir = pathlib.Path()

    rosiepi_logger.info("Cloning repository at reference: %s", commit)

    try:
        git.clone(
            "--depth",
            "1",
            "-n",
            "https://github.com/sommersoft/circuitpython.git",
            cirpy_dir
        )

        os.chdir(cirpy_dir)
        git.fetch("origin", commit)

        git.checkout(commit)

        git.submodule("sync")

        git.submodule("update", "--init")

    except sh.ErrorReturnCode as git_err:
        git_stderr = str(git_err.stderr, encoding="utf-8").strip("\n")
        err_msg = [
            f"Failed to retrive repository at {commit}:",
            f" - {git_stderr}",
        ]
        rosiepi_logger.warning("%s", "\n".join(err_msg))
        raise RuntimeError(git_stderr) from None

    finally:
        os.chdir(working_dir)

def build_fw(board, test_log, cirpy_dir): # pylint: disable=too-many-locals,too-many-statements
    """ Builds the firware at `build_ref` for `board`. Firmware will be
        output to `.fw_builds/<build_ref>/<board>/`.

    :param: str board: Name of the board to build firmware for.
    :param: str build_ref: The tag/commit to build firmware for.
    :param: test_log: The TestController.log used for output.
    """
    working_dir = os.getcwd()

    cirpy_ports_dir = cirpy_dir / "ports"

    board_port_dir = None
    for port in _AVAILABLE_PORTS:
        port_dir = cirpy_ports_dir / port / "boards" / board
        if port_dir.exists():
            board_port_dir = (cirpy_ports_dir / port).resolve()
            rosiepi_logger.info("Board source found: %s", board_port_dir)
            break

    if board_port_dir is None:
        raise RuntimeError(
            f"'{board}' board not available to test. Can't build firmware."
        )

    build_dir = pathlib.Path(board_port_dir, ".fw_build", board)

    board_cmd = (
        f"make -C {board_port_dir.resolve()} BOARD={board} BUILD={build_dir} V=2"
    )

    test_log.write("Building firmware...")
    try:
        rosiepi_logger.info("Running make recipe: %s", board_cmd)
        run_envs = {
            "BASH_ENV": "/etc/profile",
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8"
        }

        rosiepi_logger.info("Running firmware build...")
        fw_build = subprocess.run(
            board_cmd,
            check=True,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            executable=sh.which("bash"),
            start_new_session=True,
            env=run_envs,
            encoding="utf-8",
            errors="replace"
        )

        result = fw_build.stdout.split("\n")
        success_msg = [line for line in result if "bytes" in line]
        test_log.write(" - " + "\n - ".join(success_msg))
        rosiepi_logger.info("Firmware built...")

    except subprocess.CalledProcessError as cmd_err:
        err_msg = [
            "Building firmware failed:",
            " - {}".format(cmd_err.stdout.strip("\n")),
        ]
        rosiepi_logger.warning("Firmware build failed...")
        raise RuntimeError("\n".join(err_msg)) from None

    finally:
        os.chdir(working_dir)

    return build_dir

def update_fw(board, board_name, fw_path, test_log):
    """ Resets `board` into bootloader mode, and copies over
        new firmware located at `fw_path`.

    :param: board: The cpboard.py::CPboard object to act upon
    :param: board_name: The name of the board
    :param: fw_path: File path to the firmware UF2 to copy.
    :param: test_log: The TestController.log used for output.
    """
    try:
        from tests import pyboard # pylint: disable=import-outside-toplevel

        with board:
            if not board.bootloader:
                test_log.write(" - Resetting into bootloader mode...")
                board.reset_to_bootloader(repl=True)
                time.sleep(10)

        boot_board = pyboard.CPboard.from_build_name_bootloader(board_name)
        with boot_board:
            test_log.write(
                " - In bootloader mode. Current bootloader: "
                f"{boot_board.firmware.info['header']}"
            )
            test_log.write(" - Uploading firmware...")

            boot_board.firmware.upload(fw_path)

            time.sleep(10)

        with board:
            pass
        test_log.write("Firmware upload successful!")

    except BaseException as brd_err:
        err_msg = [
            "Updating firmware failed:",
            f" - {brd_err.args}",
        ]
        raise RuntimeError("\n".join(err_msg)) from None
