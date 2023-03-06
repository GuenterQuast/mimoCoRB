"""
**histogram_buffer** collection of classes to produce histograms

Show animated histogram(s) of scalar buffer variable(s)

Because this process runs as a 'Reader' process, the ploting function
is executed as a background task in order to avoid blockingn of the main task.



code adapted from https://github.com/GuenterQuast/picoDAQ
"""

import time, numpy as np
import itertools

import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt, matplotlib.animation as anim

from multiprocessing import Queue, Process
# module to read data from buffer 
from .buffer_control import rbExport

class animHists(object):
  """
  display histograms, as normalised frequency distibutions
  """

  def __init__(self, Hdescr, name='Histograms', fig=None):
    """ 
    Args:

      - list of histogram descriptors:

         - min:   minimum value
         - max:   maximum value
         - nbins: nubmer of bins
         -   ymax:  scale factor for highest bin (1. = 1/Nbins)
         - name:  name of the quantity being histogrammed
         - type:  0 linear, 1 for logarithmic y scale

      - name for figure window
      - fig:  optional external figure object; if not specified, a new
        internal one is generated
    """
  
    self.nHist = len(Hdescr)
    self.entries = np.zeros(self.nHist)
    self.frqs = []
    
  # histrogram properties
    self.mins = []
    self.maxs = []
    self.nbins = []
    self.ymxs = []
    self.names = []
    self.types = []
    self.bedges = []
    self.bcents = []
    self.widths = []
    for ih in range(self.nHist):
      self.mins.append(Hdescr[ih][0])
      self.maxs.append(Hdescr[ih][1])
      self.nbins.append(Hdescr[ih][2])
      self.ymxs.append(Hdescr[ih][3])
      self.names.append(Hdescr[ih][4])
      self.types.append(Hdescr[ih][5])
      be = np.linspace(self.mins[ih], self.maxs[ih], self.nbins[ih] +1 ) # bin edges
      self.bedges.append(be)
      self.bcents.append( 0.5*(be[:-1] + be[1:]) )                       # bin centers
      self.widths.append( 0.5*(be[1]-be[0]) )                           # bar width

  # create figure
    ncols = int(np.sqrt(self.nHist))
    nrows = ncols
    if ncols * nrows < self.nHist: nrows +=1
    if ncols * nrows < self.nHist: ncols +=1

    if fig is None:
      sf = 1. if ncols *nrows != 1 else 2.
      self.fig = plt.figure(name, figsize=(sf*3.*ncols, sf*2.*nrows) )
      axarray = self.fig.subplots(nrows=nrows, ncols=ncols)
      self.fig.subplots_adjust(left=0.25/ncols, bottom=0.25/nrows, right=0.975, top=0.95,
                             wspace=0.35, hspace=0.35)
    else:
        self.fig = fig

  # sort axes in linear array
    self.axes = []
    if self.nHist == 1:
      self.axes = [axarray]
    elif self.nHist == 2:
      for a in axarray:
        self.axes.append(a)
    else:
      nh = 0
      for ir in range(nrows):
        for ic in range(ncols):
          nh += 1
          if nh <= self.nHist:
            self.axes.append(axarray[ir,ic])
          else:
            axarray[ir,ic].axis('off')

    for ih in range(self.nHist):
      self.axes[ih].set_ylabel('frequency')
      self.axes[ih].set_xlabel(self.names[ih])
# guess an appropriate y-range for normalized histogram
      if self.types[ih]:            # log plot
        self.axes[ih].set_yscale('log')
        ymx=self.ymxs[ih]/self.nbins[ih] 
        self.axes[ih].set_ylim(1E-3 * ymx, ymx) 
        self.frqs.append(1E-4*ymx*np.ones(self.nbins[ih]) )
      else:                         # linear y scale
        self.axes[ih].set_ylim(0., self.ymxs[ih]/self.nbins[ih])
        self.frqs.append(np.zeros(self.nbins[ih]))
    
  def init(self):
    self.rects = []
    self.animtxts = []
    for ih in range(self.nHist):
    # plot an empty histogram
      self.rects.append(self.axes[ih].bar( self.bcents[ih], self.frqs[ih], 
           align='center', width=self.widths[ih], facecolor='midnightblue', alpha=0.7) )       
    # emty text
      self.animtxts.append(self.axes[ih].text(0.5, 0.925 , ' ',
              transform=self.axes[ih].transAxes,
              size='small', color='darkred') )

    graf_objects = tuple(self.animtxts) \
              + tuple(itertools.chain.from_iterable(self.rects) )  
    return graf_objects # return tuple of graphics objects

  def __call__(self, vals):

    if vals is None:
      # return old values if no new data
      return tuple(self.animtxts)  \
        + tuple(itertools.chain.from_iterable(self.rects) ) 
      
    # add recent values to frequency array, input is a list of arrays
    for ih in range(self.nHist):
      vs = vals[ih]
      self.entries[ih] += len(vs)
      for v in vs:
        iv = int(self.nbins[ih] * (v-self.mins[ih]) / (self.maxs[ih]-self.mins[ih]))
        if iv >=0 and iv < self.nbins[ih]:
          self.frqs[ih][iv]+=1
      if(len(vs)):
        norm = np.sum(self.frqs[ih]) # normalisation to one
    # set new heights for histogram bars
        for rect, frq in zip(self.rects[ih], self.frqs[ih]):
          rect.set_height(frq/norm)
    # update text
        self.animtxts[ih].set_text('Entries: %i'%(self.entries[ih]) )

    return tuple(self.animtxts)  \
        + tuple(itertools.chain.from_iterable(self.rects) ) 

