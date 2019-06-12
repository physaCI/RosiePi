from setuptools import setup, find_packages
setup(
    name="rosiepi",
    version="0.1",
    # metadata to display on PyPI
    author="Michael Schroeder",
    author_email="sommersoft@github.com",
    description="CircuitPython Firmware Test Framework",
    license="MIT",
    keywords="circuitpython, rosiepi, rosie",
    url="https://github.com/sommersoft/RosiePi",   # project home page, if any
    project_urls={
        "Issues": "https://github.com/sommersoft/RosiePi/issues",
        #"Documentation": "https://sommersoft/RosiePi/README.md",
        "Source Code": "https://github.com/sommersoft/RosiePi",
    },

    # could also include long_description, download_url, classifiers, etc.

    #scripts=['rosie_scripts/test_control_unit.py'],

    install_requires=[
        "pyserial",
        "sh",
        "pyusb",
    ],

    packages=find_packages(),

    package_data={
        "": [
            "verifiers/*"
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