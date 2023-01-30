import matplotlib
from mimocorb.observer_plot import PlotOscilloscope

matplotlib.use("TkAgg")


def plot_graph(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    oscilloscope = PlotOscilloscope(source_list, sink_list, observe_list, config_dict,  **rb_info)
    oscilloscope.start()
    
if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
