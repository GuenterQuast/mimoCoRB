"""*bufferInfoGUI*
Graphical display of buffer status
"""

import sys, time, numpy as np
import threading, multiprocessing as mp

import tkinter as Tk
from tkinter import messagebox as mbox

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt, matplotlib.animation as anim
from cycler import cycle

class plot_bufferinfo(object):
  """ 
  display statistics from Buffer Manager

    uses multiprocessing.Queue() to display buffer information:
    total number of events, data acquisition rate, buffer filling level
  """

  def __init__(self, Q, RBnames, maxRate=1500., interval=1000.):
    self.Q = Q
    self.RBnames = RBnames
    self.line_names = RBnames
    self.ymax = maxRate
    self.interval = interval/1000 # time between updates in s
    self.Nlines = len(RBnames)

    self.Npoints = 180  # number of history points
    self.R = np.zeros( (self.Nlines, self.Npoints) )
    self.xplt = np.linspace(-self.Npoints*self.interval, 0., self.Npoints)

  # create figure 
    self.fig = plt.figure("BufManInfo", figsize=(6., 3.5))
    self.fig.subplots_adjust(left=0.05, bottom=0.15, right=0.925, top=0.9,
               wspace=None, hspace=.25)
    self.axtext=plt.subplot2grid((7,1),(0,0), rowspan=2) 
    self.axrate=plt.subplot2grid((7,1),(2,0), rowspan=5) 
    self.fig.suptitle('mimoCoRB Ring Buffer Information')
    self.axtext.set_frame_on(False)
    self.axtext.get_xaxis().set_visible(False)
    self.axtext.get_yaxis().set_visible(False)
    self.axrate.yaxis.tick_right()
    self.axrate.set_ylabel('DAQ rate (HZ)')
    self.axrate.set_xlabel('rate history (s)')
    self.xmin = -self.interval * self.Npoints
    self.xmax = 0. 
    self.axrate.set_xlim(self.xmin, self.xmax)
    self.ymin = 0.01
    self.axrate.set_ylim(self.ymin, self.ymax)
    self.axrate.set_yscale('log')
    self.axrate.grid(True, alpha=0.5)

    # plot initial line objects
    lcycler = cycle(["-","-."])
    self.animlines = ()
    for i, nam in enumerate(self.line_names):
        line, = self.axrate.plot(self.xplt, self.R[i], label=nam, 
                                 marker = '.', markersize=3, 
                                 linestyle=next(lcycler), alpha=0.5 )
        self.animlines += line,
    # plot initial text objects
    self.animtxts = ()
    self.animtxts += ( self.axtext.text(0.015, 0.65 , ' ',
                         transform=self.axtext.transAxes, color='darkblue') ,)
    self.animtxts += ( self.axtext.text(0.2, 0.2 , ' ',
                         transform=self.axtext.transAxes, color='grey') ,)
    self.axrate.legend(loc="lower left")

  def init(self):
      self.ro = 0.
      self.n0 = 0
      self.t0 = time.time()
      return self.animlines + self.animtxts

  def __call__(self, n):
    if n == 0:
       self.init()

    k = n%self.Npoints
    try: 
      status, active_time, Nevents, RBinfo = \
                 self.Q.get(True, 0.5)
    except:
      return self.animlines + self.animtxts

    for i in range(self.Nlines):
        R = self.R[i]
        R[k] = RBinfo[self.RBnames[i]][2]   
        self.animlines[i].set_ydata(np.concatenate( (R[k+1:], R[:k+1]) ))

    txtStat=status
    self.animtxts[0].set_text( \
       "Time active: {:.1f}s     Number of Events: {:d}  Status: {:s}  ".format(
           active_time, Nevents, txtStat) )
    self.animtxts[1].set_text( \
     'current rate: {:.3g}Hz    in buffer: {:d}'.format(
          RBinfo[self.RBnames[0]][2], RBinfo[self.RBnames[0]][1]) )

    return self.animlines + self.animtxts

