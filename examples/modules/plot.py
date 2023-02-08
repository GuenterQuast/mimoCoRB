import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.style as mplstyle
from cycler import cycler

from mimocorb.buffer_control import ObserverData

matplotlib.use("TkAgg")

def plot_graph(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):

    source_dict = observe_list[0]

    # evaluate config dictionary
    plot_title = config_dict["title"]    
    sample_time_ns = config_dict['sample_time_ns']
    min_sleeptime = 1.0 if "min_sleeptime" not in config_dict else config_dict["min_sleeptime"] 
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
    data = np.zeros((source_dict['values_per_slot'], len(source_dict['dtype'])))


    # Turn on interactive mode for matplotlib
    plt.ion()
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
    channel_list = []
    plt.style.context("seaborn")
    color_cycler = cycler(color=['red', 'green', 'blue', 'tab:orange'])
    ax.set_prop_cycle(color_cycler)
    plt.axvline(0., linestyle = ':', color='darkblue') # trigger time
    for dtype_name, dtype_type in source_dict['dtype']:
        ch, = ax.plot(x_linspace, np.zeros_like(x_linspace),
            marker='', linestyle='-', lw=1.5, alpha=0.5, label=dtype_name)
        channel_list.append(ch)
    plt.legend()
    plt.show()
    plt.draw()

    def update_graph(data):
        """"
        Update graphics, to be called by instance of Oberver
        """

        # Use blitting to speed things up (we just want to redraw the line)
        figure.canvas.restore_region(bg)

        for i, ch in enumerate(channel_list):
            ch.set_ydata(data[:plot_length][source_dict['dtype'][i][0]] 
                              - analogue_offset)
            ax.draw_artist(ch)
            # Finish the blitting process
            figure.canvas.blit(ax.bbox)    
        plt.pause(0.2)
    
    plotObserver = ObserverData(observe_list, config_dict,  ufunc=update_graph, **rb_info)
    plotObserver()
    
if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
