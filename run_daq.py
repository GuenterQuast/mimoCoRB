#! /usr/bin/env python3
"""main program controlling DAQ with buffer manager mimoCoRB

   Script to start live data capturing and processing 
   as specified in the 'setup.yaml' file.
"""

import os
import sys
import argparse
import shutil
from pathlib import Path
import time
import numpy as np
import yaml
from multiprocessing import Process
from mimocorb import  mimo_buffer as bm, appl_lib as ua

def import_function(module_path, function_name):
    """
    Import a named object defined in a config yaml file from a module.

    Parameters:
        module_path (str): name of the python module containing the function/class
        function_name (str): python function/class name
    Returns:
        (obj): function/method name callable as object
    Raises:
        ImportError: returns None
    """
    try:
        path = Path(module_path)
        py_module = path.name
        res = path.resolve()
        path_sys = str(res).removesuffix(py_module)  # path to directory
        if path_sys not in sys.path:
            sys.path.append(path_sys)
        module = __import__(py_module, globals(), locals(), fromlist=[function_name])
    except ImportError as ie:
        print("Import Error!", ie)
        return None
    return vars(module)[function_name]


def get_config(config_file):
    """
    Args:
        config_file: defined in main_setup file (yaml) with fixed name key config_file

    Returns: yaml configuration file content (dict)
    """
    with open(os.path.abspath(config_file), "r") as f:
        config_str = yaml.load(f, Loader=yaml.FullLoader)  # SafeLoader
    return config_str

def setup_buffers(ringbuffers_dict):
    ringbuffers = {}
    for i in range(1, number_of_ringbuffers):
        # > Concescutive and concise ring buffer names are assumed! (aka: "RB_1", "RB_2", ...)
        ringbuffer_name = "RB_" + str(i)
        # > Check if the ring buffer exists in the setup_yaml file
        try:
            RB_exists = ringbuffers_dict[i-1][ringbuffer_name]
        except KeyError:
            raise RuntimeError("Ring buffer '{}' not found in setup file '{}'!\n".format(
                ringbuffer_name, setup_filename))
        num_slots = ringbuffers_dict[i-1][ringbuffer_name]['number_of_slots']
        num_ch = ringbuffers_dict[i-1][ringbuffer_name]['channel_per_slot']
        data_type = ringbuffers_dict[i-1][ringbuffer_name]['data_type']  # simple string type or list expected
        # > Create the buffer data structure (data type of the underlying buffer array)
        if type(data_type) == str:
            rb_datatype = np.dtype(data_type)
        elif type(data_type) == dict:
            rb_datatype = list()
            for key, value in data_type.items():
                rb_datatype.append( (value[0], np.dtype(value[1])) )
        else:
            raise RuntimeError("Ring buffer data type '{}' is unknown! " + 
               "Please use canonical numpy data type names ('float', 'int', 'uint8', ...)" +
               " or a list of tuples (see numpy.dtype()-API reference)".format(data_type))
        
        # > Create and store the new ring buffer object (one per ringbuffer definition in the setup yaml file)
        ringbuffers[ringbuffer_name] = bm.NewBuffer(num_slots, num_ch, rb_datatype)
    return ringbuffers
        
