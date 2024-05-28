# **mimoCoRB** - multiple-in multiple-out Configurable Ring Buffer

## Summary:

Provided here is a central component of each data acquisition system
needed to record and pre-analyse data from randomly occurring processes.
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

This project originated from an effort to structure and generalize
data acquisition for several experiments in an advanced physics laboratory
courses at Karlsruhe Institute of Technology.

As a simple demonstration, we provide signals recorded by a detector
for cosmic muons with three layers. Occasionally, such muons stop
in an absorber between the 2nd and 3rd layer, where they decay at rest
and emit a high-energetic electron recorded as a 2nd pulse in one or
two of the detection layers. 

To see a simple example showing pules shapes and the extracted pulse
heights from simulated waveforms, change to the directory `examples/`
of this package and execute

```bash
../run_daq.py spectrum_setup.yaml
```
The configuration files `examples/simul_source.yaml` and 
`examples/simul_spin_setup.yaml` contain more advanced
examples of muon lifetime measurements from double-pulses
produced by an incoming muon and the decay electron. 

