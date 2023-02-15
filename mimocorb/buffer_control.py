"""
Collection of classes to set-up, manage and access ringbuffers
and associated access funtions 
"""

from . import mimo_buffer as bm
import time, os, sys, shutil
import yaml
from pathlib import Path
import numpy as np
from numpy.lib import recfunctions as rfn
from multiprocessing import Process, Queue
import threading
import pandas as pd
import io, tarfile

class buffer_control():
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

  def __init__(self, buffers_dict, functions_dict, output_directory):
      """
      Class to hold and control mimoCoRB buffer objects 

      :param buffers_dict: dictionary defining buffers RB_1, RB_2, ...
      :param functions_dict: dictionary defining functions FKT_1, FKT_2, ...
      :param output_directory: directory prefix for copies of config files and daq output
      """

      self.buffers_dict = buffers_dict
      self.number_of_ringbuffers = len(buffers_dict) + 1
      self.out_dir = output_directory
      
      self.functions_dict = functions_dict
      self.number_of_functions = len(self.functions_dict)

      self.workers_setup = False
      self.workers_started = False
      
  def setup_buffers(self):
    self.ringbuffers = {}
    for i in range(1, self.number_of_ringbuffers):
        # > Concescutive and concise ring buffer names are assumed! (aka: "RB_1", "RB_2", ...)
        ringbuffer_name = "RB_" + str(i)
        # > Check if the ring buffer exists in the setup_yaml file
        try:
            RB_exists = self.buffers_dict[i-1][ringbuffer_name]
        except KeyError:
            raise RuntimeError("Ring buffer '{}' not found in setup congiguration!\n".format(
                ringbuffer_name))
        num_slots = self.buffers_dict[i-1][ringbuffer_name]['number_of_slots']
        num_ch = self.buffers_dict[i-1][ringbuffer_name]['channel_per_slot']
        data_type = self.buffers_dict[i-1][ringbuffer_name]['data_type']  # simple string type or list expected
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
        self.ringbuffers[ringbuffer_name] = bm.NewBuffer(num_slots, num_ch, rb_datatype)
    return self.ringbuffers
    
  def setup_workers(self):
    """Set up all the (parallel) worker functions
    """

    if self.workers_setup:
      print("Cannot setup wokers twice")
      return

    self.process_list = list()
    self.parallel_functions = {}
    
    # get configuration file and time or events per run
    self.runtime = 0 if 'runtime' not in  self.functions_dict[0]['Fkt_main'] else \
        self.functions_dict[0]['Fkt_main']['runtime']
    self.runevents = 0 if 'runevents' not in  self.functions_dict[0]['Fkt_main'] else \
        self.functions_dict[0]['Fkt_main']['runevents']
    
    if 'config_file' in self.functions_dict[0]["Fkt_main"]: 
        cfg_common = self.functions_dict[0]['Fkt_main']['config_file']
        # > If common config file is defined: copy it into the target directory ...
        shutil.copyfile(os.path.abspath(cfg_common),
                        os.path.dirname(self.out_dir) + "/" + os.path.basename(cfg_common))
        #    and and load the configuration
        config_dict_common = self.get_config(cfg_common)
        # if runtime defined, override previous value
        if 'runtime' in config_dict_common['general']: 
            self.runtime = config_dict_common['general']['runtime'] 

    for i in range(1, self.number_of_functions):
        # > Concescutive and concise function names are assumed! (aka: "Fkt_1", "Fkt_2", ...)
        function_name = "Fkt_" + str(i)
        file_py_name = self.functions_dict[i][function_name]['file_name']
        fkt_py_name = self.functions_dict[i][function_name]['fkt_name']
        # print("Load: "+function_name)
        # print(" > "+file_py_name+" "+fkt_py_name)
        number_of_processes = self.functions_dict[i][function_name]['num_process']
        try:
            assigned_ringbuffers = dict(self.functions_dict[i][function_name]['RB_assign'])
        except KeyError:
            assigned_ringbuffers = {}  # no ringbuffer assignment
            # TODO: Do we really want this behaviour? Functions without ring buffers will never
            # receive a 'shutdown()'-signal from the main thread, so they might run indefinitely
            # and block closing the main application
            # (for p in process_list: p.join() blocks until all processes terminate by themselfes!)

        # > Check if this function needs external configuration (specified in a yaml file)
        config_dict = {}
        try:
            # > Use a function specific configuration file referenced in the setup_yaml?
            cfg_file_name = self.functions_dict[i][function_name]['config_file']
        except KeyError:
            # > If there is no specific configuration file, see if there is function specific data
            #   in the common configuration file
            try:
                config_dict = config_dict_common[fkt_py_name]
            except (KeyError, TypeError):
                print("Warning: no configuration found for file '{}'!".format(fkt_py_name))
                pass  # If both are not present, no external configuration is passed to the function 
        else:
            # > In case of a function specific configuration file, copy it over into the target directory
            shutil.copyfile(os.path.abspath(cfg_file_name),
                            os.path.dirname(self.out_dir) + "/" + os.path.basename(cfg_file_name))
            config_dict = self.get_config(cfg_file_name)

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
            if value == 'read':
                # append new reader dict to the list
                source_list.append(self.ringbuffers[key].new_reader_group())
            elif value == 'write':
                # append new writer dict to the list
                sink_list.append(self.ringbuffers[key].new_writer())
            elif value == 'observe':
                # append new observer dict to the list
                observe_list.append(self.ringbuffers[key].new_observer())

        if not source_list:
            source_list = None
        if not sink_list:
            sink_list = None
        if not observe_list:
            observe_list = None
        # > Create worker processes executing the specified functions in parallel
        function = self.import_function(file_py_name, fkt_py_name)
        self.parallel_functions['FKT_'+str(i)] = (fkt_py_name, number_of_processes, assigned_ringbuffers)
        for k in range(number_of_processes):
            self.process_list.append(Process(target=function,
                                        args=(source_list, sink_list, observe_list, config_dict),
                                        kwargs=assigned_ringbuffers, name=fkt_py_name))

    self.workers_setup = True     

  def start_workers(self):
    """start all of the (parallel) worker functions
    """

    if self.workers_started:
      print("Workers already started")
    
    # > To avoid potential blocking during startup, processes will be started in reverse
    #   data flow order (so last item in the processing chain is started first)
    self.process_list.reverse()
    
    for p in self.process_list:
        p.start()

    self.workers_started = True
    return self.process_list

  def display_layout(self):
      print("List of buffers")
      for name, buffer in self.ringbuffers.items():
          print(name, buffer.number_of_slots, buffer.values_per_slot)        

  def display_functions(self):
      print("List of functions")
      for key in self.parallel_functions:
          rb_assigned = self.parallel_functions[key][2]
          print(key, self.parallel_functions[key][0],
                '('+str(self.parallel_functions[key][1])+')  ',
                rb_assigned )

  def set_ending(self):
      """stop writing and reading data, allow processes to finish
      """
      for nam, buf in self.ringbuffers.items():
          buf.set_ending()

  def shutdown(self):
      """Delete buffers, stop processes by calling the shutdown()-Method of the buffer manager
      """
      for nam, buf in self.ringbuffers.items():
        print("Shutting down buffer ",nam)
        buf.shutdown()
        del buf

      # > All worker processes should have terminated by now
      for p in self.process_list:
          if p.is_alive(): print("waiting 3s for process ", p.name, " to finish") 
          p.join(3.)        

      # force temination of remaining processes    
      for p in self.process_list:
          if p.is_alive():
            print("  !! killing active process ", p.name)
            p.terminate()
            
      # > delete remaining ring buffer references (so each buffer managers destructor gets called)
      del self.ringbuffers

  def pause(self):
      """Pause data acquisition
      """
      # disable writing to Buffer RB_1
      self.ringbuffers['RB_1'].pause()

  def resume(self):
      """re-enable  data acquisition
      """
      # disable writing to Buffer RB_1
      self.ringbuffers['RB_1'].resume()

  #helper functions
  @staticmethod
  def get_config(config_file):
    """
    Args:
        config_file: defined in main_setup file (yaml) with fixed name key config_file

    Returns: yaml configuration file content (dict)
    """
    with open(os.path.abspath(config_file), "r") as f:
        config_str = yaml.load(f, Loader=yaml.FullLoader)  # SafeLoader
    return config_str

  @staticmethod
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
  
