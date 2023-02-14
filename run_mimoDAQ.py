#! /usr/bin/env python3
"""
  **run_mimoDAQ** setup and run Data Aquisition with mimiCoRB buffer manager 

    - set-up of buffers from config file
    - set-up and start of associated processes
    - start and stop data taking

"""

import sys, os, time, yaml, shutil
from pathlib import Path
import numpy as np, threading
import multiprocessing as mp

# import mimoCoRB controller
from mimocorb.buffer_control import *

# !!!!
# import matplotlib.pyplot as plt
# !!!! matplot can only be used if no other active thread is using it 

# ------------------------------------------------------------
#     structure of buffers and related functions in .yaml-File
# ------------------------------------------------------------

# some helper functions 
def kbdwait():
    """ 
    running as a thread to wait for keyboard input
    """
    input(50*' '+'type <ret> to exit -> ')

def stop_processes(proclst):
    """
    Close all running processes at end of run
    """
    for p in proclst: # stop all sub-processes
        if p.is_alive():
            print('    terminating ' + p.name)
            p.terminate()
    else:
        print('    ' + p.name + ' terminated ')
    time.sleep(1.)

  
class run_mimoDAQ(object):
    """
    Setup and run Data Aquisition with mimiCoRB buffer manager   

    Functions:

      - setup
      - run
      - stop

    """

    def __init__(self, verbose=2):
        self.verbose = verbose

        # check for / read command line arguments and load DAQ configuration file
        if len(sys.argv)==2:
            self.setup_filename = sys.argv[1]
            try:
                with open(os.path.abspath(self.setup_filename), "r") as file:
                    setup_yaml = yaml.load(file, Loader=yaml.FullLoader)  # SafeLoader
            except FileNotFoundError:
                raise FileNotFoundError(
                    "Setup YAML file '{}' does not exist!".format(self.setup_filename))
            except yaml.YAMLError:
                raise RuntimeError(
                    "Error while parsing YAML file '{}'!".format(self.setup_filename))
        else: 
            raise FileNotFoundError("No setup YAML file provided")

        # > Get start time
        start_time = time.localtime()
    
        # > Create a 'target' directory for output of this run
        template_name = Path(self.setup_filename).stem
        template_name = template_name[:template_name.find("setup")]
        self.directory_prefix = "target/" + template_name + \
            "{:04d}-{:02d}-{:02d}_{:02d}{:02d}/".format(
            start_time.tm_year, start_time.tm_mon, start_time.tm_mday,
            start_time.tm_hour, start_time.tm_min)
        os.makedirs(self.directory_prefix, mode=0o0770, exist_ok=True)
        # > Copy the setup.yaml into the target directory
        shutil.copyfile(os.path.abspath(self.setup_filename),
                    os.path.dirname(self.directory_prefix) + "/" + self.setup_filename)
                    
        # > Separate setup_yaml into ring buffers and functions:
        self.ringbuffers_dict = setup_yaml['RingBuffer']
        self.parallel_functions_dict = setup_yaml['Functions']

    def setup(self):
                    
        # > Set up all needed ring buffers
        self.bc = buffer_control(self.ringbuffers_dict,
                                 self.parallel_functions_dict, self.directory_prefix)
        self.ringbuffers = self.bc.setup_buffers()
        print("{:d} buffers created...  ".format(len(self.ringbuffers)), end='')
            
        # > set-up  workers     
        self.bc.setup_workers()
        if self.verbose > 0:
            self.bc.display_layout()
            self.bc.display_functions()

    def run(self):                   

        # > start all workers     
        self.process_list = self.bc.start_workers()
        print("{:d} workers started...  ".format(len(self.process_list)), end='')
        self.start_time = time.time()

        N_processed = 0                
        runtime = self.bc.runtime
        runevents = self.bc.runevents
        animation = ['|', '/', '-', '\\']
        animstep = 0
        # data acquisition loop
        run = True
        try:
            if self.verbose > 1: print('\n')
            while run:
                time.sleep(0.5)

                for RB_name, buffer in self.ringbuffers.items():
                    Nevents, n_filled, rate = buffer.buffer_status()
                    if RB_name == 'RB_1': N_processed = Nevents
                time_active = time.time() - self.start_time

                if self.verbose > 1:
                    buffer_status = str(int(time_active))
                    for RB_name, buffer in self.ringbuffers.items():
                        buffer_status += 's : ' + RB_name \
                            + " {:d} ({:d}) {:.3g}Hz) ".format(Nevents, n_filled, rate)
                    print(" > {}  ".format(animation[animstep]) + buffer_status + 10*' ', end="\r")
                    animstep = (animstep + 1)%4

                # check if done
                if runtime > 0 and time_active >= runtime: run = False
                if runevents > 0 and N_processed >= runevents: run = False                        
                        
        except KeyboardInterrupt:
            print(sys.argv[0]+': keyboard interrupt - closing down ...')

        finally:
            # Stop and shut-down

            # when done, first stop data flow
            self.bc.pause()
                        
            # print statistics
            if self.verbose>0:
                print("\n\n      Execution time: {:.2f}s -  Events processed: {:d}".format(
                       int(100*(time.time()-self.start_time))/100., N_processed) )

            time.sleep(0.5)
            # set ending state to allow clean stop for all processes
            self.bc.set_ending()
            time.sleep(1.0)   # some grace time for things to finish cleanly ... 
            # ... before shutting down
            self.bc.shutdown()       
                  
if __name__ == "__main__": # - - - - - - - - - - - - - - - - - - - - - -

    print('\n*==* script ' + sys.argv[0] + ' running \n')

    daq = run_mimoDAQ()

    daq.setup()

    daq.run()
