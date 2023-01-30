"""
.. module:: _version_info
   :platform: python 3.6+
   :synopsis: Version 0.9.0 of mimoCoRB

.. moduleauthor:: Guenter Quast <guenter.quast@online.de>
"""

major = 0
minor = 9
revision = 0


def _get_version_tuple():
    """
    version as a tuple
    """
    return major, minor, revision


def _get_version_string():
    """
    version as a string
    """
    return "%d.%d.%d" % _get_version_tuple()