# <-- end class buffer_control


class SourceToBuffer:
    """
    Read data from source (e.g. file, simulation, Picoscope etc.) 
    and put data in mimo_buffer. 
    """

    def __init__(self, sink_list=None, observe_list=None, config_dict=None, ufunc=None, **rb_info):
        """
        Class to provide external input data to a buffer, usually "RB_1"

        :param sink_list: list of length 1 with dictionary for destination buffer 
        :param observe_list: list of length 1 with dictionary for observer (not implemented yet)
        :param config_dict: application-specific configuration 
        :param ufunc: user-supplied function to provide input data
        :param rb_info: dictionary with names and function (read, write, observe) of ring buffers
        """ 

        # general part for each function (template)
        if sink_list is None:
            raise ValueError("ERROR! Faulty ring buffer configuration!!")
          
        self.sink = None
        for key, value in rb_info.items():
            if value == 'read':
                raise ValueError("ERROR! reading buffes not foreseen!!")              
            elif value == 'write':
                for i in range(len(sink_list)):
                    self.sink = bm.Writer(sink_list[i])
            elif value == 'observe':
                for i in range(len(observe_list)):
                    pass

        if self.sink is None:
            raise ValueError("ERROR! Faulty ring buffer configuration!!")

        self.number_of_channels = len(self.sink.dtype)

        self.get_data_from_ufunc = ufunc
        self.event_count = 0
       
    def __del__(self):
        pass
        # TODO: remove debug or change to logger
        # print("?>", self.status)

    def __call__(self):
     # start_data_capture
        while self.sink._active.is_set():
            # do not write data if in paused mode
            if self.sink._paused.is_set():
              time.sleep(0.1)
              continue
            
            self.event_count += 1

            # get new buffer abd store event data and meta-data
            buffer = self.sink.get_new_buffer()            
            data = self.get_data_from_ufunc(self.number_of_channels)
            self.sink.set_metadata(self.event_count, time.time(), 0)
            buffer[:]['chA'] = data[0]
            if self.number_of_channels > 1:
                buffer[:]['chB'] = data[1]
            if self.number_of_channels > 2:
                buffer[:]['chC'] = data[2]
            if self.number_of_channels > 3:
                buffer[:]['chD'] = data[3]
        # make sure last data entry is processed        
        self.sink.process_buffer()

