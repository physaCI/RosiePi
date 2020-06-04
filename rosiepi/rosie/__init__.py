
import logging
import pathlib
import sys


rosiepi_logger = logging.getLogger(__name__)

def find_circuitpython():
    user_home = pathlib.Path().home()
    cirpy_dir = user_home / "circuitpython"
    #print("user_home: {}\ncirpy_dir: {}".format(user_home, cirpy_dir))
    if not cirpy_dir.exists():
        rosiepi_logger.warning("%s not found...", cirpy_dir)
        raise FileNotFoundError()
    return cirpy_dir

sys.path.append(str(find_circuitpython()))
#print(sys.path)
