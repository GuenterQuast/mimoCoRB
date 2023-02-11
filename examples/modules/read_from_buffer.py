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
from mimocorb.buffer_control import BufferData

def read_from_buffer(source_list=None, sink_list=None,
                     observe_list=None, config_dict=None, **rb_info):
    """
    Read data from mimiCoRB buffer using the interface class mimo_control.BufferData

    :param input: configuration dictionary 

    For final processing of data, e.g. a summary or historgram of data items,
    a Thread is started which becomes active wenn the source is deactivated
    by clearing the multiporcessing Event source._active. This is necessary
    because reading data blocks when no new data is provided.   
    """
    readData = BufferData(source_list, config_dict, **rb_info)
    active_event = readData.source._active

    def summary():
        """
        Background thread to collect results - here only printing a summary
        """
        #print(" ->> process read_from_buffer: Summary thread started")

        # do nothing while data taking active
        while (active_event.is_set()):
            time.sleep(0.1)
            
        # print summary wehen Reader becomes inactive    
        print("\n ->> process 'read_from_buffer': SUMMARY")
        print("   last event seen: {:d}".format(int(last_event_number)))
        # total event, count, mean decay time and its uncertainty
        print("   received # of events: {:d}".format(count), 
              "   mean decay time: {:2g}".format(decay_time/count),
              "+/- {:1g}".format(np.sqrt(decay_time_sq - decay_time**2/count)/count) )
        sys.exit()
        
    count = 0
    decay_time = 0. 
    decay_time_sq = 0. 

    Thread(target = summary, args=[]).start()    
    
    # -- start collecting data
    while active_event.is_set():
        d = next( readData(), None )   # blocks until new data received!
        if d is not None:
            metadata = d[0]
            last_event_number = metadata[0]
            data = d[1]
            count = count+1
            t = data[0][0]
            decay_time += t 
            decay_time_sq += t*t
        else:            
            break
    
if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
