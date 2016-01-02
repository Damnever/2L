# -*- coding: utf-8 -*-

from setuptools import setup
from pip.req import parse_requirements


reqs = [str(r.req)
        for r in parse_requirements('requirements.txt', session=False)]

setup(
    name='2L',
    version='0.0.1',
    description='2L, There is a surprise!',
    long_description='2L, SB! BIG S! BIG B! BIG SB!!!',
    url='https://github.com/Damnever/2L',
    author='Damnever',
    author_emial='dxc.wolf@gmail.com',
    license='The BSD 3-Clause License',
    keywords='bbs, forum, 2L',
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
    ],
    install_requires=reqs,
    entry_points={
        'console_scripts': [
            '2L=app.commands:main',
        ]
    },
)
