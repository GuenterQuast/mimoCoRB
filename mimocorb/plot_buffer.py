"""
Collection of classes with graphics functions to plot buffer data
"""
import numpy as np
import matplotlib.pyplot as plt, matplotlib.animation as anim
import matplotlib.style as mplstyle
from cycler import cycler
import time

# access to mimiCoRB Observer class
from .buffer_control import ObserverData


class WaveformPlotter(object):
    """
    Oscilloscope-like display of wave from buffer data

    The __call__ method of this class updates only the time-depenent
    input data and redraws the figure.
    """

    def __init__(self, conf_dict=None, dtypes=None, fig = None):
        """
        Oscilloscope-like display of wave from buffer data

        :param input: configuration dictionary containing
          - plot_title: graphics title to be shown on graph
          - min_sleeptime: time between updates
          - number_of_samples, sample_time_ns, channel_range, pretrigger_samples and
            analogue_offset describing the waveform data as for oscilloscope setup
        :param dtypes: names and data types of channels as 
        :type dtypes: list of tuples [('name', dtype), ...] for each channel
        :param fig: matplotlib figure object; a new one is created if None
        """

        self.conf_dict = conf_dict 
        self.dtypes = dtypes

        plot_title = '' if 'title' not in conf_dict else conf_dict["title"]    

        # Create figure object if needed
        if fig is None:
           self.fig = plt.figure(plot_title, figsize=(6., 4.5))
        else:
           self.fig = fig
                                
        # evaluate config dictionary
        sample_time_ns = self.conf_dict['sample_time_ns']
        channel_range = 500 if 'channel_range' not in self.conf_dict else \
            self.conf_dict['channel_range']
        self.analogue_offset = 0. if 'analogue_offset' not in self.conf_dict else \
            1000.*self.conf_dict['analogue_offset']
        pre_trigger_samples = 0. if 'pre_trigger_samples' not in self.conf_dict else \
            self.conf_dict['pre_trigger_samples']
        pre_trigger_ns = pre_trigger_samples * sample_time_ns
        plot_length = self.conf_dict['number_of_samples']
        total_time_ns = plot_length * sample_time_ns

        self.min_sleeptime = 1.0 if "min_sleeptime" not in self.conf_dict else \
            self.conf_dict["min_sleeptime"] 

        # Create static part of figure
        self.x_linspace = np.linspace(-pre_trigger_ns, total_time_ns - pre_trigger_ns,
                                      plot_length, endpoint=False)
        # skip iStep points when plotting data, resulting in 125 - 249 points 
        self.iStep = len(self.x_linspace)//250 + 1 
        self.ax = self.fig.add_subplot(1, 1, 1)
        self.fig.subplots_adjust(hspace=0.4)
        self.ax.set_title(plot_title) 
        self.ax.set_xlim(-pre_trigger_samples*sample_time_ns, 
                 (plot_length-pre_trigger_samples)*sample_time_ns)
        self.ax.set_xlabel('Time (ns)')
        self.ax.set_ylim(-channel_range - self.analogue_offset,
                  channel_range - self.analogue_offset)
        self.ax.set_ylabel('Signal (mV)')
        self.ax.grid(color='grey', linestyle='--', linewidth=0.5)
        
        mplstyle.use('fast')
        plt.style.context("seaborn")
        color_cycler = cycler(color=['blue', 'green', 'red', 'tab:orange'])
        self.ax.set_prop_cycle(color_cycler)
        self.ax.axvline(0., linestyle = ':', color='darkblue') # trigger time

        self.bg = self.fig.canvas.copy_from_bbox(self.ax.bbox)
        
        # line objects to be animated, i.e. updated in __call__()
        self.channel_lines = []
        for dtype_name, dtype_type in self.dtypes:
            line, = self.ax.plot( self.x_linspace[::self.iStep],
                                  np.zeros_like(self.x_linspace)[::self.iStep],
                                  marker='', linestyle='-', lw=1.5, alpha=0.5,
                                  label=dtype_name)
            self.channel_lines.append(line)            
        self.ax.legend(loc="upper right")

    def init(self):
        """plot initial line objects to be animated
        """ 
        return self.channel_lines

    def __call__(self, data):
        """
        Update graphics
        """
        for i, line in enumerate(self.channel_lines):
            line.set_ydata(data[::self.iStep][self.dtypes[i][0]]
                           - self.analogue_offset)
        # update graphics using  blitting to speed things up
        #        (just redraw lines)
        self.fig.canvas.restore_region(self.bg)
        for line in self.channel_lines:
            self.ax.draw_artist(line)
            # Finish the blitting process
            self.fig.canvas.blit(self.ax.bbox)    
        plt.pause(min(0.2, self.min_sleeptime))
        time.sleep(self.min_sleeptime)

# <<- end class WaveformPlotter

class plotWaveformBuffer():
    """
    Plot data using an mimiCoRB Observer 
    """    
    import matplotlib
    import matplotlib.pyplot as plt, matplotlib.animation as anim

    def __init__(self, source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
        """
        Plot waveform data from mimiCoRB buffer

        :param input: configuration dictionary 

          - plot_title: graphics title to be shown on graph
          - min_sleeptime: time between updates
          - sample_time_ns, channel_range, pretrigger_samples and analogue_offset
            describe the waveform data as for oscilloscope setup
        """

        # access to buffer data
        self.data_reader = ObserverData(observe_list, config_dict, **rb_info)
        self.active_event = self.data_reader.source._active

        self.source_dict = observe_list[0]
        self.osciplot = WaveformPlotter(conf_dict=config_dict, dtypes=self.source_dict['dtype'])

    def __call__(self):
        
        # animate graphics
        plt.ion()
        plt.show()
        while self.active_event.is_set():
           data = next(self.data_reader(), None)
           if data is not None:
              channel_lines = self.osciplot(data) # update graphics
           else:
              # end if data generator is exhausted or deleted
              break
        # done, exit  
        raise SystemExit
