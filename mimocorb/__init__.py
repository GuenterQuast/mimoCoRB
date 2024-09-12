"""

.. moduleauthor:: Guenter Quast <guenter.quast@online.de>

.. module mimocorb
   :synopsis: multiple-in multiple-out configurable Ring Buffer
   for data acquisition systems

.. moduleauthor:: Guenter Quast <g.quast@kit.edu>

"""

# Import version info
from ._version_info import *

# and set version
__version__ = _version_info._get_version_string()

__all__ = [
    "mimo_buffer",
    "buffer_control",
    "bufferinfoGUI",
    "plot_buffer",
    "histogram_buffer",
    "pulseSimulator",
    "parquetReader",
]