# <-- end class SourceToBuffer


class BufferData:
    """
    Read data from buffer and send to requesting client (via python yield())
    """

    def __init__(self, source_list=None, observe_list=None, config_dict=None, **rb_info):
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
          raise ValueError("Faulty ring buffer configuration passed ('source_list' missing!")

        self.source = None
        for key, value in rb_info.items():
            if value == 'read':
                self.source = bm.Reader(source_list[0])
            elif value == 'write':
                raise ValueError("!ERROR Writing to buffer not foreseen!!")
            elif value == 'observe':
                for i in range(len(observe_list)):
                    pass

        if self.source is None:
            raise ValueError("Faulty ring buffer configuration passed. No source found!")

    def __call__(self):
        # sart reading and save to text file
        while self.source._active.is_set():
            if self.source.data_available():
                data = self.source.get()
                metadata = np.array(self.source.get_metadata())
                yield ( (metadata, data) )
            else:
                time.sleep(0.05) # wait for data, avoid blocking !               
        yield(None)
            
    def __del__(self):
        pass

# <-- end class BufferData



class BufferToBuffer():
    """Read data from input buffer, filter data and write to output buffer(s)

       Args: 

       - buffer configurations (only one source and severals sinks, no observers!)

       - function ufunc() must return

           -  None if data to be rejected, 
           -  int if only raw data to be copied to sink[0]
           -  list of parameterized data to be copied to sinks[]

       Action:

           store accepted data in buffers
             
    """
    def __init__(self, source_list=None, sink_list=None, observe_list=None,
                 config_dict=None, ufunc=None, **rb_info):
        """
        Class to filter data in input buffer and transfer to output buffer(s)

        :param _list: list of length 1 with dictionary for source buffer 
        :param _list: list with dictionary(ies) for destination buffer(s) 
        :param observe_list: list of length 1 with dictionary for observer (not implemented yet)
        :param config_dict: application-specific configuration 
        :param ufunc: user-supplied function to filter, process and store data
        :param rb_info: dictionary with names and function (read, write, observe) of ring buffers
        """ 

        self.filter = ufunc  # external function to filter data
      #   get source 
        if source_list is not None:
            self.reader = bm.Reader(source_list[0])
        else:
            self.reader = None

      #   get sinks and start writer process(es) 
        if sink_list is not None:
            self.writers = []    
            for i in range(len(sink_list) ):
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
                 
    def __del__(self):
        pass
        # TODO: remove debug or change to logger
        # print("?>", self.status)

