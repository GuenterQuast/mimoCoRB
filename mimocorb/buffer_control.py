"""
Collection of classes to set-up, manage and access ringbuffers
and associated functions
"""

from . import mimo_buffer as bm
from .bufferinfoGUI import bufferinfoGUI
from .activity_logger import Gen_logger

import time
import os
import sys
import shutil
import yaml
from pathlib import Path
import numpy as np
from numpy.lib import recfunctions as rfn
from multiprocessing import Process, active_children, Queue
import threading
import pandas as pd
import io
import tarfile
import logging


class buffer_control:
    """
    Set-up and management ringbuffers and associated sub-processes

    Class methods:

      - setup_buffers()
      - setup_workers()
      - start_workers()
      - pause()
      - resume()
      - shutdown()

    """

    def __init__(self, buffers_dict, functions_dict, function_config_dict, output_directory):
        """
        Class to hold and control mimoCoRB buffer objects

        :param buffers_dict: dictionary defining buffers RB_1, RB_2, ...
        :param functions_dict: dictionary defining functions FKT_1, FKT_2, ...
        :param function_config_dict: configuration dictionary for functions
        :param output_directory: directory prefix for copies of config files and daq output
        """

        self.buffers_dict = buffers_dict
        self.number_of_ringbuffers = len(buffers_dict) + 1
        self.function_config_dict = function_config_dict
        self.out_dir = output_directory

        self.functions_dict = functions_dict
        self.number_of_functions = len(self.functions_dict)

        self.workers_setup = False
        self.workers_started = False

        self.cumulative_pause_time = 0.0
        self.start_time = 0.0

        self.status = "Initialized"

    def setup_buffers(self):
        self.ringbuffers = {}
        self.ringbuffer_names = []
        for i in range(1, self.number_of_ringbuffers):
            # > Concescutive and concise ring buffer names are assumed! (aka: "RB_1", "RB_2", ...)
            RBnam = "RB_" + str(i)
            self.ringbuffer_names.append(RBnam)
            # > Check if the ring buffer exists in the setup_yaml file
            try:
                RB_exists = self.buffers_dict[i - 1][RBnam]
            except KeyError:
                raise RuntimeError("Ring buffer '{}' not found in setup congiguration!\n".format(RBnam))
            num_slots = self.buffers_dict[i - 1][RBnam]["number_of_slots"]
            num_ch = self.buffers_dict[i - 1][RBnam]["channel_per_slot"]
            data_type = self.buffers_dict[i - 1][RBnam]["data_type"]  # simple string type or list expected
            # > Create the buffer data structure (data type of the underlying buffer array)
            if type(data_type) is str:
                rb_datatype = np.dtype(data_type)
            elif type(data_type) is dict:
                rb_datatype = list()
                for key, value in data_type.items():
                    rb_datatype.append((value[0], np.dtype(value[1])))
            else:
                raise RuntimeError(
                    "Ring buffer data type '{}' is unknown! "
                    + "Please use canonical numpy data type names ('float', 'int', 'uint8', ...)"
                    + " or a list of tuples (see numpy.dtype()-API reference)".format()
                )

            # > Create and store the new ring buffer object (one per ringbuffer definition in the setup yaml file)
            self.ringbuffers[RBnam] = bm.NewBuffer(num_slots, num_ch, rb_datatype)

        self.status = "BuffersSet"
        return self.ringbuffers

    def setup_workers(self):
        """Set up all the (parallel) worker functions"""

        if self.workers_setup:
            print("Cannot setup wokers twice")
            return

        self.process_list = list()
        self.parallel_functions = {}
        config_dict_common = None

        # get configuration file and time or events per run
        self.runtime = 0 if "runtime" not in self.functions_dict[0]["Fkt_main"] else self.functions_dict[0]["Fkt_main"]["runtime"]
        self.runevents = 0 if "runevents" not in self.functions_dict[0]["Fkt_main"] else self.functions_dict[0]["Fkt_main"]["runevents"]

        if "config_file" in self.functions_dict[0]["Fkt_main"]:
            cfg_common = self.functions_dict[0]["Fkt_main"]["config_file"]
            # > If common config file is defined: copy it into the target directory ...
            shutil.copyfile(
                os.path.abspath(cfg_common),
                os.path.dirname(self.out_dir) + "/" + os.path.basename(cfg_common),
            )
            #    and and load the configuration
            config_dict_common = self._get_config(cfg_common)
            # if runtime and runevents defined, override previous value
            if "runtime" in config_dict_common["general"]:
                self.runtime = config_dict_common["general"]["runtime"]
            if "runevents" in config_dict_common["general"]:
                self.runevents = config_dict_common["general"]["runevents"]

        for i in range(1, self.number_of_functions):
            # > Concescutive and concise function names are assumed! (aka: "Fkt_1", "Fkt_2", ...)
            function_name = "Fkt_" + str(i)
            file_py_name = self.functions_dict[i][function_name]["file_name"]
            fkt_py_name = self.functions_dict[i][function_name]["fkt_name"]
            # print("Load: "+function_name)
            # print(" > "+file_py_name+" "+fkt_py_name)
            number_of_processes = self.functions_dict[i][function_name]["num_process"]
            try:
                assigned_ringbuffers = dict(self.functions_dict[i][function_name]["RB_assign"])
            except KeyError:
                assigned_ringbuffers = {}  # no ringbuffer assignment
                # TODO: Do we really want this behaviour? Functions without ring buffers will never
                # receive a 'shutdown()'-signal from the main thread, so they might run indefinitely
                # and block closing the main application
                # (for p in process_list: p.join() blocks until all processes terminate by themselfes!)

            # > Check if this function needs configuration
            # 1. from main setup file
            config_dict = {} if fkt_py_name not in self.function_config_dict else self.function_config_dict[fkt_py_name]
            # or 2. from common yaml config
            if fkt_py_name in config_dict_common:
                config_dict = config_dict_common[fkt_py_name]
            # or 3. from external yaml:
            if "config_file" in self.functions_dict[i][function_name]:
                cfg_file_name = self.functions_dict[i][function_name]["config_file"]
                # > if found, copy it over into the target directory
                shutil.copyfile(
                    os.path.abspath(cfg_file_name),
                    os.path.dirname(self.out_dir) + "/" + os.path.basename(cfg_file_name),
                )
                config_dict = self._get_config(cfg_file_name)
            if config_dict == {}:
                print("Warning: no configuration found for function '{}'!".format(fkt_py_name))

            # > Pass the target-directory created above to the worker function (so, if applicable,
            #   it can safe own data in this directory and everything is contained there)
            config_dict["directory_prefix"] = self.out_dir

            # > Prepare function arguments
            source_list = []
            sink_list = []
            observe_list = []

            # > Split ring buffers by usage (as sinks, sources, or observers) and instantiate the
            #   appropriate object to be used by the worker function  (these calls will return
            #   configuration dictionaries used by the bm.Reader(), bm.Writer() or bm.Observer() constructor)
            for key, value in assigned_ringbuffers.items():
                if value == "read":
                    # append new reader dict to the list
                    source_list.append(self.ringbuffers[key].new_reader_group())
                elif value == "write":
                    # append new writer dict to the list
                    sink_list.append(self.ringbuffers[key].new_writer())
                elif value == "observe":
                    # append new observer dict to the list
                    observe_list.append(self.ringbuffers[key].new_observer())

            if not source_list:
                source_list = None
            if not sink_list:
                sink_list = None
            if not observe_list:
                observe_list = None
            # > Create worker processes executing the specified functions in parallel
            function = self._import_function(file_py_name, fkt_py_name)
            self.parallel_functions["FKT_" + str(i)] = (
                fkt_py_name,
                number_of_processes,
                assigned_ringbuffers,
            )
            for k in range(number_of_processes):
                self.process_list.append(
                    Process(
                        target=function,
                        args=(source_list, sink_list, observe_list, config_dict),
                        kwargs=assigned_ringbuffers,
                        name=fkt_py_name,
                    )
                )

        self.workers_setup = True
        self.status = "WorkersSet"

    def start_workers(self):
        """start all of the (parallel) worker functions"""

        self.start_time = time.time()
        if self.workers_started:
            print("!! Workers already started - cannot start again")
            return

        # > To avoid potential blocking during startup, processes will be started in reverse
        #   data flow order (so last item in the processing chain is started first)
        self.process_list.reverse()

        for p in self.process_list:
            p.start()

        self.workers_started = True
        self.status = "Running"
        return self.process_list

    def display_layout(self):
        """Print list of buffers"""
        print("List of buffers")
        for name, buffer in self.ringbuffers.items():
            print(name, buffer.number_of_slots, buffer.values_per_slot)

    def display_functions(self):
        """Print list of functions and buffer associations"""
        print("List of functions")
        for key in self.parallel_functions:
            rb_assigned = self.parallel_functions[key][2]
            print(
                key,
                self.parallel_functions[key][0],
                "(" + str(self.parallel_functions[key][1]) + ")  ",
                rb_assigned,
            )

    def stop(self):
        """stop writing and reading data, allow processes to finish"""
        for nam, buf in self.ringbuffers.items():
            buf.set_ending()
        if self.status == "Paused":
            self.cumulative_pause_time += time.time() - self.pause_time
        self.status = "Stopped"

    def shutdown(self):
        """Delete buffers, stop processes by calling the shutdown()-Method of the buffer manager"""
        for nam, buf in self.ringbuffers.items():
            print("Shutting down buffer ", nam)
            buf.shutdown()
            buf.close()
            del buf

        # > All worker processes should have terminated by now
        for p in self.process_list:
            if p.is_alive():
                print("waiting 3s for process ", p.name, " to finish")
            p.join(3.0)

        # force temination of remaining processes
        for p in self.process_list:
            if p.is_alive():
                print("  !! killing active process ", p.name)
                p.terminate()
        #  else:
        #    print("process ", p.name, "ended by itself")

        # > delete remaining ring buffer references (so each buffer managers destructor gets called)
        del self.ringbuffers
        self.status = "Shutdown"

    def pause(self):
        """Pause data acquisition"""
        # disable writing to Buffer RB_1
        self.ringbuffers["RB_1"].pause()
        self.status = "Paused"
        self.pause_time = time.time()

    def resume(self):
        """Re-enable  data acquisition after pause"""
        # disable writing to Buffer RB_1
        if self.status == "Paused":
            self.ringbuffers["RB_1"].resume()
            self.status = "Running"
        else:
            print(" !!! Resume only possible from state 'Paused'")
        self.cumulative_pause_time += time.time() - self.pause_time

    # helper functions
    @staticmethod
    def _get_config(config_file):
        """
        Args:
            config_file: defined in main setup file (yaml)

        Returns: yaml configuration file content (dict)
        """
        with open(os.path.abspath(config_file), "r") as f:
            config_dict = yaml.load(f, Loader=yaml.FullLoader)  # SafeLoader
        return config_dict

    @staticmethod
    def _import_function(module_path, function_name):
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
                sys.path.remove(path_sys)
            else:
                module = __import__(py_module, globals(), locals(), fromlist=[function_name])
        except ImportError as ie:
            print("Import Error!", ie)
            return None
        return vars(module)[function_name]


