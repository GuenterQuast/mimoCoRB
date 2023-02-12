"""
**plot**: plotting waveforms from buffer using mimoCoRB.buffer_control.OberserverData 
"""
import numpy as np
import matplotlib
import matplotlib.pyplot as plt, matplotlib.animation as anim
# class providing animated graphics
from mimocorb.plot_buffer import WaveformPlotter
# class to export data from observer
from mimocorb.buffer_control import ObserverData

# select matplotlib frontend if needed
matplotlib.use("TkAgg")

def plot_graph(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    """
    Plot waveform data from mimiCoRB buffer

    :param input: configuration dictionary 

      - plot_title: graphics title to be shown on graph
      - min_sleeptime: time between updates
      - sample_time_ns, channel_range, pretrigger_samples and analogue_offset
        describe the waveform data as for oscilloscope setup
    """

    # access to buffer data
    data_reader = ObserverData(observe_list, config_dict, **rb_info)
    active_event = data_reader.source._active

    source_dict = observe_list[0]
    osciplot = WaveformPlotter(conf_dict=config_dict, dtypes=source_dict['dtype'])

   # use simple, hand-made method to animate graphics
    plt.ion()
    plt.show()
    while active_event.is_set():
       data = next(data_reader(), None)
       if data is not None:
          channel_lines = osciplot(data) # update graphics
          osciplot.update_graph()
       else:
          # end if data generator is exhausted or deleted
          break
         
if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
