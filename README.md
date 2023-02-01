# **mimoCoRB** - multiple-in multiple-out Configurable Ring Buffer

## Summary:

Provided here is a central component of each data acquisition system
needed to record and pre-analyze data from randomly occurrig proceses.
Typical examples are wave-forms data as provided by single-photon
counters or typical detectors common in quantum mechanical measurements
or in nuclear, particle physics and astro particle physics, e. g.
photo tubes, Geiger counters, avalanche photo-diodes or modern SiPMs.

The random nature of such processes and the need to keep read-out dead
times low requires an input buffer and a buffer manager running as
a background process. Data are provided via the buffer manager 
interface to several consumer processes to analyze, check or visualize
data and analysis results. Such consumers may be obligatory ones,
i. e. data acquisition pauses if all input buffers are full and an 
obligatory consumer is still busy processing. A second type of
random consumers or "observers" receives an event copy from the buffer
manager upon request, without pausing the data acquisition process.
Typical examples of random consumers are displays of a subset of the
wave forms or of intermediate analysis results.

This project originated from an attempt to structure and generalize
data acquision for several experimenta in an advanced physics laboratory
courses at Karlruhe Institute of Technology.

As a simple demonstration, we provide signals recored by a detector
for comsmic myons with three layers. Occasionally, such muons stop
in an absorber between the 2nd and 3rd layer, where they decay at rest
and emit a high-energetic electron recorded as a 2nd pulse in one or
two of the detection layers. 