# <-- end class buffer_control


class rbImport:
    """
    Read data from external source (e.g. front-end device, file, simulation, etc.)
    and put data in mimo_buffer. Data is read by calling a user-supplied generator
    function for data and metadata.
    """

    def __init__(self, sink_list=None, config_dict=None, ufunc=None, **rb_info):
        """
        Class to provide external input data to a buffer, usually "RB_1"

        :param sink_list: list of length 1 with dictionary for destination buffer
        :param observe_list: list of length 1 with dictionary for observer (not implemented yet)
        :param config_dict: application-specific configuration
        :param ufunc: user-supplied function to provide input data
        :param rb_info: dictionary with names and function (read, write, observe) of ring buffers
        """

        # sub-logger for this class
        self.logger = Gen_logger(__class__.__name__)
        # general part for each function (template)
        if sink_list is None:
            self.logger.error("Faulty ring buffer configuration passed, 'sink_list' missing!")
            raise ValueError("ERROR! Faulty ring buffer configuration passed ('sink_list' missing)!")

        self.sink = None
        for key, value in rb_info.items():
            if value == "read":
                self.logger.error("Reading buffers not foreseen!!")
                raise ValueError("ERROR! reading buffers not foreseen!!")
            elif value == "write":
                self.logger.info(f"Writing to buffer {sink_list[0]}")
                self.sink = bm.Writer(sink_list[0])
                if len(sink_list) > 1:
                    self.logger.error("More than one sink presently not foreseen!")
                    print("!!! More than one sink presently not foreseen!!")
            elif value == "observe":
                self.logger.error("Observer processes not foreseen!")
                raise ValueError("ERROR! obervers not foreseen!!")

        if self.sink is None:
            self.logger.error("Faulty ring buffer configuration passed. No sink found!")
            raise ValueError("Faulty ring buffer configuration passed. No sink found!")

        self.number_of_channels = len(self.sink.dtype)
        self.chnams = [self.sink.dtype[i][0] for i in range(self.number_of_channels)]

        self.event_count = 0
        self.T_last = time.time()

        if not callable(ufunc):
            self.logger.error("User-supplied function is not callable!")
            raise ValueError("ERROR! User-supplied function is not callable!")
        else:
            # set-up generator for the data
            self.userdata_generator = ufunc()

    def __call__(self):
        # start_data_capture

        while self.sink._active.is_set():
            # do not write data if in paused mode
            if self.sink._paused.is_set():
                time.sleep(0.1)
                continue

            self.event_count += 1

            # get new buffer and store event data and meta-data
            # no try-block to ease debugging of user code
            data, metadata = next(self.userdata_generator)
            if data is None:  # source exhausted
                break
            #            try:
            #                data, metadata = next(self.userdata_generator)
            #            except:
            #                logging.error("Error in user-supplied generator: cannot retrieve data and metadata")
            #                break

            timestamp = time.time_ns() * 1e-9  # in s as type float64
            T_data_ready = time.time()
            buffer = self.sink.get_new_buffer()
            # - fill data and metadata
            for i in range(self.number_of_channels):
                buffer[self.chnams[i]][:] = data[i]

            # - account for deadtime
            T_buffer_ready = time.time()
            deadtime = T_buffer_ready - T_data_ready
            deadtime_fraction = deadtime / (T_buffer_ready - self.T_last)
            if metadata is None:
                self.sink.set_metadata(self.event_count, timestamp, deadtime_fraction)
            else:
                self.sink.set_metadata(*metadata)  # tuple to parameter list

            self.T_last = T_buffer_ready
        # make sure last data entry is also processed
        self.sink.process_buffer()


