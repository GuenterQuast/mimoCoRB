#! /usr/bin/env python3
"""main program controlling DAQ with buffer manager mimoCoRB

   Script to start live data capturing and processing 
   as specified in the 'setup.yaml' file.
"""
import os, sys, time
import argparse
import numpy as np
import shutil
import yaml
from pathlib import Path
from mimocorb.buffer_control import  buffer_control

    
if __name__ == '__main__': # ---------------------------------------------------------------------------
    
    print("Script: " + os.path.basename(sys.argv[0]))
    ## print("Python: ", sys.version, "\n".ljust(22, '-'))
    
    #  Setup command line arguments and help messages
    parser = argparse.ArgumentParser(
        description="start live data capturing and processing as specified in the 'setup.yaml' file")
    parser.add_argument("setup", type=str)
    arguments = parser.parse_args()

    #  Load setup yaml file
    if not arguments.setup:
        raise RuntimeError("No setup YAML file was specified!")
    else:
        setup_filename = arguments.setup
    try:
        with open(os.path.abspath(setup_filename), "r") as file:
            setup_yaml = yaml.load(file, Loader=yaml.FullLoader)  # SafeLoader
    except FileNotFoundError:
        raise FileNotFoundError("The setup YAML file '{}' does not exist!".format(setup_filename))
    except yaml.YAMLError:
        raise RuntimeError("An error occurred while parsing the setup YAML file '{}'!".format(setup_filename))

    # > Get start time
    start_time = time.localtime()
    
    # > Create the 'target' directory (with setup name and time code)
    template_name = Path(setup_filename).stem
    template_name = template_name[:template_name.find("setup")]
    directory_prefix = "target/" + template_name + "{:04d}-{:02d}-{:02d}_{:02d}{:02d}{:02d}/".format(
        start_time.tm_year, start_time.tm_mon, start_time.tm_mday,
        start_time.tm_hour, start_time.tm_min, start_time.tm_sec )
    os.makedirs(directory_prefix, mode=0o0770, exist_ok=True)
    # > Copy the setup.yaml into the target directory
    shutil.copyfile(os.path.abspath(setup_filename),
                    os.path.dirname(directory_prefix) + "/" + setup_filename)

    # > Separate setup_yaml into ring buffers and functions:
    ringbuffers_dict = setup_yaml['RingBuffer']
    parallel_functions_dict = setup_yaml['Functions']

    # > Set up all needed ring buffers
    bc = buffer_control(ringbuffers_dict, parallel_functions_dict, directory_prefix)
    ringbuffers = bc.setup_buffers()
    print("{:d} buffers created...  ".format(len(ringbuffers)), end='')
            
    # set-up  workers ...     
    bc.setup_workers()
    bc.display_layout()

    # ... and start all workers     
    process_list = bc.start_workers()
    print("{:d} workers started...  ".format(len(process_list)), end='')
    bc.display_functions()


    # begin of data acquisition -----
    # get runtime defined in config dictionary
    runtime = bc.runtime
    Nprocessed = 0

    now = time.time()
    if runtime != 0:
        # > As sanity check: Print the expected runtime (start date and finish date) in human readable form
        print("\nStart: ", time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(now)),
              " - end: ", time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(now + runtime)), '\n')
        while time.time() - now < runtime:
                             # This must not get too small!
                             #  All the buffer managers (multiple threads per ring buffer)
                             #  run in the main thread and may block data flow if execution time constrained!
            time.sleep(0.5)  
            buffer_status = ""
            for RB_name, buffer in ringbuffers.items():
                Nevents, n_filled, rate = buffer.buffer_status()
                if RB_name == 'RB_1': Nprocessed = Nevents
                buffer_status += ': '+ RB_name + " {:d} ({:d}) {:.3g}Hz) ".format(Nevents, n_filled, rate)
            print("Time remaining: {:.0f}s".format(now + runtime - time.time()) +
                "  - buffers:" + buffer_status, end="\r")
        # when done, first stop data flow
        bc.pause()
        print("\n      Execution time: {:.2f}s -  Events processed: {:d}".format(
                       int(100*(time.time()-now))/100., Nprocessed) )
        time.sleep(0.5)
        # set ending state to allow clean stop for all processes
        bc.set_ending()
        input("\n\n      Finished - type enter to exit -> ")

    else:  # > 'Batch mode' - processing end defined by an event
           #   (worker process exiting, e.g. no more events from file_source)
        run = True
        print("Batch mode - buffer manager keeps running until one worker process exits!\n")
        animation = ['|', '/', '-', '\\']
        animation_step = 0
        while run:
            time.sleep(0.5)
            buffer_status = ""
            for RB_name, buffer in ringbuffers.items():
                Nevents, n_filled, rate = buffer.buffer_status()
                if RB_name == 'RB_1': Nprocessed = Nevents
                buffer_status += ': '+ RB_name + " {:d} ({:d}) {:.3g}Hz".format(Nevents, n_filled, rate)
            print(" > {} ".format(animation[animation_step]) + buffer_status + 9*' ', end="\r")
            animation_step = (animation_step + 1)%4
            for p in process_list:
                if p.exitcode == 0:  # Wait until one processes exits 
                    run = False
                    break
        # stop data taking          
        bc.pause()
        print("\n      Execution time: {:.2f}s -  Events processed: {:d}".format(
                       int(100*(time.time()-now))/100., Nprocessed) )
        time.sleep(0.5)
        bc.set_ending()    
        input("\n\n      Finished - type enter to exit -> ")

    # -->   end of main loop < --

    print("\nSession ended, sending shutdown signal...")

    # -->   finally, shut-down all processes

    # some grace time for things to finish cleanly ... 
    time.sleep(1.0)
    # ... before shutting down
    bc.shutdown()

    print("      Finished - Good Bye")
