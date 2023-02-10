import numpy as np
import time

# module to read data from buffer 
from mimocorb.buffer_control import BufferData

def read_from_buffer(source_list=None, sink_list=None,
                     observe_list=None, config_dict=None, **rb_info):

    print(" ->> process read_from_buffer: initializing")

    count = 0
    decay_time = 0 
    readData = BufferData(source_list, config_dict, **rb_info)
    while True:
        d = next( readData(), None )
        if d is not None:
            metadata = d[0]
            last_event_number = metadata[0]
            data = d[1]
            count = count+1
            decay_time += data[0][0]
        else:
            break

    # finally, print summary    
    print(" ->> process read_from_buffer: SUMMARY")
    print("   last event seen: ", last_event_number)
    print("   received # of events: ", count, 
          "   mean decay time: ", decay_time/count)
    
if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