# <-- end class rbImport


class rbPut:
    """
    Recieve data from external source (e.g. front-end device, file, simulation, etc.)
    and put data in mimo_buffer.

    Returns False if sink is not active
    """

    def __init__(self, sink_list=None, config_dict=None, ufunc=None, **rb_info):
        """
        Class to provide external input data to a buffer, usually "RB_1"

        :param sink_list: list of length 1 with dictionary for destination buffer
        :param observe_list: list of length 1 with dictionary for observer (not implemented yet)
        :param config_dict: application-specific configuration
        :param ufunc: user-supplied function to provide input data
        :param rb_info: dictionary with names and function (read, write, observe) of ring buffers
        """

        # sub-logger for this class
        self.logger = Gen_logger(__class__.__name__)

        # general part for each function (template)
        if sink_list is None:
            self.logger.error("Faulty ring buffer configuration passed, 'sink_list' missing!")
            raise ValueError("ERROR! Faulty ring buffer configuration passed ('sink_list' missing)!")

        self.sink = None
        for key, value in rb_info.items():
            if value == "read":
                self.logger.error("Reading buffers not foreseen!!")
                raise ValueError("ERROR! reading buffers not foreseen!!")
            elif value == "write":
                self.logger.info(f"Writing to buffer {sink_list[0]}")
                self.sink = bm.Writer(sink_list[0])
                if len(sink_list) > 1:
                    self.logger.error("More than one sink presently not foreseen!")
                    print("!!! More than one sink presently not foreseen!!")
            elif value == "observe":
                self.logger.error("Observer processes not foreseen!")
                raise ValueError("ERROR! obervers not foreseen!!")

        if self.sink is None:
            self.logger.error("Faulty ring buffer configuration passed. No sink found!")
            raise ValueError("Faulty ring buffer configuration passed. No sink found!")

        self.number_of_channels = len(self.sink.dtype)
        self.chnams = [self.sink.dtype[i][0] for i in range(self.number_of_channels)]

        self.event_count = 0
        self.T_last = time.time()

    def __call__(self, data, metadata):
        if self.sink._active.is_set() and data is not None:
            # do not write data if in paused mode
            if self.sink._paused.is_set():
                time.sleep(0.1)
                return

            T_data_ready = time.time()
            timestamp = time.time_ns() * 1e-9  # in s as type float64
            self.event_count += 1

            # get new buffer and store event data and meta-data
            buffer = self.sink.get_new_buffer()
            # - fill data and metadata
            for i in range(self.number_of_channels):
                buffer[self.chnams[i]][:] = data[i]

            # - account for deadtime
            T_buffer_ready = time.time()
            deadtime = T_buffer_ready - T_data_ready
            deadtime_fraction = deadtime / (T_buffer_ready - self.T_last)
            if metadata is None:
                self.sink.set_metadata(self.event_count, timestamp, deadtime_fraction)
            else:
                self.sink.set_metadata(*metadata)  # tuple to parameter list

            self.T_last = T_buffer_ready
        else:
            # make sure last data entry is also processed
            self.sink.process_buffer()

        return self.sink._active.is_set()


# <-- end class push_to_rb


class rbExport:
    """
    Read data from buffer and send to requesting client (via Python yield()).
    Data are provided by a generator function yielding data and metadata in
    the __call__() method of the class.
    """

    def __init__(self, source_list=None, config_dict=None, **rb_info):
        """
        Class acting as a python generator to extract data and send to client

        :param source_list: list of length 1 with dictionary for source buffer
        :param observe_list: list of length 1 with dictionary for observer (not implemented yet)
        :param config_dict: application-specific configuration (file name)
        :param rb_info: dictionary with names and function (read, write, observe) of
        ring buffers attached to this process
        """

        # general part for each function (template)
        if source_list is None:
            raise ValueError("Faulty ring buffer configuration passed ('source_list' missing)!")

        self.source = None
        for key, value in rb_info.items():
            if value == "read":
                self.source = bm.Reader(source_list[0])
            elif value == "write":
                raise ValueError("!ERROR Writing to buffer not foreseen!!")
            elif value == "observe":
                raise ValueError("!ERROR additional Observer presently not foreseen!!")

        if self.source is None:
            raise ValueError("Faulty ring buffer configuration passed. No source found!")

    def __call__(self):
        # sart reading and save to text file
        while self.source._active.is_set():
            if self.source.data_available():
                data = self.source.get()
                metadata = np.array(self.source.get_metadata())
                yield ((data, metadata))
            else:
                time.sleep(0.05)  # wait for data, avoid blocking !
        yield (None)

    def __del__(self):
        pass


# <-- end class rbExport