def plot_Histograms(Q, Hdescripts, interval, name = 'Histograms'):
  """ 
  show animated histogram(s)

  Args:

  -  Q:    multiprocessing.Queue() 
  -  Hdescripts:  list of histogram descriptors, where each 
     descriptor is a list: 

       -   min:   minimum value
       -   max:   maximum value
       -   nbins: nubmer of bins
       -   ymax:  scale factor for highest bin (1. = 1/Nbins)
       -   name:  name of the quantity being histogrammed
       -   type:  0 linear, 1 for logarithmic y scale

  -  interval: time (in s) between updates
  -  name: name of histogram window
  """

  # Generator to provide data to animation
  def yieldData_fromQ():
  # receive data from multiprocessing Queue 
    cnt = 0
    try:
      while True:
#        while not Q.qsize(): 
#          time.sleep(0.1)
        if not Q.qsize():
          yield(None)
        else:  
          v = Q.get(timeout=0.1)
          yield v
        cnt+=1
    except:
      print('*==* yieldData_fromQ: termination signal received')
      return


# ------- executable part -------- 
#  print(' -> plot_Histograms starting')

  interval_ms = interval*1000.

#  try:
  H = animHists(Hdescripts, name)
  figH = H.fig
# set up matplotlib animation
  Hanim = anim.FuncAnimation(figH, H, yieldData_fromQ, 
                      init_func=H.init, interval=interval_ms, blit=True,
                      fargs=None, repeat=True, save_count=None)
                           # save_count=None is a (temporary) work-around 
                           #     to fix memory leak in animate
  plt.show()
  
#  except:
#    print('*==* plot_Histgrams: termination signal recieved')
  raise SystemExit

class histogram_buffer(object):
    """
    Read data from mimiCoRB buffer using the interface class mimo_control.rbExport
    and show histograms of variables selected in the configuration dictionary
    """

    def __init__(self, source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
        """
        Produce Histograms of (scalar) variables in buffer.
    
        Plotting is done by means of the class plot_Histograms() running as background process

        :param input: configuration dictionaries 
        """
       # evaluate configuration dictionary
        if "histograms" not in config_dict:
            self.hist_dict = None
        else:
         # set-up background process for plotting histograms  
            self.hist_dict = config_dict['histograms']
            self.varnams = config_dict['variables']
            self.title = "Histograms" if 'title' not in config_dict else config_dict['title'] 
            self.interval = 2. if 'interval' not in config_dict else config_dict['interval']
            self.nHist = len(self.hist_dict)    
            if self.nHist != len(self.varnams):
                raise SystemExit(" ERROR: lists of variables and histograms must have same length")
           # create a multiprocesssing Queue to tranfer information to plotting routine
            self. histQ = Queue()
           # start background process  
            self.histP = Process(name='Histograms', target = plot_Histograms, 
                                 args=(self.histQ, self.hist_dict, self.interval, self.title)) 
#                                       data Queue, Hist.Desrc  interval    
            self.histP.start()


      # initialze access to mimo_buffer    
        self.readData = rbExport(source_list=source_list, config_dict=config_dict, **rb_info)
        self.active_event = self.readData.source._active
        self.paused_event = self.readData.source._paused

        self.count = 0
        self.deadtime_f = 0.
        self.last_event_number = 0

    def __call__(self):
       # create an empty list of lists for data to be histogrammed
        histdata = [ [] for i in range(self.nHist)]

      #    while self.active_event.is_set():
        while True:
            d = next( self.readData(), None )   # this blocks until new data provided !
            if d is not None:  # new data received ------
                metadata = d[1]
                self.last_event_number = metadata[0]
                self.deadtime_f += metadata[2]
              # 
                data = d[0]   
              # - store and possibly transfer data to be histogrammed
                if self.hist_dict is not None and self.histP.is_alive():
              # retrieve histogram variables
                    for i, vnam in enumerate(self.varnams):
                        histdata[i] += (data[0][vnam],)  # appending tuple to list is faster than append()
                    if self.histQ.empty():
                        self.histQ.put(histdata)
                        histdata = [ [] for i in range(self.nHist)]
              # - count events        
                self.count += 1      # ---- end processing data
            else:            
                break

        # end-of-run action(s)
        # print summary when Reader becomes inactive    
        print("\n ->> process 'plot_buffer': SUMMARY")
        print("  received # of events: {:d}".format(self.count),
              "  last event seen: {:d}".format(int(self.last_event_number)),
              "  average deadtime: {:.1f}%".format(100*self.deadtime_f/max(1,self.count)) ) 

        # if histogrammer active, wait for shutdown to keep graphics window open
        #    (ending-state while paused_event is still set)
        if self.hist_dict is not None:
            while self.paused_event.is_set():
                time.sleep(0.3)
            self.histP.terminate()
