from setuptools import find_packages, setup

setup(
    name='brewblox-ctl',
    use_scm_version={'local_scheme': lambda v: ''},
    url='https://github.com/BrewBlox/brewblox-ctl',
    author='BrewPi',
    author_email='development@brewpi.com',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    keywords='brewblox deployment menu',
    packages=find_packages(exclude=['test']),
    include_package_data=True,
    install_requires=[
        'requests',
        'click',
        'python-dotenv[cli]',
        'pyyaml',
        'pprint'
    ],
    python_requires='>=3.5',
    setup_requires=['setuptools_scm'],
    entry_points={
        'console_scripts': [
            'brewblox-ctl = brewblox_ctl.__main__:main',
        ]
    }
)
