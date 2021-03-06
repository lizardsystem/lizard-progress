from setuptools import setup

version = '5.1.6.dev0'

long_description = '\n\n'.join([
    open('README.rst').read(),
    open('CREDITS.rst').read(),
    open('CHANGES.rst').read(),
    ])

install_requires = [
    'Django >= 1.4, < 1.7',  # Ships with form-wizard
    'python-dateutil >= 1.5,< 2.0',  # Needed for Celery
    'celery',
    'billiard',
    'django-celery',
    'django-kombu',
    'django-extensions',
    'django-jsonfield',
    'django-nose',
    'django-transaction-hooks',
    'geojson',
    'metfilelib >= 0.14',
    'ribxlib >= 0.10',
    'pkginfo',
    'factory_boy',
    'mock',
    'dxfwrite',
    'pandas',
    'pyproj',
    # This is for the export to Lizard functionality
    'sqlalchemy >= 0.8',
    'geoalchemy2',
    'pyshp < 2', # Also used by other exports
    'requests',
    # Previously in lizard-map / lizard-ui
    'south',
    'django-compressor',
    'django-tls'
    ]

tests_require = [
    'coverage',
    'nose',
    ]

setup(name='lizard-progress',
      version=version,
      description="TODO",
      long_description=long_description,
      # Get strings from http://www.python.org/pypi?%3Aaction=list_classifiers
      classifiers=['Programming Language :: Python',
                   'Framework :: Django',
                   ],
      keywords=[],
      author='Remco Gerlich, Carsten Byrman',
      author_email='remco.gerlich@nelen-schuurmans.nl',
      url='',
      license='GPL',
      packages=['lizard_progress'],
      include_package_data=True,
      zip_safe=False,
      install_requires=install_requires,
      tests_require=tests_require,
      extras_require={'test': tests_require},
      entry_points={
          'console_scripts': [],
      }
)
