"""
**file_source**: Read waveform data from file
"""

from mimocorb.buffer_control import rbImport
import numpy as np
import sys, time
from mimocorb.parquetReader import parquetReader

            
def tar_parquet_source(source_list=None, sink_list=None, observe_list=None,
                            config_dict=None, **rb_info):
    """
    Read real data from parquet in a tar file

    The class mimocorb.buffer_control/rbImport is used to interface to the
    newBuffer and Writer classes of the package mimoCoRB.mimo_buffer

    :param config_dict: configuration dictionary
  
      - path: (relative) path to source files in .tar, 
      - sleeptime: (mean) time between events
      - random: pick a random time between events according to a Poission process
      - number_of_samples, sample_time_ns, pretrigger_samples and analogue_offset
        describe the waveform data to be generated (as for oscilloscope setup) 
    """


    def yield_data():
        """
        Data generator to deliver raw pulse data from parquet files
        """

        while True:
            data = reader()
            if data is None: # reached end, exit process
                sys.exit()
            yield(data, None)

    # initialize file reader 
    reader = parquetReader(config_dict)
    # get configuration
    sink_dict = sink_list[0]
    number_of_channels = len(sink_dict["dtype"])
    number_of_values = sink_dict["values_per_slot"]
    reader.number_of_channels = number_of_channels
    reader.chnams = [sink_dict["dtype"][i][0] for i in range(number_of_channels)]
    # start mimoCoRB client
    fs = rbImport(sink_list=sink_list, config_dict=config_dict,
                  ufunc = yield_data, **rb_info)
    # print("** tar_parquet_source ** started, config_dict: \n", config_dict)
    fs()