# <-- end class BufferToBuffer


class BufferToTxtfile:
    """Save data to file in csv-format
    """
      
    def __init__(self, source_list=None, observe_list=None, config_dict=None, **rb_info):
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
            if value == 'read':
                for i in range(len(source_list)):
                    self.source = bm.Reader(source_list[i])
            elif value == 'write':
                raise ValueError("!ERROR Writing to buffer not foreseen!!")
            elif value == 'observe':
                for i in range(len(observe_list)):
                    pass

        if self.source is None:
            raise ValueError("Faulty ring buffer configuration passed. No source found!")

        if not (self.source.values_per_slot == 1):
            raise ValueError("LogToTxt can only safe single buffer lines! " +\
                             "(Make sure: bm.Reader.values_per_slot == 1 )")

        self.filename = config_dict["directory_prefix"]+"/"+config_dict["filename"]+".txt"
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
        df_dict = {k:pd.Series(dtype=v) for k,v in zip(my_header, my_dtype)}
        self.df = pd.DataFrame(df_dict)
        self.df.to_csv(self.filename, sep="\t", index=False)
        # Now add one row to the data frame (the 'new row' to append to the file...)
        df_dict = {k:pd.Series([0], dtype=v) for k,v in zip(my_header, my_dtype)}
        self.df = pd.DataFrame(df_dict)

    def __del__(self):
        pass

    def __call__(self):
        # sart reading and save to text file
        input_data = self.source.get()
        while self.source._active.is_set():
            metadata = np.array(self.source.get_metadata())
            data = rfn.structured_to_unstructured(input_data[0])
            newline = np.append(metadata, data)
            self.df.iloc[0] = newline
            self.df.to_csv(self.filename, mode='a', sep="\t", header=False, index=False)
            input_data = self.source.get()

            
