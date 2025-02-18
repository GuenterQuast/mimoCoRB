"""
**plot_buffer** Collection of classes with graphics functions to plot buffer data

The class animWaveFormPlotter is used by the class plotBuffer().
The _call__() method of this latter class is the entry point to the package.

"""

import numpy as np
import time
import matplotlib.pyplot as plt

# access to mimiCoRB Observer class
from .buffer_control import rbObserver

# define global graphics style
pref_style = "dark_background"
_style = pref_style if pref_style in plt.style.available else "default"
plt.style.use(_style)


class animWaveformPlotter(object):
    """
    Oscilloscope-like display of wave from buffer data

    The __call__ method of this class receives input data and
    updates and redraws only the new elements of the figure
    created in __init__
    """

    def __init__(self, conf_dict=None, dtypes=None, source_dict=None, fig=None):
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
        self.source_dict = source_dict
        self.dtypes = source_dict["dtype"]
        self.debug = self.source_dict["debug"]

        plot_title = "" if "title" not in conf_dict else conf_dict["title"]

        # Create figure object if needed
        if fig is None:
            self.fig = plt.figure(plot_title, figsize=(6.0, 4.5))
        else:
            self.fig = fig

        # evaluate config dictionary
        sample_time_ns = self.conf_dict["sample_time_ns"]
        channel_range = 500 if "channel_range" not in self.conf_dict else self.conf_dict["channel_range"]
        self.analogue_offset = 0.0 if "analogue_offset" not in self.conf_dict else 1000.0 * self.conf_dict["analogue_offset"]
        self.trigger_level = None if "trigger_level" not in self.conf_dict else self.conf_dict["trigger_level"] - self.analogue_offset
        trigger_channel = "" if "trigger_channel" not in self.conf_dict else self.conf_dict["trigger_channel"]
        trigger_direction = "" if "trigger_direction" not in self.conf_dict else self.conf_dict["trigger_direction"]
        pre_trigger_samples = 0 if "pre_trigger_samples" not in self.conf_dict else self.conf_dict["pre_trigger_samples"]
        pre_trigger_ns = pre_trigger_samples * sample_time_ns
        plot_length = self.source_dict["values_per_slot"]
        total_time_ns = plot_length * sample_time_ns

        self.min_sleeptime = 1.0 if "min_sleeptime" not in self.conf_dict else self.conf_dict["min_sleeptime"]

        # Create static part of figure
        self.x_linspace = np.linspace(-pre_trigger_ns, total_time_ns - pre_trigger_ns, plot_length, endpoint=False)
        # skip iStep points when plotting data, resulting in 125 - 249 points
        self.iStep = len(self.x_linspace) // 250 + 1
        self.ax = self.fig.add_subplot(1, 1, 1)
        self.fig.subplots_adjust(hspace=0.4)
        self.ax.set_title(plot_title)
        self.ax.set_xlim(
            -pre_trigger_samples * sample_time_ns,
            (plot_length - pre_trigger_samples) * sample_time_ns,
        )
        self.ax.set_xlabel("Time (ns)")
        self.ax.set_ylim(-channel_range - self.analogue_offset, channel_range - self.analogue_offset)
        self.ax.set_ylabel("Signal (mV)")
        self.ax.grid(color="grey", linestyle="--", linewidth=0.5)

        # color_cycler = cycler(color=['lightblue','lightgreen','red','tab:orange'])
        # self.ax.set_prop_cycle(color_cycler)
        if pre_trigger_samples > 0:
            self.ax.axvline(0.0, linestyle=":", color="skyblue")  # trigger time
        if self.trigger_level is not None:
            self.ax.axhline(self.trigger_level, linestyle="--", color="red")  # trigger level
            self.ax.text(
                0.03,
                0.94,
                "Trg " + trigger_channel + " " + str(self.trigger_level) + "mV " + trigger_direction,
                transform=self.ax.transAxes,
                size="small",
                color="red",
            )

        self.bg = self.fig.canvas.copy_from_bbox(self.ax.bbox)

        # line objects to be animated, i.e. updated in __call__()
        self.channel_lines = []
        for dtype_name, dtype_type in self.dtypes:
            (line,) = self.ax.plot(
                self.x_linspace[:: self.iStep],
                np.zeros_like(self.x_linspace)[:: self.iStep],
                marker="",
                linestyle="-",
                lw=1.5,
                alpha=0.5,
                label=dtype_name,
            )
            self.channel_lines.append(line)
        self.animtxts = []
        self.animtxts.append(
            self.ax.text(
                0.45,
                0.94,
                " ",
                transform=self.ax.transAxes,
                size="small",
                color="goldenrod",
            )
        )
        self.ax.legend(loc="upper right")
        # show static part without blocking
        plt.show(block=False)

        # init frequency measurement
        self.last_evNr = 0
        self.last_evT = time.time()

    def init(self):
        """plot initial line objects to be animated"""
        return self.channel_lines

    def __call__(self, data, mdata=None):
        """
        Update variable element of graphics
        """
        # draw variable graphics elements using blitting
        self.fig.canvas.restore_region(self.bg)
        for i, line in enumerate(self.channel_lines):
            line.set_ydata(data[:: self.iStep][self.dtypes[i][0]] - self.analogue_offset)
            self.ax.draw_artist(line)
        if mdata is not None:  # add event number
            evNr = mdata[0][0]
            evT = mdata[0][1]
            frq = (evNr - self.last_evNr) / (evT - self.last_evT)
            self.last_evNr = evNr
            self.last_evT = evT
            self.animtxts[0].set_text("# " + str(evNr) + "  - {:.3g}".format(frq) + " Hz")
            self.ax.draw_artist(self.animtxts[0])
        # - finish the blitting process
        self.fig.canvas.blit(self.ax.bbox)
        plt.pause(min(0.1, self.min_sleeptime))


