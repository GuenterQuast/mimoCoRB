from . import mimo_buffer as bm
import time, numpy as np
from collections.abc import Iterable
from numpy.lib import recfunctions as rfn
import pandas as pd
import io, tarfile

class SourceToBuffer:
    """Read data from source (e.g. file, simulation, Picoscope etc.) 
       and put data in mimo_buffer
    """

    def __init__(self, source_list=None, sink_list=None, observe_list=None, config_dict=None, data_source=None, **rb_info):

        # general part for each function (template)
        if sink_list is None:
            raise ValueError("ERROR! Faulty ring buffer configuration (sink in picoscope_source: OscilloscopeSource)!!")

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
            raise ValueError("ERROR! Faulty ring buffer configuration passed!")

        self.number_of_channels = len(self.sink.dtype)

        self.data_source = data_source
        self.event_count = 0
       
    def __del__(self):
        pass
        # TODO: remove debug or change to logger
        # print("?>", self.status)

    def start_data_capture(self):
        while True:
            self.event_count += 1

            # get new buffer abd store event data and meta-data
            buffer = self.sink.get_new_buffer()            
            data = self.data_source(self.number_of_channels)
            buffer[:]['chA'] = data[0]
            if self.number_of_channels > 1:
                buffer[:]['chB'] = data[1]
            if self.number_of_channels > 2:
                buffer[:]['chC'] = data[2]
            if self.number_of_channels > 3:
                buffer[:]['chD'] = data[3]            
            self.sink.set_metadata(self.event_count, time.time(), 0)
        self.sink.process_buffer()


class BufferToBuffer():
    """Read data from input buffer, filter and write to output buffer(s)       
    """
    def __init__(self, source_list=None, sink_list=None, observe_list=None, config_dict=None, filter=None, **rb_info):

        self.filter = filter  # external function to filter data
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
            ValueError("ERROR! Faulty ring buffer configuration (in lifetime_filter.calculate_decay_time)!!")


    def process_data(self):
        
        while self.reader._active.is_set():

           # Get new data from buffer ...
           input_data = self.reader.get()

           #  ... and process data with user-provided filter function
           filtered_data = self.filter(input_data)
           # expected return values:
           #   None to discard data or
           #   List of structured numpy array(s)
           #      one array only: processed (compressed) data
           #      two arrays: 1st one is data in input format, 2nd one is processed data
           
           if filtered_data is not None:
               if isinstance(filtered_data, Iterable):
                   if len(filtered_data)==2:
                     d_par = filtered_data[1]
                     d_raw = filtered_data[0]
               else:
                   d_par = filtered_data
                   d_raw = None
                   
               pulse_parameters = self.writers[1].get_new_buffer()
               pulse_parameters[:] = 0   # is this needed ?
               for ch in d_par.dtype.names:
                   pulse_parameters[ch] = d_par[ch]  
               self.writers[1].set_metadata(*self.reader.get_metadata())
               self.writers[1].process_buffer()     
             # Save the pulse waveform
               if d_raw is not None:
                   pulse_rawdata = self.writers[0].get_new_buffer()
                   for ch in d_raw.dtype.names:
                       pulse_rawdata[ch] = d_raw[ch]               
                   self.writers[0].set_metadata(*self.reader.get_metadata())
                   self.writers[0].process_buffer()
                 
    def __del__(self):
        pass
        # TODO: remove debug or change to logger
        # print("?>", self.status)


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

    def start(self):
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


    def start(self):
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

