#! /usr/bin/env python3
"""
run mimoCoRB data acquisition suite
"""

import argparse
import sys
import time
from mimocorb.buffer_control import run_mimoDAQ

# define command line arguments ...
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("filename", nargs="?", default="demo_setup.yaml", help="configuration file")
parser.add_argument("-v", "--verbose", type=int, default=2, help="verbosity level (2)")
parser.add_argument("-d", "--debug", action="store_true", help="switch on debug mode (False)")
# ... and parse command line input
args = parser.parse_args()

print("\n*==* script " + sys.argv[0] + " running \n")

daq = run_mimoDAQ(args.filename, verbose=args.verbose, debug=args.debug)

daq.setup()

daq.run()

# wait for user confirmation (useful if started via GUI)
# input(30*' '+'Finished, good bye !  Type <ret> to exit -> ')

print("\n*==* script " + sys.argv[0] + " finished " + time.asctime() + "\n")
