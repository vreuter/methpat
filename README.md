Introduction
============

This program summarises the resultant DNA methylation pattern data from the output of [Bismark](http://www.bioinformatics.babraham.ac.uk/projects/bismark/) bismark_methylation_extractor. Information of the DNA methylation positions for each amplicon, DNA methylation patterns observed within each amplicon and their abundance counts are summarised into a tab delimited text file amenable for further downstream statistical analysis and visualization.

Installation
------------

Methpat currently requires version 2.7 of Python.

The best way to install Methpat is to use the following command:

    pip install git+https://github.com/bjpop/methpat.git

This will automatically download and install the dependencies of methpat.

Usage
-----

    usage: methpat.py [-h] [--dump_reads FILE] [--count_thresh THRESH] --amplicons
                      AMPLICONS_FILE --logfile FILENAME
                      BISMARK_FILE

    Count methylation patterns in bismark output

    positional arguments:
      BISMARK_FILE          input bismark file

    optional arguments:
      -h, --help            show this help message and exit
      --dump_reads FILE     dump the read methylation information to FILE
      --count_thresh THRESH
                            Only display methylation patterns with at least THRESH
                            number of matching reads
      --amplicons AMPLICONS_FILE
                            Only display methylation patterns with at least THRESH
                            number of matching reads
      --logfile FILENAME    log progress in FILENAME