def setup_workers(parallel_functions_dict):
    # > Set up all the (parallel) worker functions
    process_list = list()
    number_of_functions = len(parallel_functions_dict)
    for i in range(1, number_of_functions):
        # > Concescutive and concise function names are assumed! (aka: "Fkt_1", "Fkt_2", ...)
        function_name = "Fkt_" + str(i)
        file_py_name = parallel_functions_dict[i][function_name]['file_name']
        fkt_py_name = parallel_functions_dict[i][function_name]['fkt_name']
        # print("Load: "+function_name)
        # print(" > "+file_py_name+" "+fkt_py_name)
        number_of_processes = parallel_functions_dict[i][function_name]['num_process']
        try:
            assigned_ringbuffers = dict(parallel_functions_dict[i][function_name]['RB_assign'])
        except KeyError:
            assigned_ringbuffers = {}  # no ringbuffer assignment
            # TODO: Do we really want this behaviour? Functions without ring buffers will never
            # receive a 'shutdown()'-signal from the main thread, so they might run indefinitely
            # and block closing the main application
            # (for p in process_list: p.join() blocks until all processes terminate by themselfes!)
        
        # > Prepare function arguments
        source_list = []
        sink_list = []
        observe_list = []
        config_dict = {}
        # > Check if this function needs external configuration (specified in a yaml file)
        try:
            # > Is there a function specific configuration file referenced in the setup_yaml? If yes, use this!
            cfg_file_name = parallel_functions_dict[i][function_name]['config_file']
        except KeyError:
            # > If there is no specific configuration file, see if there is function specific data
            # in the common configuration file
            try:
                config_dict = config_dict_common[fkt_py_name]
            except (KeyError, TypeError):
                print("Warning: no configuration found for file '{}'!".format(fkt_py_name))
                pass  # If both are not present, no external configuration is passed to the function 
        else:
            # > In case of a function specific configuration file, copy it over into the target directory
            shutil.copyfile(os.path.abspath(cfg_file_name),
                            os.path.dirname(directory_prefix) + "/" + os.path.basename(cfg_file_name))
            config_dict = get_config(cfg_file_name)

        # > Pass the target-directory created above to the worker function (so, if applicable,
        #   it can safe own data in this directory and everything is contained in this)
        config_dict["directory_prefix"] = directory_prefix
        
        # > Split ring buffers by usage (as sinks, sources, or observers) and instantiate the
        #   appropriate object to be used by the worker function  (these calls will return
        #   configuration dictionaries used by the bm.Reader(), bm.Writer() or bm.Observer() constructor)
        for key, value in assigned_ringbuffers.items():
            if value == 'read':
                # append new reader dict to the list
                source_list.append(ringbuffers[key].new_reader_group())
            elif value == 'write':
                # append new writer dict to the list
                sink_list.append(ringbuffers[key].new_writer())
            elif value == 'observe':
                # append new observer dict to the list
                observe_list.append(ringbuffers[key].new_observer())

        if not source_list:
            source_list = None
        if not sink_list:
            sink_list = None
        if not observe_list:
            observe_list = None
        # > Create worker processes executing the specified functions in parallel
        parallel_function = import_function(file_py_name, fkt_py_name)
        for k in range(number_of_processes):
            process_list.append(Process(target=parallel_function,
                                        args=(source_list, sink_list, observe_list, config_dict),
                                        kwargs=assigned_ringbuffers, name=fkt_py_name))
      # start worker processes 
      # > To avoid potential blocking during startup, processes are started in reverse data flow
      #   order (so last item in the processing chain is started first)
    process_list.reverse()
    for p in process_list:
        p.start()
    print("{:d} workers started...".format(len(process_list)))

    return process_list



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
        start_time.tm_hour, start_time.tm_min, start_time.tm_sec
    )
    os.makedirs(directory_prefix, mode=0o0770, exist_ok=True)
    # > Copy the setup.yaml into the target directory
    shutil.copyfile(os.path.abspath(setup_filename), os.path.dirname(directory_prefix) + "/" + setup_filename)

    # > Separate setup_yaml into ring buffers and functions:
    ringbuffers_dict = setup_yaml['RingBuffer']
    parallel_functions_dict = setup_yaml['Functions']
    number_of_ringbuffers = len(ringbuffers_dict) + 1

    # > Hook: possibility to execute user specific code "before ring buffer creation" 
    ua.appl_init()

    # > Set up all needed ring buffers

    ringbuffers = setup_buffers(ringbuffers_dict)
        
    # get configuration file and runtime
    runtime = 0 if 'runtime' not in  parallel_functions_dict[0]['Fkt_main'] else \
        parallel_functions_dict[0]['Fkt_main']

    if 'config_file' in parallel_functions_dict[0]["Fkt_main"]: 
        cfg_common = parallel_functions_dict[0]['Fkt_main']['config_file']
        # > If common config file is defined: copy it into the target directory ...
        shutil.copyfile(os.path.abspath(cfg_common),
                        os.path.dirname(directory_prefix) + "/" + os.path.basename(cfg_common))
        #    and and load the configuration
        config_dict_common = get_config(cfg_common)
        # if runtime defined, override previous value
        if 'runtime' in config_dict_common['general']: 
           runtime = config_dict_common['general']['runtime'] 

    # now start all workers     
    process_list = setup_workers(parallel_functions_dict)
  
    # begin of data acquisition -----
    now = time.time()
    Nprocessed = 0 
    if runtime != 0:
        # > As sanity check: Print the expected runtime (start date and finish date) in human readable form
        print("Start: ", time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(now)),
              " - end: ", time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(now + runtime)), '\n')
        while time.time() - now < runtime:
            time.sleep(0.5)  # This may not get too small! All the buffer managers (multiple threads per ring buffer) run in the main thread and may block data flow if execution time constrained!
            buffer_status = ""
            for RB_name, buffer in ringbuffers.items():
                Nevents, n_filled, rate = buffer.buffer_status()
                if RB_name == 'RB_1': Nprocessed = Nevents
                buffer_status += ': '+ RB_name + " {:3d} ({:d}) {:.4g}Hz) ".format(n_filled, Nevents, rate)
            print("Time remaining: {:.0f}s".format(now + runtime - time.time()) +
                "  - buffers:" + buffer_status, end="\r")
        print("\n      Execution time: {:.2f}s -  Events processed: {:d}".format(
                       int(100*(time.time()-now))/100., Nprocessed) )
    else:  # > 'Batch mode' - processing end defined by an event (worker process exiting, e.g. no more events from file_source)
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
        print("\n      Execution time: {:.2f}s -  Events processed: {:d}".format(
                       int(100*(time.time()-now))/100., Nprocessed) )
        input("\n\n      Finished - type enter to exit -> ")

    # -->   end of main loop < --

    print("\nSession ended, sending shutdown signal...")

    # -->   finally, shut-down all processes

    # > user defined application run after timer finished (can be ignored if not needed)
    ua.appl_after_start()

    # > End each worker process by calling the shutdown()-Method of the buffer manager
    for name, buffer in ringbuffers.items():
        buffer.shutdown()
        del buffer

    # > All worker processes should have terminated by now
    for p in process_list:
        p.join()        

    # > delete remaining ring buffer references (so each buffer managers destructor gets called)
    del ringbuffers

    # > user defined application run after all processing is finished (can be ignored if not needed)
    ua.appl_after_stop()

    print("      Finished - Good Bye")
