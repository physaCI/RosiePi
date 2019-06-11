from setuptools import setup, find_packages
setup(
    name="rosiepi",
    version="0.1",
    # metadata to display on PyPI
    author="Michael Schroeder",
    author_email="sommersoft@gmail.com",
    description="CircuitPython Firmware Test Framework",
    license="MIT",
    keywords="circuitpython, rosiepi, rosie",
    url="https://github.com/sommersoft/RosiePi",   # project home page, if any
    project_urls={
        "Issues": "https://github.com/sommersoft/RosiePi/issues",
        #"Documentation": "https://docs.example.com/HelloWorld/",
        "Source Code": "https://github.com/sommersoft/RosiePi",
    },

    # could also include long_description, download_url, classifiers, etc.

    #scripts=['rosie_scripts/test_control_unit.py'],

    install_requires=[
        "pyserial",
        "sh",
        "pyusb",
        "sh",
    ],

    packages=find_packages(),#["rosiepi"],

    #package_dir={"":"rosiepi"},
    package_data={
        "": [
            "circuitpython/tests/*",
            "circuitpython/tests/circuitpython/*",
            ".fw_builds/*"
        ]
    },

    entry_points={
        "console_scripts": [
            "rosiepi = rosiepi.rosie.test_controller:main"
        ]
    }
)
