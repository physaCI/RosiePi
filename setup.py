from setuptools import setup, find_packages
setup(
    name="rosiepi",
    version="0.2",
    # metadata to display on PyPI
    author="Michael Schroeder",
    author_email="sommersoft@github.com",
    description="CircuitPython Firmware Test Framework",
    license="MIT",
    keywords="circuitpython, rosiepi, rosie",
    url="https://github.com/physaCI/RosiePi",   # project home page, if any
    project_urls={
        "Issues": "https://github.com/physaCI/RosiePi/issues",
        #"Documentation": "https://sommersoft/RosiePi/README.md",
        "Source Code": "https://github.com/physaCI/RosiePi",
    },

    python_requires=">=3.7",

    # could also include long_description, download_url, classifiers, etc.

    #scripts=['rosie_scripts/test_control_unit.py'],

    install_requires=[
        "pyserial==3.4",
        "pytest<5.5",
        "pyusb",
        "requests",
        "sh",
    ],

    packages=find_packages(),

    entry_points={
        "console_scripts": [
            "rosiepi = rosiepi.rosie.test_controller:main",
            "run_rosie = rosiepi.run_rosiepi:main"
        ]
    }
)
