"""Module save_files to handle file I/O for data in txt and parquet format
"""

from mimocorb import mimo_buffer as bm

import numpy as np
from numpy.lib import recfunctions as rfn
import pandas as pd
import sys
import os
import io
import tarfile


class LogToTxt:
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


class SaveBufferParquet:
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


# def save_to_txt(source_dict):
def save_to_txt(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    sv = LogToTxt(source_list, sink_list, observe_list, config_dict,  **rb_info)
    sv.start()


def save_parquet(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    sv = SaveBufferParquet(source_list, sink_list, observe_list, config_dict,  **rb_info)
    sv.start()


if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
