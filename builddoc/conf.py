# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import sys, os

sys.path.insert(0, os.path.abspath('../'))
sys.path.insert(0, os.path.abspath('../examples/'))
sys.path.insert(0, os.path.abspath('../examples/modules'))
sys.path.insert(0, os.path.abspath('../test/'))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'mimoCoRB'
# copyright = '2023, G. Quast, K. Heitlinger'
author = 'C. Mayer, K. Heitlinger, G. Quast'
release = '1.0.'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# do not attempt to load modules possibly not available
autodoc_mock_imports = [
    'numpy', 'matplotlib', 'scipy','websockets', 'tarfile', 'pandas',
    'unittest', 'test' ] 


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']