class rbTransfer:
    """Read data from input buffer, filter data and write to output buffer(s)
    Data is provided as the argument to a user-defined filter function
    returing None if data is to be rejected, a number if data is to
    be copied to another buffer, or a list of processed input data write
    to additional buffers.

    Args:

    - buffer configurations (only one source and severals sinks, no observers!)

    - function ufunc() must return

        -  None if data to be rejected,
        -  int if only raw data to be copied to sink[0]
        -  list of parameterized data to be copied to sinks[]

    Action:

        store accepted data in buffers

    """

    def __init__(self, source_list=None, sink_list=None, config_dict=None, ufunc=None, **rb_info):
        """
        Class to filter data in input buffer and transfer to output buffer(s)

        :param _list: list of length 1 with dictionary for source buffer
        :param _list: list with dictionary(ies) for destination buffer(s)
        :param observe_list: list of length 1 with dictionary for observer (not implemented yet)
        :param config_dict: application-specific configuration
        :param ufunc: user-supplied function to filter, process and store data
        :param rb_info: dictionary with names and function (read, write, observe) of ring buffers
        """

        if not callable(ufunc):
            self.logger.error("User-supplied function is not callable!")
            raise ValueError("ERROR! User-supplied function is not callable!")
        else:
            self.filter = ufunc  # external function to filter data
        #   get source
        if source_list is not None:
            self.reader = bm.Reader(source_list[0])
            if len(source_list) > 1:
                print("!!! more than one reader process currently not supported")
        else:
            self.reader = None

        #   get sinks and start writer process(es)
        if sink_list is not None:
            self.writers = []
            for i in range(len(sink_list)):
                self.writers.append(bm.Writer(sink_list[i]))
        else:
            self.writers = None

        if self.reader is None or self.writers is None:
            ValueError("ERROR! Faulty ring buffer configuration!!")

    def __call__(self):
        # process_data
        while self.reader._active.is_set():
            # Get new data from buffer ...
            input_data = self.reader.get()

            #  ... and process data with user-provided filter function
            filter_data = self.filter(input_data)
            # expected return values:
            #   None to discard data or
            #   List of structured numpy array(s)
            #      one array only: processed (compressed) data
            #      two arrays: 1st one is data in input format, 2nd one is processed data

            if filter_data is None:
                #  data rejected by filter
                continue

            save_input = False
            save_filter_processed = False
            #  filter passed, data is to be kept
            if isinstance(filter_data, (list, tuple)):
                save_filter_processed = True
                # got parameterizations to store
                if len(self.writers) > len(filter_data):
                    # also store input raw data
                    save_input = True
            else:
                save_input = True

            idx_out = 0
            if save_input:
                # store input data
                buf = self.writers[idx_out].get_new_buffer()
                for ch in input_data.dtype.names:
                    buf[ch] = input_data[ch]
                self.writers[idx_out].set_metadata(*self.reader.get_metadata())
                self.writers[idx_out].process_buffer()
                idx_out += 1

            if save_filter_processed:
                for d in filter_data:
                    if d is not None:
                        buf = self.writers[idx_out].get_new_buffer()
                        buf[:] = 0
                        for ch in d.dtype.names:
                            buf[ch] = d[ch]
                        self.writers[idx_out].set_metadata(*self.reader.get_metadata())
                        self.writers[idx_out].process_buffer()
                    idx_out += 1


# <-- end class rbTransfer


class rbProcess:
    """Read data from input buffer, filter data and write to output buffer(s)
    Data is provided as the argument to a user-defined filter function
    returing None if data is to be rejected, a list mapping to the output buffers.
    Each element of the list can contain None for not writing, True for raw data copy or
    a (list of) numpy structured array(s). If a list is provided, each element of the list
    is written to a separate slot of the output buffer.

    Args:

    - buffer configurations (only one source and severals sinks, no observers!)

    - function ufunc() must return

        -  None if data to be rejected,
        -  list mapping to the output buffers. Each element of the list can be
            -  None if data to be rejected
            -  True if raw data to be copied
            -  numpy structured array to be written to output buffer
            -  list of numpy structured arrays to be copied to output buffer: each element of the list into a slot.



    Action:

        store accepted data in buffers

    """

    def __init__(self, source_list=None, sink_list=None, config_dict=None, ufunc=None, **rb_info):
        """
        Class to filter data in input buffer and transfer to output buffer(s)

        :param _list: list of length 1 with dictionary for source buffer
        :param _list: list with dictionary(ies) for destination buffer(s)
        :param observe_list: list of length 1 with dictionary for observer (not implemented yet)
        :param config_dict: application-specific configuration
        :param ufunc: user-supplied function to filter, process and store data
        :param rb_info: dictionary with names and function (read, write, observe) of ring buffers
        """

        if not callable(ufunc):
            self.logger.error("User-supplied function is not callable!")
            raise ValueError("ERROR! User-supplied function is not callable!")
        else:
            self.filter = ufunc  # external function to filter data
        #   get source
        if source_list is not None:
            self.reader = bm.Reader(source_list[0])
            if len(source_list) > 1:
                print("!!! more than one reader process currently not supported")
        else:
            self.reader = None

        #   get sinks and start writer process(es)
        self.number_of_output_buffers = len(sink_list)
        if sink_list is not None:
            self.writers = []
            for i in range(self.number_of_output_buffers):
                self.writers.append(bm.Writer(sink_list[i]))
        else:
            self.writers = None

        if self.reader is None or self.writers is None:
            ValueError("ERROR! Faulty ring buffer configuration!!")

    def __call__(self):
        # process_data
        while self.reader._active.is_set():
            # Get new data from buffer ...
            input_data = self.reader.get()

            #  ... and process data with user-provided filter function
            filter_data = self.filter(input_data)
            # expected return values:
            #   None to discard data or
            #   List mapping to the output buffers. Each element of the list can be
            #       None: data to be rejected
            #       True: raw data to be copied
            #       numpy structured array: data to be written to output buffer
            #       list of numpy structured arrays: data to be copied to output buffer: each element of the list into a slot.

            if filter_data is None:
                #  data rejected by filter
                continue

            if len(filter_data) != self.number_of_output_buffers:
                ValueError("ERROR! Number of output buffers does not match number of filter return values!!")

            for i in range(self.number_of_output_buffers):
                if filter_data[i] is None:
                    #  data rejected by filter
                    continue
                if filter_data[i] is True:
                    #  raw data to be copied
                    buf = self.writers[i].get_new_buffer()
                    for ch in input_data.dtype.names:
                        buf[ch] = input_data[ch]
                    self.writers[i].set_metadata(*self.reader.get_metadata())
                    self.writers[i].process_buffer()
                elif isinstance(filter_data[i], (list, tuple)):
                    #  data to be copied to output buffer: each element of the list into a slot
                    for d in filter_data[i]:
                        if d is not None:
                            buf = self.writers[i].get_new_buffer()
                            buf[:] = 0
                            for ch in d.dtype.names:
                                buf[ch] = d[ch]
                            self.writers[i].set_metadata(*self.reader.get_metadata())
                            self.writers[i].process_buffer()
                else:
                    #  data to be written to output buffer
                    buf = self.writers[i].get_new_buffer()
                    buf[:] = 0
                    for ch in filter_data[i].dtype.names:
                        buf[ch] = filter_data[i][ch]
                    self.writers[i].set_metadata(*self.reader.get_metadata())
                    self.writers[i].process_buffer()


