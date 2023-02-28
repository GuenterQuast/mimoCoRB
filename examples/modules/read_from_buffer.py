"""
**read_from_buffer**: example of a module reading and analyzing data 
from a buffer

Since reading blocks when no new data is available, a 2nd thread
is started to collect data at the end
"""

import numpy as np
from threading import Thread
import sys, time

# module to read data from buffer 
from mimocorb.buffer_control import rbExport

def read_from_buffer(source_list=None, sink_list=None,
                     observe_list=None, config_dict=None, **rb_info):
    """
    Read data from mimiCoRB buffer using the interface class mimo_control.rbExport

    :param input: configuration dictionary 

    """
    readData = rbExport(source_list=source_list, config_dict=config_dict, **rb_info)
    active_event = readData.source._active

    count = 0
    decay_time = 0. 
    decay_time_sq = 0.
    deadtime_f = 0.
    last_event_number = 0
    
    # -- start collecting data
#    while active_event.is_set():
    while True:
        #  expect  data, metadata) or None if end 
        d = next( readData(), None )   # blocks until new data received!
        if d is not None:
            metadata = d[1]
            last_event_number = metadata[0]
            deadtime_f += metadata[2]
            # 
            data = d[0]
            count = count+1
            t = data[0][0]
            decay_time += t 
            decay_time_sq += t*t
        else:            
            break

    # end-of-run action(s)
    # print summary when Reader becomes inactive    
    print("\n ->> process 'read_from_buffer': SUMMARY")
    print("   last event seen: {:d}".format(int(last_event_number)),
          " average deadtime: {:.1f}%".format(100*deadtime_f/max(1,count)) ) 
    # total event, count, mean decay time and its uncertainty
    print("   received # of events: {:d}".format(count),
          "   mean decay time: {:2g}".format(decay_time/max(1, count)),
          "+/- {:1g}".format(
              np.sqrt(decay_time_sq - decay_time**2/max(1,count))/max(1,count)) )

if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
