from . import mimo_buffer as bm
import time, numpy as np

class Source_to_buffer:
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