# <-- end class rbProcess


class rbDrain:
    """read data from ring buffer and sent to null"""

    def __init__(self, source_list=None, config_dict=None, **rb_info):
        """
        Class to extract data

        :param _list: list of length 1 with dictionary for source buffer
        :param observe_list: list of length 1 with dictionary for observer (not implemented yet)
        :param config_dict: application-specific configuration (file name)
        :param rb_info: dictionary with names and function (read, write, observe) of ring buffers
        """

        # general part for each reader (template)
        if source_list is None:
            raise ValueError("Faulty ring buffer configuration passed ('source_list' missing)!")

        self.source = None
        for key, value in rb_info.items():
            if value == "read":
                self.source = bm.Reader(source_list[0])
                if len(source_list) > 1:
                    print("!!! more than one reader process currently not supported")
            elif value == "write":
                print("!!! Writing to buffer not foreseen !!")
            elif value == "observe":
                print("!!! Observer processes not foreseen !!")

        if self.source is None:
            raise ValueError("Faulty ring buffer configuration passed. No source found!")

        self.filename = config_dict["directory_prefix"] + "/" + "message.txt"
        with open(self.filename, "w") as f:
            print("No output foreseen to be written by rbDrain()", file=f)

    def __del__(self):
        pass

    def __call__(self):
        # sart reading (and do nothing)
        while self.source._active.is_set():
            input_data = self.source.get()
            if input_data is None:
                break  # last event is none
        #  END
        print("\n ** rbDrain: end seen")


# <-- end class rbDrain


class rb_toTxtfile:
    """Save data to file in csv-format"""

    def __init__(self, source_list=None, config_dict=None, **rb_info):
        """
        Class to extract data and store in csv file

        :param _list: list of length 1 with dictionary for source buffer
        :param observe_list: list of length 1 with dictionary for observer (not implemented yet)
        :param config_dict: application-specific configuration (file name)
        :param rb_info: dictionary with names and function (read, write, observe) of ring buffers
        """

        # general part for each function (template)
        if source_list is None:
            raise ValueError("Faulty ring buffer configuration passed ('source_list' missing)!")
        if config_dict is None:
            raise ValueError("Faulty configuration passed ('config_dict' missing)!")

        self.source = None
        for key, value in rb_info.items():
            if value == "read":
                self.source = bm.Reader(source_list[0])
                if len(source_list) > 1:
                    print("!!! more than one reader process currently not supported")
            elif value == "write":
                print("!!! Writing to buffer not foreseen !!")
            elif value == "observe":
                print("!!! Observer processes not foreseen !!")

        if self.source is None:
            raise ValueError("Faulty ring buffer configuration passed. No source found!")

        if not (self.source.values_per_slot == 1):
            raise ValueError("LogToTxt can only save single buffer lines! " + "(Make sure: bm.Reader.values_per_slot == 1 )")

        self.filename = config_dict["directory_prefix"] + "/" + config_dict["filename"] + ".txt"
        if "header_alias" in config_dict:
            alias = config_dict["header_alias"]
        else:
            alias = {}

        # Construct header and corresponding dtype
        my_header = []
        my_dtype = []
        for dtype_name, dtype_type in self.source.metadata_dtype:
            if dtype_name in alias:
                my_header.append(alias[dtype_name])
            else:
                my_header.append(dtype_name)
            my_dtype.append(dtype_type)

        for dtype_name, dtype_type in self.source.dtype:
            if dtype_name in alias:
                my_header.append(alias[dtype_name])
            else:
                my_header.append(dtype_name)
            my_dtype.append(dtype_type)
        df_dict = {k: pd.Series(dtype=v) for k, v in zip(my_header, my_dtype)}
        self.df = pd.DataFrame(df_dict)
        self.df.to_csv(self.filename, sep="\t", index=False)
        # Now add one row to the data frame (the 'new row' to append to the file...)
        df_dict = {k: pd.Series([0], dtype=v) for k, v in zip(my_header, my_dtype)}
        self.df = pd.DataFrame(df_dict)

    def __del__(self):
        pass

    def __call__(self):
        # sart reading and save to text file
        while self.source._active.is_set():
            input_data = self.source.get()
            if input_data is None:
                break  # last event is none
            metadata = np.array(self.source.get_metadata())
            data = rfn.structured_to_unstructured(input_data[0])
            newline = np.append(metadata, data)
            self.df.iloc[0] = newline
            self.df.to_csv(self.filename, mode="a", sep="\t", header=False, index=False)
        #  END
        print("\n ** rb_toTxtfile: end seen")


# <-- end class rb_to_Textfile