class BufferToParquetfile:
    """Save data a set of parquet-files packed as a tar archive
    """
    def __init__(self, source_list=None, observe_list=None, config_dict=None, **rb_info):
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
            if value == 'read':
                for i in range(len(source_list)):
                    self.source = bm.Reader(source_list[i])
            elif value == 'write':
                raise ValueError("!ERROR Writing to buffer not foreseen!!")
            elif value == 'observe':
                for i in range(len(observe_list)):
                    pass
                  
        if self.source is None:
            raise ValueError("Faulty ring buffer configuration passed to 'SaveBufferParquet'!")

        if not "filename" in config_dict:
            raise ValueError("A 'filename' has to be provided to 'SaveBufferParquet' the config_dict!")
        else:
            self.filename = config_dict["filename"]

        tar_filename = config_dict["directory_prefix"]+"/"+config_dict["filename"]+".tar"
        self.tar = tarfile.TarFile(tar_filename, "w")


    def __call__(self):
        # stard reading and save to tarred parquet file
        while self.source._active.is_set():
            # get data
            input_data = self.source.get()
            df = pd.DataFrame(data=input_data)
            counter, timestamp, deadtime = self.source.get_metadata()
            # convert to parquet format and append to tar-file
            ioBuffer = io.BytesIO()                    # create a file-like object 
            df.to_parquet(ioBuffer, engine='pyarrow')  # generate parquet format
            #    create a TarInfo object to write data to tar file with special name
            tarinfo = tarfile.TarInfo(name=self.filename+"_{:d}.parquet".format(counter))
            tarinfo.size = ioBuffer.getbuffer().nbytes
            ioBuffer.seek(0)                           # reset file pointer
            self.tar.addfile(tarinfo, ioBuffer)        # add to tar-file
    
    def __del__(self):
        self.tar.close()

# <-- end class BufferToTxtfile

class ObserverData:
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
            raise ValueError("ERROR! Faulty ring buffer configuration" +\
                             "(source in lifetime_modules: PlotOscilloscope)!!")
        if len(observe_list)!=1:
            raise ValueError("!ERROR only one observer source supported!!")            
        
        self.source = None
        for key, value in rb_info.items():
            if value == 'read':
                raise ValueError("!ERROR Reading buffer not foreseen!!")
            elif value == 'write':
                raise ValueError("!ERROR Writing to buffer not foreseen!!")
            elif value == 'observe':
                self.source = bm.Observer(observe_list[0])
        if self.source is None:
            print("ERROR! Faulty ring buffer configuration passed to 'PlotOscilloscope'!!")
            sys.exit()

        #  evaluate information from config dict     
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
            # Limit refresh rate to 1/sleeptime
            _sleep_time = sleeptime - (time.time()-last_update)
            if _sleep_time > 0:
                time.sleep(_sleep_time)
        # print("DEBUG: plot.wait_data_thread can safely be joined!")

    def __call__(self):
        while True:
            time.sleep(self.min_sleeptime/10)
            if self.source._active.is_set():
                if self.new_data_available.is_set():
                    with self.data_lock:
                        yield (self.data)
                    self.new_data_available.clear()
            else:
                self.parse_new_data.clear()
                self.wait_data_thread.join()
                yield(None)
                break

# <-- end class ObserverData