# <<- end class animWaveformPlotter


class plot_buffer:
    """
    Plot data using a mimiCoRB Observer
    """

    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.animation as anim

    def __init__(
        self,
        source_list=None,
        sink_list=None,
        observe_list=None,
        config_dict=None,
        **rb_info,
    ):
        """
        Plot waveform data from mimiCoRB buffer

        :param input: configuration dictionary

          - plot_title: graphics title to be shown on graph
          - min_sleeptime: time between updates
          - sample_time_ns, channel_range, pretrigger_samples and analogue_offset
            describe the waveform data as for oscilloscope setup
        """

        # get update interval from dictionary
        self.min_sleeptime = 1.0 if "min_sleeptime" not in config_dict else config_dict["min_sleeptime"]
        # access to buffer data
        self.data_reader = rbObserver(observe_list=observe_list, config_dict=config_dict, **rb_info)
        self.active_event = self.data_reader.source._active
        self.source_dict = observe_list[0]
        # initialize oscilloscope-like display
        self.osciplot = animWaveformPlotter(conf_dict=config_dict, source_dict=self.source_dict)

    def __call__(self):
        """
        Procude animated waveform display from data read by observer process
        """
        while True:
            data = next(self.data_reader())
            if data is not None:
                # expect tuple (data, metadata)
                self.channel_lines = self.osciplot(data[0], data[1])  # update graphics with data
                # interrupted sleep so that end-event (=None) is not missed
                dt = 0
                while self.active_event.is_set():
                    time.sleep(0.025)
                    dt += 0.025
                    if dt >= self.min_sleeptime:
                        break
            else:
                # print("plotWaveformBuffer: 'None' recieved - ending")
                # end if empty end-of-run event received, or if data generator is exhausted or deleted
                break

        # finished
        #   possibly add some code to store graphics
        # print(" * PlotWaveformBuffer ended normally")
        raise SystemExit
