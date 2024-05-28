#! /usr/bin/env python3
"""
script to start a mimoCoRB data acquisition suite
"""

import sys, time
from mimocorb.buffer_control import run_mimoDAQ

print("\n*==* script " + sys.argv[0] + " running \n")

daq = run_mimoDAQ(debug=False)

daq.setup()

daq.run()

# wait for user confirmation (useful if started via GUI)
# input(30*' '+'Finished, good bye !  Type <ret> to exit -> ')

print("\n*==* script " + sys.argv[0] + " finished " + time.asctime() + "\n")