class rb_toParquetfile:
    """Save data a set of parquet-files packed as a tar archive"""

    def __init__(self, source_list=None, config_dict=None, **rb_info):
        """
        Class to extract data and store in tar archive of parquet files

        :param source_list: list (length 1) with dictionary for source buffer
        :param observe_list: list of length 1 with dictionary for observer (not implemented yet)
        :param config_dict: application-specific configuration (file name)
        :param rb_info: dictionary with names and function (read, write, observe) of ring buffers
        """
        if source_list is None:
            raise ValueError("Faulty ring buffer configuration ('source_list' in missing)!")

        self.source = None
        for key, value in rb_info.items():
            if value == "read":
                self.source = bm.Reader(source_list[0])
                if len(source_list) > 1:
                    print("!!! more than one reader process currently not supported")

            elif value == "write":
                print("!!! Writing to buffer not foreseen!!")
            elif value == "observe":
                print("!!! Observer Process not foreseen!!")

        if self.source is None:
            raise ValueError("Faulty ring buffer configuration passed to 'rb_toParquetfile'!")

        if "filename" not in config_dict:
            raise ValueError("A 'filename' has to be provided to 'rb_toParquetfile'")
        else:
            self.filename = config_dict["filename"]

        tar_filename = config_dict["directory_prefix"] + "/" + config_dict["filename"] + ".tar"
        self.tar = tarfile.TarFile(tar_filename, "w")

    def __call__(self):
        # stard reading and save to tarred parquet file
        while self.source._active.is_set():
            # get data
            input_data = self.source.get()
            if input_data is None:
                break  # end if None received
            df = pd.DataFrame(data=input_data)
            counter, timestamp, deadtime = self.source.get_metadata()
            # convert to parquet format and append to tar-file
            ioBuffer = io.BytesIO()  # create a file-like object
            df.to_parquet(ioBuffer, engine="pyarrow")  # generate parquet format
            #    create a TarInfo object to write data to tar file with special name
            tarinfo = tarfile.TarInfo(name=self.filename + "_{:d}.parquet".format(counter))
            tarinfo.size = ioBuffer.getbuffer().nbytes
            ioBuffer.seek(0)  # reset file pointer
            self.tar.addfile(tarinfo, ioBuffer)  # add to tar-file

        # close file
        self.tar.close()
        # print("\n ** rb_toParquet: end seen")

    def __del__(self):
        self.tar.close()
        # print(" ** rb_toParquet: file closed")


# <-- end class rb_toParqeutfile


class rbObserver:
    """
    Deliver data from buffer to an observer process. A tuple (data, metadata)
    is provided by a generator function ( i.e. via yield()) implemented in
    the __call__() method of the class.
    """

    def __init__(self, observe_list=None, config_dict=None, **rb_info):
        """
        Class to extract data from buffer as an observer

        :param observe_list: list of length 1 with dictionary for Observer
        :param config_dict: application-specific configuration (minimum wait time)

        :return generator: implemented in __call__ method
        :rtype python generator
        :param rb_info: dictionary with names and function (read, write, observe) of ring buffers
        """

        if observe_list is None:
            raise ValueError("ERROR! Faulty ring buffer configuration")

        self.source = None
        for key, value in rb_info.items():
            if value == "read":
                print("!!! Reading buffer not foreseen!!")
            elif value == "write":
                print("!!! Writing to buffer not foreseen!!")
            elif value == "observe":
                self.source = bm.Observer(observe_list[0])
                if len(observe_list) > 1:
                    print("!!! More than one observer presently not foreseen!!")

        if self.source is None:
            print("ERROR! Faulty ring buffer configuration passed - no source buffer specified !")
            sys.exit()

        #  evaluate information from config dict to set sleep time
        self.min_sleeptime = 1.0 if "min_sleeptime" not in config_dict else config_dict["min_sleeptime"]

    def __call__(self):
        # sart reading and save to text file
        while True:
            # data = self.source.get() # use get() function
            data = self.source.dataQ.get()  # use queue directly
            if data is None:  # recieved none, end!
                break
            yield (data)
        # end seen, pass None
        yield (None)

    def __del__(self):
        pass


# <-- end class rbObserver


class rbWSObserver:
    """
    Deliver data from buffer to an observer process
    """

    def __init__(self, observe_list=None, config_dict=None, **rb_info):
        """
        Class to extract data from buffer as an observer

        :param observe_list: list of length 1 with dictionary for Observer
        :param config_dict: application-specific configuration (minimum wait time)

        :return generator: implemented in __call__ method
        :rtype python generator
        :param rb_info: dictionary with names and function (read, write, observe) of ring buffers
        """

        if observe_list is None:
            raise ValueError("ERROR! Faulty ring buffer configuration")

        self.source = None
        for key, value in rb_info.items():
            if value == "read":
                print("!!! Reading buffer not foreseen!!")
            elif value == "write":
                print("!!! Writing to buffer not foreseen!!")
            elif value == "observe":
                self.source = bm.Observer(observe_list[0])
                if len(observe_list) > 1:
                    print("!!! More than one observer presently not foreseen!!")

        if self.source is None:
            print("ERROR! Faulty ring buffer configuration passed - no source buffer specified !")
            sys.exit()

        #  evaluate information from config dict to set sleep time
        self.min_sleeptime = 1.0 if "min_sleeptime" not in config_dict else config_dict["min_sleeptime"]

        self.data_lock = threading.Lock()

        # Setup threading
        self.main_thread = threading.current_thread()
        self.parse_new_data = threading.Event()
        self.parse_new_data.set()
        self.new_data_available = threading.Event()
        self.new_data_available.set()
        self.wait_data_thread = threading.Thread(target=self._wait_data, args=(self.min_sleeptime,))
        self.wait_data_thread.start()

    def close(self):
        if threading.current_thread() == self.main_thread:
            # print(" > DEBUG: plot.close(). Observer refcount: {:d}".format(sys.getrefcount(self.source)))
            del self.source

    def __del__(self):
        if threading.current_thread() == self.main_thread:
            # print(" > DEBUG: plot.__del__(). Observer refcount: {:d}".format(sys.getrefcount(self.source)))
            del self.source

    def _wait_data(self, sleeptime=1.0):
        while self.parse_new_data.is_set():
            last_update = time.time()
            with self.data_lock:
                self.data = self.source.get()
            self.new_data_available.set()
            if self.data is None:
                # end process
                break
            # Limit refresh rate to 1/sleeptime
            _sleep_time = sleeptime - (time.time() - last_update)
            if _sleep_time > 0:
                time.sleep(_sleep_time)
        # print("DEBUG: plot.wait_data_thread can safely be joined!") #!

    def __call__(self):
        while True:
            if self.source._active.is_set():
                if self.new_data_available.is_set():
                    with self.data_lock:
                        yield (self.data)
                    if self.data is None:
                        print("None seen")
                        self.parse_new_data.clear()
                        self.wait_data_thread.join()
                    self.new_data_available.clear()
                if self.data is None:
                    self.parse_new_data.clear()
                    yield (None)
                if not self.source._active.is_set():
                    break
                time.sleep(self.min_sleeptime / 10)
            else:
                self.parse_new_data.clear()
                print(" new_data_available cleared")
                self.wait_data_thread.join()
                yield (None)
                break


# <-- end class rbWSObserver


