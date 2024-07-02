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


    events_required = 1000 if "eventcount" not in config_dict else config_dict["eventcount"]
    
    def yield_data():
        """
        Data generator to deliver raw pulse data from parquet files
        """

        event_count = 0
        while events_required == 0 or event_count < events_required:
            data = reader()
            if data is None: # reached end, exit process
                sys.exit()
            yield(data, None)                


    reader = parquetReader(config_dict)        
    fs = rbImport(sink_list=sink_list, config_dict=config_dict,
                  ufunc = yield_data, **rb_info)
    reader.number_of_channels = len(fs.sink.dtype)
    number_of_channels = len(fs.sink.dtype)
    reader.number_of_channels = number_of_channels
    reader.chnams = [fs.sink.dtype[i][0] for i in range(number_of_channels)]

    # TODO: Change to logger!
    # print("** tar_parquet_source ** started, config_dict: \n", config_dict)
    # print("?> sample interval: {:02.1f}ns".format(fs.time_interval_ns.value))
    fs()
