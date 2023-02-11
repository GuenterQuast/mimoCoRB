"""
**plot**: implementation of an observer for plotting waveforms 
"""
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.style as mplstyle
from cycler import cycler

# class to export data from observer
from mimocorb.buffer_control import ObserverData

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

    # properties of data source
    source_dict = observe_list[0]

    # evaluate config dictionary
    plot_title = config_dict["title"]    
    min_sleeptime = 1.0 if "min_sleeptime" not in config_dict else config_dict["min_sleeptime"] 

    sample_time_ns = config_dict['sample_time_ns']
    channel_range = 500 if 'channel_range' not in config_dict else \
            config_dict['channel_range']
    analogue_offset = 0. if 'analogue_offset' not in config_dict else \
            1000.*config_dict['analogue_offset']
    pre_trigger_samples = 0. if 'pre_trigger_samples' not in config_dict else \
            config_dict['pre_trigger_samples']
    pre_trigger_ns = pre_trigger_samples * sample_time_ns

    plot_length = source_dict['values_per_slot']
    total_time_ns = plot_length * sample_time_ns
            
    x_linspace = np.linspace(-pre_trigger_ns, total_time_ns - pre_trigger_ns,
                                      plot_length, endpoint=False)
    # skip iStep points when plotting data, resulting in 125 - 249 points 
    iStep = len(x_linspace)//250 + 1 
    
    # Create static part of figure
    # Turn on interactive mode for matplotlib
    figure, ax = plt.subplots(1, 1)
    figure.subplots_adjust(hspace=0.4)
    plt.title(plot_title) 

    ax.set_xlim(-pre_trigger_samples*sample_time_ns, 
                (plot_length-pre_trigger_samples)*sample_time_ns)
    ax.set_xlabel('Time (ns)')
    ax.set_ylim(-channel_range - analogue_offset,
                 channel_range - analogue_offset)
    ax.set_ylabel('Signal (mV)')
    plt.grid(color='grey', linestyle='--', linewidth=0.5)
        
    mplstyle.use('fast')
    bg = figure.canvas.copy_from_bbox(ax.bbox)
    channel_lines = []
    plt.style.context("seaborn")
    color_cycler = cycler(color=['blue', 'green', 'red', 'tab:orange'])
    ax.set_prop_cycle(color_cycler)
    plt.axvline(0., linestyle = ':', color='darkblue') # trigger time
    for dtype_name, dtype_type in source_dict['dtype']:
        line, = ax.plot(x_linspace[::iStep], np.zeros_like(x_linspace)[::iStep],
            marker='', linestyle='-', lw=1.5, alpha=0.5, label=dtype_name)
        channel_lines.append(line)
    plt.legend()
    plt.ion()
    plt.show()
    plt.draw()

    def update_graph(data):
        """"
        Update graphics, to be called by instance of Observer
        """

        # Use blitting to speed things up (we just want to redraw the line)
        figure.canvas.restore_region(bg)

        if data is not None:
            for i, line in enumerate(channel_lines):
                line.set_ydata(data[::iStep][source_dict['dtype'][i][0]] 
                              - analogue_offset)
                ax.draw_artist(line)
                # Finish the blitting process
                figure.canvas.blit(ax.bbox)    
            plt.pause(min(0.2, min_sleeptime))
        else:
            # data taking ended, finish
            pass # nothing to do 
    
    plotObserver = ObserverData(observe_list, config_dict, **rb_info)

    while True:
        data = next(plotObserver(), None)
        if data is not None:
            update_graph(data)
        else:
            break
    
if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
