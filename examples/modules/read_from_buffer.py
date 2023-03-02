"""
**plot_variables_from_buffer**: example of a module reading data 
from a buffer and producing histograms of variables

Uses modules mimocorb.buffer_control.rbExport and mimocorb.plot_Histograms

Actions:

  - evaluate configuration dictionary
  - optional: start sub-process for histogramming
  - read and analyze data from buffer
  - optional: pass data to histogrammer
"""

import numpy as np
import sys, time

from mimocorb.histogram_buffer import plot_Histograms
from multiprocessing import Queue, Process
# module to read data from buffer 
from mimocorb.buffer_control import rbExport

def read_from_buffer(source_list=None, sink_list=None,
                     observe_list=None, config_dict=None, **rb_info):
    """
    Read data from mimiCoRB buffer using the interface class mimo_control.rbExport
    and show histograms of variables selectet in configuration dictionary

    :param input: configuration dictionary 
    """

    # evaluate configuration dictionary
    if "histograms" not in config_dict:
        hist_dict = None
    else:
      # set-up background process for plotting histograms  
        hist_dict = config_dict['histograms']
        varnams = config_dict['variables']
        title = "Histograms" if 'title' not in config_dict else config_dict['title'] 
        interval = 2. if 'interval' not in config_dict else config_dict['interval']
        nHist = len(hist_dict)    
        if nHist != len(varnams):
            raise SystemExit(" ERROR: lists of variables and histograms must have same length")
      # create an empty list of lists for data to be histogrammed
        histdata = [ [] for i in range(nHist)]
      # create a multiprocesssing Queue to tranfer information to plotting routine
        histQ = Queue(1)
      # start background process  
        histP = Process(name='Histograms', target = plot_Histograms, 
                    args=(histQ, hist_dict, 1000.*interval, title)) 
#                         data Queue, Hist.Desrc  interval    
        histP.start()

  # initialze access to mimo_buffer    
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
        #while not readData.source.data_available(): # wait for data to avoid blocking
        #    time.sleep(0.05)
        d = next( readData(), None )   # this blocks until new data provided !
        if d is not None:  # new data received ------
            metadata = d[1]
            last_event_number = metadata[0]
            deadtime_f += metadata[2]
            # 
            data = d[0]
            
            # - analyse (some of) the data        
            t = data[0]['decay_time']
            decay_time += t 
            decay_time_sq += t*t
            
            # - store and possibly transfer data to be histogrammed
            if hist_dict is not None and histP.is_alive():
              # retrieve histogram variables
                for i, vnam in enumerate(varnams):
                    histdata[i].append(data[0][vnam])
                if histQ.empty():
                    histQ.put(histdata)
                    histdata = [ [] for i in range(nHist)]

            # - count events        
            count = count+1      # ---- end processing data
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

    # stop background histogrammer
    if hist_dict is not None:
        histP.terminate()
    
if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
