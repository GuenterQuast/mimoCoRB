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
from multiprocessing import Process
import pandas as pd
import io, tarfile

class buffer_control():
  """Set-up and management ringbuffers and associated sub-processes
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
    
    # get configuration file and runtime
    self.runtime = 0 if 'runtime' not in  self.functions_dict[0]['Fkt_main'] else \
        self.functions_dict[0]['Fkt_main']['runtime']

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
        self.parallel_functions['FKT_'+str(i)] = (fkt_py_name, number_of_processes)
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
          print(key, self.parallel_functions[key][0],
                '('+str(self.parallel_functions[key][1])+')')        

      
  def shutdown(self):
      """Delete buffers, stop processes by calling the shutdown()-Method of the buffer manager
      """
      for name, buffer in self.ringbuffers.items():
        print("Shutting down buffer ",name)
        buffer.shutdown()
        del buffer

      # > All worker processes should have terminated by now
      for p in self.process_list:
          p.join()        

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
    """Read data from source (e.g. file, simulation, Picoscope etc.) 
       and put data in mimo_buffer
    """

    def __init__(self, source_list=None, sink_list=None, observe_list=None, config_dict=None, ufunc=None, **rb_info):

        # general part for each function (template)
        if sink_list is None:
            raise ValueError("ERROR! Faulty ring buffer configuration!!")

        self.sink = None
        for key, value in rb_info.items():
            if value == 'read':
                for i in range(len(source_list)):
                    pass
            elif value == 'write':
                for i in range(len(sink_list)):
                    self.sink = bm.Writer(sink_list[i])
            elif value == 'observe':
                for i in range(len(observe_list)):
                    pass

        if self.sink is None:
            raise ValueError("ERROR! Faulty ring buffer configuration!!")

        self.number_of_channels = len(self.sink.dtype)

        self.get_data = ufunc
        self.event_count = 0
       
    def __del__(self):
        pass
        # TODO: remove debug or change to logger
        # print("?>", self.status)

    def __call__(self):
     # start_data_capture
        while True:
            self.event_count += 1

            # get new buffer abd store event data and meta-data
            buffer = self.sink.get_new_buffer()            
            data = self.get_data(self.number_of_channels)
            buffer[:]['chA'] = data[0]
            if self.number_of_channels > 1:
                buffer[:]['chB'] = data[1]
            if self.number_of_channels > 2:
                buffer[:]['chC'] = data[2]
            if self.number_of_channels > 3:
                buffer[:]['chD'] = data[3]            
            self.sink.set_metadata(self.event_count, time.time(), 0)
        self.sink.process_buffer()

# <-- end class SourceToBuffer


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
    def __init__(self, source_list=None, sink_list=None, observe_list=None, config_dict=None, ufunc=None, **rb_info):

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
            save_filtered = False
            #  filter passed, data is to be kept                      
            if isinstance(filter_data, (list, tuple)):
                save_filtered = True
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

            if save_filtered:    
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
    def __init__(self, source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
        # general part for each function (template)
        if source_list is None:
            raise ValueError("Faulty ring buffer configuration passed ('source_list' in save_files: LogToTxt missing)!")
        if config_dict is None:
            raise ValueError("Faulty configuration passed ('config_dict' in save_files: LogToTxt missing)!")

        self.source = None

        for key, value in rb_info.items():
            if value == 'read':
                for i in range(len(source_list)):
                    self.source = bm.Reader(source_list[i])
            elif value == 'write':
                for i in range(len(sink_list)):
                    pass
            elif value == 'observe':
                for i in range(len(observe_list)):
                    pass

        if self.source is None:
            raise ValueError("Faulty ring buffer configuration passed. No source found!")

        if not (self.source.values_per_slot == 1):
            raise ValueError("LogToTxt can only safe single buffer lines! (Make sure: bm.Reader.values_per_slot == 1 )")

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
    def __init__(self, source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
        if source_list is None:
            raise ValueError("Faulty ring buffer configuration ('source' in save_files: SaveBufferParquet missing)!")

        for key, value in rb_info.items():
            if value == 'read':
                for i in range(len(source_list)):
                    self.source = bm.Reader(source_list[i])
            elif value == 'write':
                for i in range(len(sink_list)):
                    pass
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