class run_mimoDAQ(object):
    """
    Setup and run Data Aquisition with mimiCoRB buffer manager   

    Functions:

      - setup
      - run
      - stop
    """

  # --- helper classes for keyboard interaction -----
    def keyboard_input(self, cmd_queue):
        """ Read keyboard input, run as background-thread to avoid blocking """

        while self.status != "Stopped":
            cmd_queue.put(input())

    @staticmethod        
    class tc:
        """define terminal color codes"""
        r = '\033[1;31;48m'
        g = '\033[1;32;48m'  # green color
        b = '\033[1;34;48m'
        k = '\033[1;30;48m'
        y = '\033[1;33;48m'   # yellow color
        p = '\033[1;35;48m'
        c = '\033[1;36;48m'
        B = '\033[1;37;48m'   # bold
        U = '\033[4;37;48m'   # underline
        E = '\033[1;37;0m'    # end color

  # --- end helpers ------------------------
  
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

    def stop(self, N):
        # Stop and shut-down
        #  when done, first stop data flow
        self.bc.pause()
                        
        # print statistics
        if self.verbose>0:
            print("\n\n      Execution time: {:.2f}s -  Events processed: {:d}".format(
                   int(100*(time.time()-self.start_time))/100., N) )
    
        time.sleep(0.5) # give some time for buffers to become empty

        # set ending state to allow clean stop for all processes
        self.bc.set_ending()
        time.sleep(1.0)   # some grace time for things to finish cleanly ... 
        # ... before shutting down
        self.bc.shutdown()
                  
    def run(self):                   
        # start data taking loop
        self.status = "Setup"

        # allow keyboard control
        self.kbdcontrol = True
        # strings for printout
        animation = ['|', '/', '-', '\\']
        animstep = 0
        # terminal colors 
        r = '\033[1;31;48m'
        g = '\033[1;32;48m'  # green color
        b = '\033[1;34;48m'
        k = '\033[1;30;48m'
        y = '\033[1;33;48m'   # yellow color
        p = '\033[1;35;48m'
        c = '\033[1;36;48m'
        B = '\033[1;37;48m'   # bold
        U = '\033[4;37;48m'   # underline
        E = '\033[1;37;0m'    # end color
        
        # set-up keyboard control
        if self.kbdcontrol:
            cmdQ = Queue(1)  # Queue for command input from keyboard
            kbdthrd = threading.Thread(name='kbdInput', target=self.keyboard_input, args=(cmdQ,)).start()
            print("\n" + b + "Keyboard control active" +E)
            print("  type:")
            print("  " + b + "E<ret>" + E + " to end")
            print("  " + b + "P<ret>" + E + " to pause")
            print("  " + b + "R<ret>" + E + " to resume \n")

        # > start all workers     
        self.process_list = self.bc.start_workers()
        print("{:d} workers started...  ".format(len(self.process_list)), end='')

        # > activate data taking (in case it was started in paused mode)
        self.start_time = time.time()
        self.bc.resume()
        
        # > begin data acquisition loop
        N_processed = 0                
        runtime = self.bc.runtime
        runevents = self.bc.runevents
        run = True
        self.status = "Running"
        try:
            if self.verbose > 1: print('\n')
            while run:
                time.sleep(0.5)

                stat = B+g+ self.status + E + ' '
                time_active = time.time() - self.start_time
                t_act = B+r+ str(int(time_active))+'s ' + E
                buffer_status = stat + t_act 
                for RB_name, buffer in self.ringbuffers.items():
                    Nevents, n_filled, rate = buffer.buffer_status()
                    if RB_name == 'RB_1': N_processed = Nevents
                    if self.verbose > 1:
                        buffer_status += B+k+ RB_name +E + ": " +\
                           B+b+ "{:d}".format(Nevents) +E + "({:d}) {:.3g}Hz ".format(n_filled, rate)
                        print(" > {}  ".format(animation[animstep]) + buffer_status + 10*' ', end="\r")
                        animstep = (animstep + 1)%4

                # check if done
                # - time limit reached ?
                if runtime > 0 and time_active >= runtime: run = False
                # - number of requested events accumulated ?   
                if runevents > 0 and N_processed >= runevents: run = False
                # - is writer source to 1st buffer exhausted ?   
                if self.process_list[-1].exitcode == 0: run = False
                # - End command from keyboad
                if self.kbdcontrol and not cmdQ.empty():
                    cmd = cmdQ.get()
                    print("\n" + cmd)
                    if cmd == 'E':
                        print("\n     Exit command recieved from Keyboard \n")
                        run = False
                        self.status = 'Stopped'
                    elif cmd == 'P':
                        print("\n     Pause command recieved from Keyboard \n")
                        self.bc.pause()
                        self.status = "Paused"
                    elif cmd == 'R':
                        print("\n     Resume command recieved from Keyboard \n")
                        self.status = "Running"
                        self.bc.resume()

        except KeyboardInterrupt:
            print('\n'+sys.argv[0]+': keyboard interrupt - closing down cleanly ...')

        finally:

            self.stop(N_processed)
