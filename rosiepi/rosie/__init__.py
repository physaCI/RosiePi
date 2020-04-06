import pathlib
import sys

import os
import getpass

from ..logger import rosiepi_logger

rosiepi_logger.info(f"getpass.getuser: {getpass.getuser()}")
rosiepi_logger.info(f"os.environ['USER']: {os.environ.get('USER')}")

def find_circuitpython():
    user_home = pathlib.Path().home()
    rosiepi_logger.info(f"user_home: {user_home}")
    cirpy_dir = user_home / "circuitpython"
    #print("user_home: {}\ncirpy_dir: {}".format(user_home, cirpy_dir))
    if not cirpy_dir.exists():
        raise FileNotFoundError()
    return cirpy_dir

sys.path.append(str(find_circuitpython()))
#print(sys.path)