class run_mimoDAQ:
    """
    Setup and run Data Aquisition suite with mimoCoRB buffer manager

    The layout of ringbuffers and associated functions is defined
    in a configuration file in yaml format.

    Functions:

      - setup()
      - run()
      - end()

    Data acquisition stops when either of the following conditions is met:

      - number of requested events processed
      - requested run-time reached
      - inuput source exhausted
      - end command issued from Keyboard or graphical interface

    """

    # --- helper classes for keyboard interaction -----

    def keyboard_input(self, cmd_queue):
        """Read keyboard input and send to Qeueu, runing as background-thread to avoid blocking"""

        while self.run:
            cmd_queue.put(input())

    @staticmethod
    class tc:
        """define terminal color codes"""

        k = "\033[1;30;48m"  # black
        r = "\033[1;31;48m"  # red
        g = "\033[1;32;48m"  # green
        y = "\033[1;33;48m"  # yellow
        b = "\033[1;34;48m"  # blue
        p = "\033[1;35;48m"  # pink
        c = "\033[1;36;48m"  # cyan
        B = "\033[1;37;48m"  # bold
        U = "\033[4;37;48m"  # underline
        E = "\033[1;37;0m"  # end color

    # --- end helpers ------------------------

    def __init__(self, setup_filename, verbose=2, debug=False):
        """
        Initialize ringbuffers and associated functions from main configuration file
        """
        self.debug = debug
        self.setup_filename = setup_filename
        self.verbose = verbose

        # set global logging level for all sub-logger used by this module
        Gen_logger.set_level(
            logging.DEBUG if debug else logging.WARNING,
        )
        # create sub-logger for this class
        self.logger = Gen_logger(__class__.__name__)

        # check for / read command line arguments and load DAQ configuration file
        try:
            with open(os.path.abspath(self.setup_filename), "r") as file:
                self.setup_dict = yaml.load(file, Loader=yaml.FullLoader)  # SafeLoader
        except FileNotFoundError:
            raise FileNotFoundError("Setup YAML file '{}' does not exist!".format(self.setup_filename))
        except yaml.YAMLError:
            raise RuntimeError("Error while parsing YAML file '{}'!".format(self.setup_filename))

        # set general options from input dictionary
        # - output directory prefix
        self.output_directory = "target" if "output_directory" not in self.setup_dict else self.setup_dict["output_directory"]
        # - allow keyboard control ?
        self.kbdcontrol = True if "KBD_control" not in self.setup_dict else self.setup_dict["KBD_control"]
        # - enable GUI ?
        self.GUIcontrol = True if "GUI_control" not in self.setup_dict else self.setup_dict["GUI_control"]

        # > Get start time
        start_time = time.localtime()

        # > Create a 'target' sub-directory for output of this run
        template_name = Path(self.setup_filename).stem
        template_name = template_name[: template_name.find("setup")]
        self.directory_prefix = (
            self.output_directory
            + "/"
            + template_name
            + "{:04d}-{:02d}-{:02d}_{:02d}{:02d}/".format(
                start_time.tm_year,
                start_time.tm_mon,
                start_time.tm_mday,
                start_time.tm_hour,
                start_time.tm_min,
            )
        )
        os.makedirs(self.directory_prefix, mode=0o0770, exist_ok=True)
        # > Copy the setup.yaml into the target directory
        shutil.copyfile(
            os.path.abspath(self.setup_filename),
            os.path.dirname(self.directory_prefix) + "/" + self.setup_filename,
        )

    def __del__(self):
        # print("run_mimoDAQ: destructor called")
        pass

    def setup(self):
        # > Separate setup_yaml into ring buffers and functions:
        ringbuffers_dict = self.setup_dict["RingBuffer"]
        parallel_functions_dict = self.setup_dict["Functions"]
        function_config_dict = {} if "FunctionConfigs" not in self.setup_dict else self.setup_dict["FunctionConfigs"]

        # > Set up ring buffers from dictionaries
        self.bc = buffer_control(ringbuffers_dict, parallel_functions_dict, function_config_dict, self.directory_prefix)
        self.ringbuffers = self.bc.setup_buffers()
        self.RBnames = self.bc.ringbuffer_names
        print("{:d} buffers created...  ".format(len(self.ringbuffers)), end="")

        # > set-up  workers
        self.bc.setup_workers()
        if self.verbose > 0:
            self.bc.display_layout()
            self.bc.display_functions()

    def end(self, twait=3.0):
        """
        clean shutdown of daq suite

        Arg:

            twait: waiting time for processes to finish before shutdown
        """
        #    first, stop data flow (in case it is still active)
        if self.bc.status == "Running":
            self.bc.pause()
            time.sleep(0.5)  # give some time for buffers to become empty

        # set ending state to allow clean ending for all processes
        if self.bc.status != "Stopped":
            self.bc.stop()
            time.sleep(twait)
        # shut-down all buffers
        self.bc.shutdown()

    def run(self):
        # start data taking loop
        self.run = True

        # strings for printout
        animation = ["|", "/", "-", "\\"]
        animstep = 0
        # terminal colors
        col_k = "\033[1;30;48m"  # grey
        col_r = "\033[1;31;48m"  # red
        col_g = "\033[1;32;48m"  # green
        col_y = "\033[1;33;48m"  # yellow color
        col_b = "\033[1;34;48m"  # blue
        col_p = "\033[1;35;48m"  # pink
        col_c = "\033[1;36;48m"  # cyan
        B = "\033[1;37;48m"  # bold
        U = "\033[4;37;48m"  # underline
        E = "\033[1;37;0m"  # end

        print(" - - - - -")
        self.cmdQ = None
        self.logQ = None
        self.RBinfoQ = None
        # set-up keyboard control
        if self.kbdcontrol or self.GUIcontrol:
            self.cmdQ = Queue()  # Queue for command input from keyboard
        if self.kbdcontrol:
            self.kbdthread = threading.Thread(name="kbdInput", target=self.keyboard_input, args=(self.cmdQ,)).start()
            print(col_c + "Keyboard control active" + E + "   type:")
            print("  " + col_b + "P<ret>" + E + " to pause")
            print("  " + col_b + "R<ret>" + E + " to resume")
            print("  " + col_b + "S<ret>" + E + " to stop")
            print("  " + col_b + "E<ret>" + E + " to end")
        if self.GUIcontrol:
            self.logQ = Queue()  # Queue for logging to buffer manager info display
            self.RBinfoQ = Queue(1)  # Queue Buffer manager info display
            self.maxrate = 4500.0
            self.interval = 1000.0  # update interval in ms
            self.RBinfo_proc = Process(
                name="bufferinfoGUI",
                target=bufferinfoGUI,
                args=(
                    self.cmdQ,
                    self.logQ,
                    self.RBinfoQ,
                    #                                              cmdQ     BM_logQue    BM_InfoQue
                    self.RBnames,
                    self.maxrate,
                    self.interval,
                ),
            )
            self.RBinfo_proc.start()
            print(col_c + "Graphical User Interface active " + E)

        if self.bc.runtime > 0:
            print(col_c + "Run ends after" + E, self.bc.runtime, "s")
        if self.bc.runevents > 0:
            print(col_c + "Run ends after" + E, self.bc.runevents, "events")

        # > start all workers
        self.process_list = self.bc.start_workers()
        self.start_time = self.bc.start_time
        n_workers = len(self.process_list)
        print("\n" + 8 * " " + "{:d} workers started - ".format(n_workers), time.asctime())

        # > activate data taking (in case it was started in paused mode)
        if self.bc.status == "Paused":
            self.bc.resume()

        # > begin data acquisition loop
        N_processed = 0
        deadtime = 0.0
        runtime = self.bc.runtime
        runevents = self.bc.runevents
        RBinfo = {}
        try:
            while self.run:
                stat = col_r + self.bc.status + E + " "
                if self.bc.status != "Stopped":
                    time_active = time.time() - self.start_time - self.bc.cumulative_pause_time
                tact_p1s = int(10 * (time.time() - self.start_time))  # int in 1s/10
                t_act = col_p + str(int(time_active)) + "s " + E
                buffer_status_color = stat + t_act
                buffer_status = time.asctime() + " " + self.bc.status + " " + str(int(time_active)) + "s  "
                # status update once per second
                if tact_p1s % 10 == 0 or len(RBinfo) == 0:
                    for RB_name, buffer in self.ringbuffers.items():
                        Nevents, n_filled, rate, av_deadtime = buffer.buffer_status()
                        if RB_name == "RB_1":
                            N_processed = Nevents
                            deadtime = av_deadtime
                        RBinfo[RB_name] = [Nevents, n_filled, rate]
                        buffer_status_color += (
                            col_k + RB_name + E + ": " + col_p + "{:d}".format(Nevents) + E + "({:d}) {:.3g}Hz ".format(n_filled, rate)
                        )
                        buffer_status += RB_name + ": " + "{:d}".format(Nevents) + "({:d}) {:.3g}Hz ".format(n_filled, rate)
                    if self.verbose > 1:
                        print(
                            " > {}  ".format(animation[animstep]) + buffer_status_color + 10 * " ",
                            end="\r",
                        )
                        animstep = (animstep + 1) % 4
                # print line to log every 60 s
                if self.GUIcontrol:
                    if self.bc.status != "Stopped":
                        if tact_p1s % 600 == 0:
                            if not self.logQ.full():
                                self.logQ.put(buffer_status)
                        # check if all workers are alive
                        all_active = sum([p.is_alive() for p in self.process_list]) == n_workers
                        if self.RBinfoQ.empty():  # update graphical info display
                            self.RBinfoQ.put(
                                (
                                    self.bc.status,
                                    time_active,
                                    N_processed,
                                    av_deadtime,
                                    RBinfo,
                                    all_active,
                                )
                            )
                # check if done --------------------------------------------------
                # - end command from keyboad or GUI ?
                if (self.kbdcontrol or self.GUIcontrol) and not self.cmdQ.empty():
                    cmd = self.cmdQ.get()
                    print("\n" + cmd)
                    if cmd == "S":
                        print("\n     Stop command recieved")
                        self.logQ.put(time.asctime() + " Run stopped")
                        self.bc.stop()
                    if cmd == "E":
                        print("\n     Exit command recieved - wait for shutdown")
                        self.run = False
                        break
                    elif cmd == "P":
                        print("\n     Pause command recieved")
                        self.logQ.put(time.asctime() + " Run paused")
                        self.bc.pause()
                    elif cmd == "R":
                        print("\n     Resume command recieved")
                        self.logQ.put(time.asctime() + " Run resumed")
                        self.bc.resume()

                # keep loop active while in stopped state
                if self.bc.status == "Stopped":
                    continue

                # - time limit reached ?
                if runtime > 0 and time_active >= runtime:
                    self.logQ.put(time.asctime() + " requested run time reached: run stopped")
                    print("\n Requested run time reached - setting 'Stopped' state ")
                    self.bc.stop()
                # - number of requested events collected ?
                if runevents > 0 and N_processed >= runevents:
                    self.logQ.put(time.asctime() + " requested number of events collected: run stopped")
                    print("\n Requested number of events reached - setting 'Stopped' state")
                    self.bc.stop()
                # - is writer source to 1st buffer exhausted ?
                if self.process_list[-1].exitcode == 0:
                    self.logQ.put(time.asctime() + " Run stopped")
                    print("\n Input source exhausted - setting 'Stopped' state")
                    self.bc.stop()

                time.sleep(0.1)  # <-- end while run:

        except KeyboardInterrupt:
            print("\n" + sys.argv[0] + ": keyboard interrupt - closing down cleanly ...")

        finally:
            # print End-of-Run statistics
            EoR_info = "\n      Execution time: {:.2f}s -  Events processed: {:d}".format(
                int(10 * (time.time() - self.start_time)) / 10.0, N_processed
            )
            if self.verbose > 0:
                print("\n" + EoR_info)
            if self.GUIcontrol:
                self.logQ.put(time.asctime() + " End of Run" + EoR_info)

            # stop and shutdown
            self.end(twait=2.0)
            if self.cmdQ is not None:  # remove all entries from command Q
                while not self.cmdQ.empty():
                    self.cmdQ.get()

            if self.kbdcontrol:
                print(30 * " " + "Finished, good bye !  Type <ret> to exit -> ")
            else:
                input(30 * " " + "Finished, good bye !  Type <ret> to exit -> ")

            if self.GUIcontrol and self.RBinfo_proc.is_alive():
                input(30 * " " + "Type <ret> again to close Run Control Window\n")
                self.RBinfo_proc.terminate()

    # get all active child processes
    active = active_children()
    for child in active:
        print(" !! Killing child process", child)
        child.terminate()


if __name__ == "__main__":  # ----------------------------------------------------------------------
    # example code to run a data acquitistion suite defined in a yaml config

    # execute via:   python3 -m mimocorb.buffer_control <config file>

    print("\n*==* script " + sys.argv[0] + " running \n")

    daq = run_mimoDAQ()

    daq.setup()

    daq.run()
