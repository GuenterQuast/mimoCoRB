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



Detailed desctiption of components
..................................


Ring buffer


Writer, Reader and Observer classes


User Access classes wrapping the mimoCoRB classes


Configuraion of DAQ with yaml files


.. toctree::
   :maxdepth: 2
   :caption: Contents:



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
		 
     

	
