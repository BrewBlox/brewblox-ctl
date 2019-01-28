from setuptools import find_packages, setup

setup(
    name='brewblox-menu',
    use_scm_version={'local_scheme': lambda v: ''},
    url='https://github.com/BrewBlox/brewblox-menu',
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
    install_requires=[],
    python_requires='>=3.5',
    setup_requires=['setuptools_scm'],
    entry_points={
        'console_scripts': [
            'brewblox-menu = brewblox_menu.commands:main',
            # 'bbt-distcopy = brewblox_tools.distcopy:main',
            # 'bbt-bump = brewblox_tools.bump:main',
            # 'bbt-deploy-docker = brewblox_tools.deploy_docker:main',
            # 'bbt-localbuild = brewblox_tools.localbuild:main',
        ]
    }
)
