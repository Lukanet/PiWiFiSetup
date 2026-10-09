import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="PiWiFiSetup",
    version="0.0.8",
    author="Lukanet Ltd",
    author_email="avramov@lukanet.com",
    description="PiWiFiSetup is a program to headlessly configure a Raspberry Pi's WiFi connection using any other WiFi-enabled device",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Lukanet/PiWiFiSetup",
    project_urls={
        "Bug Tracker": "https://github.com/Lukanet/PiWiFiSetup/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU v3",
        "Operating System :: OS Independent",
    ],
    #package_dir={"": "src"},
    #packages=setuptools.find_packages(where="src"),
    packages=['PiWiFiSetup'],
    python_requires=">=3",
    install_requires=['Flask'],
    include_package_data=True,
    zip_safe=False,
    entry_points = {
        'console_scripts': ['PiWiFiSetup=PiWiFiSetup.PiWiFiSetup:main'],
    },
    options = {
    'build_scripts': {
        'executable': '/usr/bin/env python3',
        }
    }
)