def bufferinfoGUI(Qcmd, Qlog, Qinfo,
                  RBnames=["RB_1"], maxRate = 100. , interval = 1000.):
  """
  Show Buffer Manager logging messages and rate history and command buttons
    Args:
      Qcmd      multiprocessing.Queue for command passing to calling process
      Qlog:     multiprocessing.Queue() for logging-info  
      Qinfo:    multiprocessing.Queue() for status info
      RBnames:  list, buffer names, used as line labels
      maxrate: maximum rate for y-axis
      interval: update interval
  """

  def wrtoLog(T):
    while True:
      T.insert(Tk.END, Qlog.get()+'\n' )
      T.see("end")
      time.sleep(0.01)

  def sequence_gen():
  # generator for sequence of integers
      i=0
      while True:
        i+=1
        yield i
      return

  def cmdPause():
      Qcmd.put('P')

  def cmdResume():
      Qcmd.put('R')

  def cmdStop():
      Qcmd.put('S')

  def cmdEnd():
      Qcmd.put('E')

  # a simple clock
  def clkLabel(TkLabel):
     t0 = time.time()
     def clkUpdate():
       dt = int(time.time() - t0)
       datetime = time.strftime('%y/%m/%d %H:%M',time.localtime(t0))
       TkLabel.config(text = 'started ' + datetime + \
                      '   T=' + str(dt) + 's  ' )
       TkLabel.after(1000, clkUpdate)
     clkUpdate()

# ------- executable part -------- 

# generate window, Buttons, graphics and text display 
  Tkwin = Tk.Tk()
  Tkwin.geometry("1024x600")
  Tkwin.wm_title("Buffer Information")

# handle destruction of top-level window
  def _delete_window():
    if mbox.askokcancel("Quit", "Really destroy BufManCntrl window ?"):
       print("Deleting BufManCntrl window")
       Tkwin.destroy()
  
  Tkwin.protocol("WM_DELETE_WINDOW", _delete_window)

# Comand buttons
  frame = Tk.Frame(master=Tkwin)
  frame.grid(row=0, column=8)
  frame.pack(padx=5, side=Tk.BOTTOM)

  buttonE = Tk.Button(frame, text='EndRun', fg='red', command=cmdEnd)
  buttonE.grid(row=0, column=8)

  blank = Tk.Label(frame, width=7, text="")
  blank.grid(row=0, column=7)

  clock = Tk.Label(frame)
  clock.grid(row=0, column=5)

  blank2 = Tk.Label(frame, width=7, text="")
  blank2.grid(row=0, column=4)

  buttonS = Tk.Button(frame, text=' Stop ', fg='purple', command=cmdStop)
  buttonS.grid(row=0, column=3)

  buttonR = Tk.Button(frame, text='Resume', fg='blue', command=cmdResume)
  buttonR.grid(row=0, column=2)

  buttonP = Tk.Button(frame, text='Pause ', fg='blue', command=cmdPause)
  buttonP.grid(row=0, column=1)

  blank3 = Tk.Label(frame, width=7, text="")
  blank3.grid(row=0, column=0)

#
# graphics display 
  RBi = plot_bufferinfo(Qinfo, RBnames, maxRate, interval)
  figRBi = RBi.fig
  canvas = FigureCanvasTkAgg(figRBi, master=Tkwin)
  canvas.draw()
  canvas.get_tk_widget().pack(side=Tk.TOP, fill=Tk.BOTH, expand=1)
  canvas._tkcanvas.pack(side=Tk.TOP, fill=Tk.BOTH, expand=1)
#
# text window
  S = Tk.Scrollbar(Tkwin)
  T = Tk.Text(Tkwin, height=10, width=150, wrap=Tk.WORD,
#      bg='black', fg='aquamarine' , font='Helvetica 10')
      bg='black', fg='darkorange' , font='Helvetica 10')
  S.pack(side=Tk.RIGHT, fill=Tk.Y)
  T.pack(side=Tk.LEFT, fill=Tk.Y)
  S.config(command=T.yview)
  T.config(yscroll=S.set)

##! try:
  while True: 
# start display of active time
    clkLabel(clock)

# start an update-process for logging information as thread
#    print("starting update thread")
    wrthread = threading.Thread(target=wrtoLog,
                              args=(T, ) ) 
    wrthread.daemon = True
    wrthread.start()

# set up matplotlib animation for rate history
    RBiAnim = anim.FuncAnimation(figRBi, RBi, sequence_gen,
                     interval=interval, init_func=RBi.init,
                     blit=True, fargs=None, repeat=True, save_count=None) 
                         # save_count=None is a (temporary) work-around 
                         #     to fix memory leak in animate
    Tk.mainloop()
#  except:
#    print('*==* bufferinfoGUI: termination signal received')
#  sys.exit()


  
