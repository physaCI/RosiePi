import pathlib
import sys

def find_circuitpython():
    user_home = pathlib.Path().home()
    cirpy_dir = user_home / "circuitpython"
    #print("user_home: {}\ncirpy_dir: {}".format(user_home, cirpy_dir))
    if not cirpy_dir.exists():
        sys.exit(1)
    return cirpy_dir

sys.path.append(str(find_circuitpython()))
#print(sys.path)
