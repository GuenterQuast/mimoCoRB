===========================================================
mimoCoRB - multiple-in multile-out Configurable Ring Buffer
===========================================================

mimoCoRB Overview:
------------------

**mimoCoRB**: multiple-in multiple-out Configurable Ring Buffer

The package **mimoCoRB** provides a central component of each data acquisition
system needed to record and pre-analyze data from randomly occurrig proceses.
Typical examples are waveform data as provided by single-photon
counters or typical detectors common in quantum mechanical measurements
or in nuclear, particle physics and astro particle physics, e. g.
photo tubes, Geiger counters, avalanche photo-diodes or modern SiPMs.

The random nature of such processes and the need to keep read-out dead
times low requires an input buffer and a buffer manager running as
a background process. While a data source feeds data into the
ringbuffer, consumer processes are fed with an almost constant stream
of data to filter, reduce, analyze or simply visualize data and
on-line analysis results. Such consumers may be obligatory ones,
i. e. data acquisition pauses if all input buffers are full and an 
obligatory consumer is still busy processing. A second type of
random consumers or "observers" receives an event copy from the buffer
manager upon request, without pausing the data acquisition process.
Typical examples of random consumers are displays of a subset of the
wave forms or of intermediate analysis results.

This project originated from an attempt to structure and generalize
data acquision for several experiments in advanced physics laboratory
courses at Karlruhe Institute of Technology (KIT).

As a simple demonstration, we provide data from simulatd signals as would
be recored by a detector for comsmic myons with three detection layers.
Occasionally, such muons stop in an absorber between the 2nd and 3rd layer,
where they decay at rest and emit a high-energetic electron recorded as a
2nd pulse in one or two of the detection layers. After data acquitision, a search for
typical pulses is performed, data with detected double pulses are selected
and fed into a second buffer. A third buffer receives data in a
reduced format which only contains the parameters of found pulses.
These data and the wave forms of all double-pulses are finally stored
on disk. This application is a very typical example of the general
process of on-line data processing in modern experiments and may
serve as a starting point for own applictions.




.. toctree::
   :maxdepth: 2
   :caption: Contents:



Detailed desctiption of components
..................................


Ring buffer


Writer, Reader and Observer classes


User Access classes wrapping the mimoCoRB classes


Configuraion of DAQ with yaml files


### Simple application example (also provided as a unittest)

An application example of *mimo_buffer* is shown below.  
This code may serve as a starting point for own projects.
The set-up is as follows:

  2 ring buffers are defined:
  
    - input Buffer  RB_1: 10 ch x 1024 slots (int32)

    - output Buffer RB_2: 10 ch x 2 slots/ch (float64)
   
    Simple data is filled into RB_1, copied and extended by a process
    writing data into RB_2, and finally a reader process to check
    integrity and completenss of thd data. The most complex part of
    the code is in function *run_control()*, which demonstrates
    how to set up the buffers, define Reader and Writer instances
    and start the prallel processes for generating, processing
    and reading the data. 
   
The example including coment lines for explanation is shown here:

.. code-block:: python

  import time
  import unittest
  import numpy as np
  from multiprocessing import Process, Value
  from mimocorb import mimo_buffer as bm

  # global variables 
  N_requested = 1000  # numer of data injectios ("events")
  Time_tick = 0.001   # time between events
  Ncpu1 = 2           # number of parallel abalyzer processes

  def data_generator(sink_dict):
    """writes continuously rising integers to buffer specified in sink_dict
    """
    sink = bm.Writer(sink_dict)
    n=0
    # inject data
    for x in range(N_requested):
        buffer = sink.get_new_buffer() # get new buffer and pass last item
        #  random wait for next data item
        time.sleep(-Time_tick*np.log(np.random.rand() ))
        # fill "data"
        n += 1
        buffer[:] = n
    # process last data item
    sink.process_buffer()


  def analyzer(source_dict, sink_dict):
    """read from source and write first element and a time difference to sink
    """
    source = bm.Reader(source_dict)
    sink = bm.Writer(sink_dict)
    start_time = time.time()
    
    while True:
        input_data = source.get()
        output_data = sink.get_new_buffer()
        # process data
        output_data[0] = input_data[0]
        # mimick processing time
        time.sleep(2*Time_tick)
        output_data[1] = time.time() - start_time

        # 
        sink.process_buffer()


  def check_result(source_dict, res):
    """reads RB_2 and sum up the integer content (value should be sum(1 -35) = 630);

       sum is returned as shared memory Value-object
    """
    source = bm.Reader(source_dict)
    sum_rb = 0
    while True:
        input_data = source.get()
        res.value +=int(input_data[0])

  def run_control():
    """Setup buffers, start processes and shut_down when 1st writer done 
    """

    # Create ring buffers: #2: 10 channel, 2 value per channel
    #    (1: buffer content; 2: time difference as int)
    #    d_type = [('chA', np.float)]  #not necessary: always the same type
    generator_buffer = bm.NewBuffer(10, 1, np.int32)
    eval_buffer = bm.NewBuffer(10, 2, np.float32)

    # create readers first
    source_dic_gen = generator_buffer.new_reader_group()
    source_dic_eval = eval_buffer.new_reader_group()

    # Create worker processes (correct sequence: first action as last)
    process_list = []
    #  evaluation to test ring buffer behavior
    result = Value('i', 0)   # int variable in shared meomry
    process_list.append(Process(target=check_result,
                                args=(source_dic_eval, result)))
    # data transfer between the 2 buffers: generator_buffer -> eval_buffer
    sink_dic_eval = eval_buffer.new_writer()
    # work with all cpu's requested
    number_of_workers = Ncpu1
    for i in range(number_of_workers):
        process_list.append(Process(target=analyzer,
                                    args=(source_dic_gen, sink_dic_eval)))

    # fill buffer (generator_buffer) with data first
    sink_dic_gen = generator_buffer.new_writer()
    process_list.append(Process(target=data_generator,
                                args=(sink_dic_gen,)))

    for p in process_list:
        p.start()

    run_active = True
    while run_active:
       run_active = False if process_list[-1].exitcode==0 else True
       time.sleep(0.1)  # wait
        
    time.sleep(0.1)  # some grace-time for readers to finish

    generator_buffer.shutdown()
    eval_buffer.shutdown()
    del generator_buffer, eval_buffer

    for p in process_list:
        p.join()

    return result.value


  class RPTest(unittest.TestCase):

    def test_process(self):
        # start python test module and check result
        a = run_control()
        expected_result = N_requested*(N_requested+1)//2
        self.assertEqual(a, expected_result)  # expected result: sum(i); i = 1, N_requested


  if __name__ == "__main__":
    unittest.main(verbosity=2)
  #    print(process_buffer())



   

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

=====================
Module Documentation 
=====================

..  automodule:: mimocorb
     :imported-members:
     :members:

..  automodule:: mimocorb.mimo_buffer
     :members:

..  automodule:: mimocorb.access_classes
     :members:

..  automodule:: rb_unittest
		 
     

	
