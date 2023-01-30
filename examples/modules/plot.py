import matplotlib
from cycler import cycler
from mimocorb import mimo_buffer as bm
from multiprocessing import Lock, SimpleQueue
import threading 
import matplotlib.pyplot as plt
import matplotlib.style as mplstyle
import numpy as np
from scipy.stats import gaussian_kde
import time
import sys, os

matplotlib.use("TkAgg")

class PlotOscilloscope:
    def __init__(self, source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
        """plot wave-form data
        """

        plot_title = config_dict["title"]
        
        self.source = None

        if observe_list is None:
            raise ValueError("ERROR! Faulty ring buffer configuration (source in lifetime_modules: PlotOscilloscope)!!")

        for key, value in rb_info.items():
            if value == 'read':
                for i in range(len(source_list)):
                    pass
            elif value == 'write':
                for i in range(len(sink_list)):
                    pass
            elif value == 'observe':
                for i in range(len(observe_list)):
                    self.source = bm.Observer(observe_list[i])

        if self.source is None:
            print("ERROR! Faulty ring buffer configuration passed to 'PlotOscilloscope'!!")
            sys.exit()

        # evaluate config dictionary
        self.sample_time_ns = config_dict['sample_time_ns']
        min_sleeptime = 1.0 if "min_sleeptime" not in config_dict else config_dict["min_sleeptime"] 
        self.channel_range = 500 if 'channel_range' not in config_dict else \
            config_dict['channel_range']
        self.analogue_offset = 0. if 'analogue_offset' not in config_dict else \
            1000.*config_dict['analogue_offset']
        self.pre_trigger_samples = 0. if 'pre_trigger_samples' not in config_dict else \
            config_dict['pre_trigger_samples']
        self.pre_trigger_ns = self.pre_trigger_samples * self.sample_time_ns

        self.plot_length = self.source.values_per_slot
        self.total_time_ns = self.plot_length * self.sample_time_ns
            
        self.x_linspace = np.linspace(-self.pre_trigger_ns, self.total_time_ns-self.pre_trigger_ns,
                                      self.plot_length, endpoint=False)
        self.data = np.zeros((self.source.values_per_slot, len(self.source.dtype)))

        self.data_lock = threading.Lock()

        # Setup threading
        self.main_thread = threading.current_thread()
        self.parse_new_data = threading.Event()
        self.parse_new_data.set()
        self.new_data_available = threading.Event()
        self.new_data_available.set()
        self.wait_data_thread = threading.Thread(target=self._wait_data, args=(min_sleeptime,))
        self.wait_data_thread.start()

        # Turn on interactive mode for matplotlib
        plt.ion()
        self.figure, self.ax = plt.subplots(1, 1)
        self.figure.subplots_adjust(hspace=0.4)
        plt.title(plot_title) 

        self.ax.set_xlim(-self.pre_trigger_samples*self.sample_time_ns, 
                         (self.plot_length-self.pre_trigger_samples)*self.sample_time_ns)
        self.ax.set_xlabel('Time (ns)')
        self.ax.set_ylim(-self.channel_range - self.analogue_offset,
                          self.channel_range - self.analogue_offset)
        self.ax.set_ylabel('Signal (mV)')
        plt.grid(color='grey', linestyle='--', linewidth=0.5)
        
        mplstyle.use('fast')
        self.bg = self.figure.canvas.copy_from_bbox(self.ax.bbox)
        self.channel_list = []
        plt.style.context("seaborn")
        color_cycler = cycler(color=['red', 'green', 'blue', 'tab:orange'])
        self.ax.set_prop_cycle(color_cycler)
        plt.axvline(0., linestyle = ':', color='darkblue') # trigger time
        for dtype_name, dtype_type in self.source.dtype:
            ch, = self.ax.plot(self.x_linspace, np.zeros_like(self.x_linspace),
                    marker='', linestyle='-', lw=1.5, alpha=0.5, label=dtype_name)
            self.channel_list.append(ch)
        plt.legend()
        plt.show()
        plt.draw()

    def __del__(self):
        if threading.current_thread() == self.main_thread:
            # print(" > DEBUG: plot.__del__(). Observer refcount: {:d}".format(sys.getrefcount(self.source)))
            del self.source

    def _on_update(self):
        # Use blitting to speed things up (we just want to redraw the line)
        self.figure.canvas.restore_region(self.bg)
        # Update data
        with self.data_lock:
            for i, ch in enumerate(self.channel_list):
                ch.set_ydata(self.data[:self.plot_length][self.source.dtype[i][0]] 
                              - self.analogue_offset)
                self.ax.draw_artist(ch)
        # Finish the blitting process
        self.figure.canvas.blit(self.ax.bbox)    
        
    def _wait_data(self, sleeptime=1.0):
        while self.parse_new_data.is_set():
            last_update = time.time()
            with self.data_lock:
                self.data = self.source.get()
            self.new_data_available.set()
            # Limit refresh rate to 1/sleeptime
            _sleep_time = sleeptime - (time.time()-last_update)
            if _sleep_time > 0:
                time.sleep(_sleep_time)
        # print("DEBUG: plot.wait_data_thread can safely be joined!")

    def start(self):
        while self.source._active.is_set():
            plt.pause(0.2)
            if self.new_data_available.is_set():
                self._on_update()
                self.new_data_available.clear()
        self.parse_new_data.clear()
        plt.close('all')
        self.wait_data_thread.join()

        
class PlotKDE:
    def __init__(self, source_dict=None, sink_dict=None, config_dict=None, **add_dict):
        # general part for each function (template)
        self.source = None
        if source_dict is not None:
            pass
        if sink_dict is not None:
            pass
        #   define add dict variables (d<n>_r/w) necessary here while implementing this function!
        #   (here we assume 2 values, if more, change the code)
        if len(add_dict) != 0:
            for key, value in add_dict.items():
                if key == "read":
                    self.source = bm.Reader(value)
                elif key == "write":
                    pass

        if self.source is None:
            print("ERROR! Faulty ring buffer configuration passed!!")
            sys.exit()
        
        # General configuration
        self.plot_length = self.source.values_per_slot
        self.sample_time_ns = config_dict['sample_time_ns']
        timenow = time.localtime()
        self.filename = config_dict['filename']+"_{:04d}-{:02d}-{:02d}_{:02d}{:02d}{:02d}.txt".format(
            timenow.tm_year, timenow.tm_mon, timenow.tm_mday,
            timenow.tm_hour, timenow.tm_min, timenow.tm_sec
        )
        self.data = []
        
        # Turn on interactive mode for matplotlib
        plt.ion()
        self.figure, self.ax = plt.subplots()
        plt.title(config_dict["title"])
        self.ax.set_xlim(0, self.plot_length*self.sample_time_ns)
        self.x_linspace = np.arange(0, self.plot_length) * self.sample_time_ns
        self.graph = self.ax.plot([], [], marker='', linestyle='-')[0]
        self.graph.set_xdata(self.x_linspace)
        self.ax.set_xlabel('in ns')
        self.ax.set_ylim(0, 1)
        self.ax.set_ylabel('density')
        self.ax.grid(color='grey')
        mplstyle.use('fast')
        
        # Setup threading
        self.parse_new_data = threading.Event()
        self.parse_new_data.set()
        self.wait_data_thread = threading.Thread(target=self._wait_data)
        self.wait_data_thread.start()

    def __del__(self):
        self.parse_new_data.clear()
        self.wait_data_thread.join()
        plt.savefig(self.filename)
        plt.close(fig=self.figure)

    def _on_update(self):
        # Create KDE in scipy
        kde = gaussian_kde(self.data)
        y_data = kde.evaluate(self.x_linspace)
        self.graph.set_ydata(y_data)
        # Need both of these in order to rescale
        #self.ax.relim()
        #self.ax.autoscale_view()
        # We need to draw *and* flush
        self.figure.canvas.draw()
        #self.figure.canvas.flush_events()
        
    def _wait_data(self):
        last_update = time.time()
        while self.parse_new_data.is_set():
            pulse = self.source.get()
            self.data.append(pulse[0]['decay_time'])
            if time.time() > last_update + 1:
                self._on_update()
                last_update = time.time()

    def start(self):
        while self.source._active.is_set():
            plt.pause(0.2)



def plot_graph(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    oscilloscope = PlotOscilloscope(source_list, sink_list, observe_list, config_dict,  **rb_info)
    oscilloscope.start()

    
def plot_kde(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    kde_plot = PlotKDE(source_list, sink_list, observe_list, config_dict,  **rb_info)
    kde_plot.start()


    
if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
