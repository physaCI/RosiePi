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

import os
import pkg_resources
import sh
from sh.contrib import git
import subprocess
import sys
import time

_AVAILABLE_PORTS = ["atmel-samd", "nrf"]

def cirpy_dir():
    return pkg_resources.resource_filename("rosiepi", "circuitpython")


def check_local_clone():
    """ Checks if there is a local clone of the circuitpython repository.
        If not, it will clone it to the `circuitpython` directory.
    """
    check_dir = os.listdir(cirpy_dir())
    if ".git" not in check_dir:
        working_dir = os.getcwd()
        os.chdir(cirpy_dir())
        git.clone("https://github.com/adafruit/circuitpython.git")
        os.chdir(working_dir)


def build_fw(board, build_ref):
    """ Builds the firware at `build_ref` for `board`. Firmware will be
        output to `.fw_builds/<build_ref>/<board>/`.

    :param: str board: Name of the board to build firmware for.
    :param: str build_ref: The tag/commit to build firmware for.
    """
    working_dir = os.getcwd()
    cirpy_ports_dir = os.path.join(cirpy_dir(), "ports")

    board_port_dir = None
    for port in _AVAILABLE_PORTS:
        port_dir = os.path.join(cirpy_ports_dir, port, "boards")
        if board in os.listdir(port_dir):
            board_port_dir = os.path.join(cirpy_ports_dir, port)
            break
    if board_port_dir == None:
        err_msg = [
            "'{}' board not available to test. Can't build firmware.".format(board),
            "="*60,
            "Closing RosiePi"
        ]
        raise RuntimeError("\n".join(err_msg))

    # TODO: might need to move this to a USB drive in the future to
    # minimize writes to the RPi SD card.
    build_dir = os.path.join(
        pkg_resources.resource_filename("rosiepi", ".fw_builds"),
        build_ref[:5],
        board
    )

    os.chdir(cirpy_dir())
    try:
        print("Fetching {}...".format(build_ref))
        git.fetch("origin", build_ref)

        print("Checking out {}...".format(build_ref))
        git.checkout(build_ref)

        print("Updating submodules...")
        git.submodule("update", "--init", "--recursive")
    except sh.ErrorReturnCode as git_err:
        # TODO: change to 'master'
        git.checkout("-f", "core_fold")
        os.chdir(working_dir)
        err_msg = [
            "Building firmware failed:",
            " - {}".format(str(git_err.stderr, encoding="utf-8").strip("\n")),
            "="*60,
            "Closing RosiePi"
        ]
        raise RuntimeError("\n".join(err_msg)) from None

    os.chdir(board_port_dir)
    board_cmd = (
        "make clean BOARD={board_name} BUILD={dir}".format(board_name=board,
                                                           dir=build_dir),
        "make BOARD={board_name} BUILD={dir}".format(board_name=board,
                                                     dir=build_dir)
    )

    print("Building firmware...")
    try:
        subprocess.run(board_cmd[0], shell=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.STDOUT)
        fw_build = subprocess.run(board_cmd[1], check=True, shell=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        result = str(fw_build.stdout, encoding="utf-8").split("\n")
        success_msg = [line for line in result if "bytes" in line]
        print(" - " + "\n - ".join(success_msg))
    except subprocess.CalledProcessError as cmd_err:
        # TODO: change to 'master'
        git.checkout("-f", "core_fold")
        os.chdir(working_dir)
        err_msg = [
            "Building firmware failed:",
            " - {}".format(str(cmd_err.stdout, encoding="utf-8").strip("\n")),
            "="*60,
            "Closing RosiePi"
        ]
        raise RuntimeError("\n".join(err_msg)) from None


    # TODO: change to 'master'
    git.checkout("-f", "core_fold")
    os.chdir(working_dir)
    return build_dir

def update_fw(board, fw_path):
    """ Resets `board` into bootloader mode, and copies over
        new firmware located at `fw_path`.

    :param: board: The cpboard.py::CPboard object to act upon
    :param: fw_path: File path to the firmware UF2 to copy.
    """
    success_msg = ["Firmware upload successful!"]
    try:
        with board:
            if not board.bootloader:
                print("Resetting into bootloader mode...")
                board.reset_to_bootloader(repl=True)
                time.sleep(10)
            print("In bootloader mode. Current bootloader: {}".format(board.firmware.info["header"]))

            print("Uploading firmware...")
            board.firmware.upload(fw_path)
            print("Waiting for board to reload...")
            time.sleep(10)
        with board:
            pass
            #success_msg.append(" - New firmware: {}".format(board.firmware.info))
        print("\n".join(success_msg))
    except BaseException as brd_err:
        err_msg = [
            "Updating firmware failed:",
            " - {}".format(brd_err.args),
            "="*60,
            "Closing RosiePi"
        ]
        raise BaseException("\n".join(err_msg)) from None
