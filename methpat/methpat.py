#!/usr/bin/env python

# Assumptions: a read only maps to one amplicon (not overlapping with another).

import sys
from argparse import ArgumentParser
import logging
from visualise import make_html
from collections import namedtuple

DEFAULT_WEBASSETS = 'package'
DEFAULT_TITLE = 'Methylation Patterns'
DEFAULT_COUNT_THRESH = 0
DEFAULT_LOG_FILENAME = 'methpat.log'
DEFAULT_HTML_FILENAME = 'methpat.html'

def parseArgs():
    parser = ArgumentParser(
        description = 'Summarise methylation patterns in bismark output, and generate visualisation.')
    parser.add_argument(
        'bismark_file', metavar='BISMARK_FILE', type=str,
        help='input bismark file')
    parser.add_argument(
        '--count_thresh', metavar='THRESH', type=int, default=DEFAULT_COUNT_THRESH,
        help='only display methylation patterns with at least THRESH number of matching reads, defaults to "{}"'.format(DEFAULT_COUNT_THRESH))
    parser.add_argument(
        '--amplicons', metavar='AMPLICONS_FILE', type=str, required=True,
        help='file containing amplicon information in TSV format')
    parser.add_argument('--logfile', metavar='FILENAME', type=str, default=DEFAULT_LOG_FILENAME,
        help='log progress in FILENAME, defaults to "{}"'.format(DEFAULT_LOG_FILENAME))
    parser.add_argument('--html', metavar='FILENAME', type=str, default=DEFAULT_HTML_FILENAME,
        help='save visualisation in html FILENAME defaults to "{}"'.format(DEFAULT_HTML_FILENAME))
    parser.add_argument('--webassets', choices=('package', 'local', 'online'), type=str,
        default=DEFAULT_WEBASSETS,
        help='location of assets used by output visualisation web page, defaults to "{}"'.format(DEFAULT_WEBASSETS))
    parser.add_argument('--title', metavar='TITLE', type=str,
        default=DEFAULT_TITLE,
        help='title of the output visualisation page, defaults to "{}"'.format(DEFAULT_TITLE))
    parser.add_argument('--dump_pattern_reads', type=str, metavar='FILENAME', required=False,
        help='output read IDs for each methylation pattern to FILENAME')
    return parser.parse_args()

# Bismark uses different codes to indicate the methylation state of
# cytosines:
# z/Z for CpG
# x/X for CHG
# h/H for CHH
# u/U for unknown context 
def encode_methyl(char):
    "convert a methylation state to a binary digit"
    try:
        return { 'z' : 0, 'Z' : 1, 'x': 0, 'X': 1, 'h': 0, 'H': 1, 'u': 0, 'U': 0 }[char]
    except KeyError:
        exit('Methpat: unexpected methylation state ' + char)

def pretty_state(unique_sites, cpg_sites):
    unique_index = 0
    cpg_index = 0 
    result = ''
    while unique_index < len(unique_sites):
        if cpg_index < len(cpg_sites):
            if unique_sites[unique_index] == cpg_sites[cpg_index].pos:
                result += str(cpg_sites[cpg_index].methyl_state)
                unique_index += 1
                cpg_index += 1
            else:
                result += '-'
                unique_index += 1
        else:
            result += '-'
            unique_index += 1
    return result

class CPG_site(object):
    def __init__(self, pos, methyl_state):
        # pos is an integer
        self.pos = pos
        # methyl_state is '0' (off) or '1' (on)
        self.methyl_state = methyl_state

    def __cmp__(self, other):
        return cmp(self.pos, other.pos)

    def __str__(self):
        return "({0}, {1})".format(self.pos, self.methyl_state)

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return self.pos == other.pos and self.methyl_state == other.methyl_state

    def __hash__(self):
        return hash((self.pos, self.methyl_state))

# cpg_sites are encoded and lists of pairs of (pos, methyl)
# this is a methylation pattern
Read = namedtuple("Read", ["chr", "cpg_sites"])

# This is the information which we generate as the output and ultimately visualise
PatternInfo = namedtuple("PatternInfo", ['amplicon', 'chr', 'start', 'end', 'binary', 'count', 'binary_raw', 'read_ids'])

class Amplicon(object):
    def __init__(self, start, end, start_trim, end_trim, name):
        self.start = start
        self.end = end
        self.start_trim = start + start_trim
        self.end_trim = end - end_trim
        self.name = name

    # the ordering of amplicons is determined by their start and end positions
    # they are assumed to be non-overlapping
    def __cmp__(self, other):
        return cmp((self.start, self.end), (other.start, other.end))

def intesect_cpg_sites_amplicon(cpg_sites, amplicon):
    '''Compute the intersection of a list of sorted (ascending) cpg sites with
    the trimmed part of an amplicon. If the intersection is empty then
    the result is an empty list. Otherwise it is a list of sorted cpg sites
    that actually lie within the trimmed amplicon.'''

    return [ cpg for cpg in cpg_sites
                 if cpg.pos >= amplicon.start_trim and
                    cpg.pos <= amplicon.end_trim ]
 
def main():
    args = parseArgs()

    logging.basicConfig(filename=args.logfile,
                        level=logging.DEBUG,
                        filemode='w',
                        format='%(asctime)s %(message)s',
                        datefmt='%m/%d/%Y %H:%M:%S')
    logging.info('program started')
    logging.info('command line: {0}'.format(' '.join(sys.argv)))

    reads = {}

    # collect the list of CPG sites for each read id 
    # the input file has one CPG site per line, identified to a given read id
    # Bismark file has format:
    # READ_ID STRAND(+/-) CHROMOSOME POSITION METHYL_STATE(z/Z)
    # Each READ_ID can appear multiple times, once for each position with
    # a corresponding methylation state. We collect all (pos, methyl_state)
    # pairs together for each read_id. 
    with open(args.bismark_file) as file:
        next(file) # skip the header
        for line in file:
            parts = line.split()
            read_id, _strand, chr, pos, methyl = parts[0:5]
            # convert methylation state to binary digit 
            cpg_site = CPG_site(int(pos), encode_methyl(methyl))
            # reads with the same id must be in the same chr
            if read_id in reads:
                reads[read_id].cpg_sites.append(cpg_site)
            else:
                reads[read_id] = Read(chr, [cpg_site])

    # mapping from amplicon name to chromosome name
    amplicon_chromosomes = {}

    # Amplicons are represented as:
    # CHROMOSOME START_POS END_POS NAME SIZE TRIM_START TRIM_END

    # mapping from chr name to list of amplicons
    # each amplicon is represented as (start, end, name)
    # We assume the amplicons are not overlapping.

    # keep a record of the amplicon names in the order that they appeared
    # in the input file, so we can render them in the same order in 
    # the visualisation.
    amplicon_names = []
    amplicons = {}
    with open(args.amplicons) as file:
        for line in file:
            parts = line.split()
            chr, start, end, name, size, trim_start, trim_end = parts[:7]
            amplicon = Amplicon(int(start), int(end), int(trim_start), int(trim_end), name)
            amplicon_names.append(name)
            if chr in amplicons:
                amplicons[chr].append(amplicon)
            else:
                amplicons[chr] = [amplicon]
            amplicon_chromosomes[name] = chr

    # sort the amplicon entries based on their coordinates
    for chr in amplicons:
        amplicons[chr].sort()

    # We want to associate each amplicon with all the different methylation patterns
    # which it contains, and have a counter for each one. The cpg_sites represents
    # a particular methylation pattern.
    # amplicon -> cpg_sites -> [read_id] 
    methyl_state_counts = {}

    for read_id, read in reads.items():
        intersection = []
        if read.chr in amplicons:
           # sort cpg sites based on their position
           cpg_sites = sorted(read.cpg_sites)

           for amplicon in amplicons[read.chr]:
               # get a list of cpg sites that lie within the amplicon (if any)
               intersection = tuple(intesect_cpg_sites_amplicon(cpg_sites, amplicon))
               if intersection:
                   if amplicon.name in methyl_state_counts:
                       this_amplicon_info = methyl_state_counts[amplicon.name]
	               if intersection in this_amplicon_info:
		           this_amplicon_info[intersection].append(read_id)
	               else:
		           this_amplicon_info[intersection] = [read_id]
	           else:
	               methyl_state_counts[amplicon.name] = { intersection : [read_id] }

                   # stop searching for an amplicon if we find a non-empty intersection
                   # we assume a read intersects only one amplicon
                   break

        if not intersection:
	    logging.info("read {0} in chromosome {1} not in any amplicon".format(read_id, read.chr)) 


    # map each amplicon name to a list of its unique methylation sites (chr positions)
    amplicon_unique_sites = {}
    result = []
    for amplicon in methyl_state_counts:
        # compute the set of unique CPG sites for this amplicon
        unique_sites = set()
        for cpg_sites in methyl_state_counts[amplicon].keys():
            unique_sites.update([site.pos for site in cpg_sites])
        if len(unique_sites) > 0:
            # sort the unique CPG sites into ascending order of position
            unique_sites = sorted(unique_sites)
            amplicon_unique_sites[amplicon] = unique_sites
            start = unique_sites[0]
            end = unique_sites[-1]
            for cpg_sites, read_ids in methyl_state_counts[amplicon].items():
                count = len(read_ids)
                if count >= args.count_thresh:
                    binary = pretty_state(unique_sites, cpg_sites)
                    binary_raw = str(cpg_sites)
                    chr = amplicon_chromosomes[amplicon]
                    pattern_info = PatternInfo(amplicon, chr, start, end, binary, count, binary_raw, read_ids)
                    result.append(pattern_info)

    # For each pattern in each amplicon dump the reads IDs which are associated with that pattern
    if args.dump_pattern_reads:
        with open(args.dump_pattern_reads, 'w') as dump_pattern_reads_file:
            dump_pattern_reads_file.write('\t'.join(['Amplicon', 'Chrom', 'Start', 'End', 'Pattern', 'Read IDs']) + '\n')
            for info in sorted(result): 
                read_str = '\t'.join(info.read_ids)
                dump_pattern_reads_file.write('\t'.join([info.amplicon, info.chr, str(info.start),
                    str(info.end), info.binary, read_str]) + '\n')

    print('\t'.join(["<amplicon ID>", "<chr>", "<Base position start/CpG start>",
          "<Base position end/CpG end>", "<Methylation pattern>", "<count>", "<raw cpg sites>"]))

    json_dict = {}
 
    # unique number for each amplicon
    unique_id = 0

    for info in sorted(result):
        print('\t'.join([info.amplicon, info.chr, str(info.start), str(info.end), info.binary, str(info.count), info.binary_raw]))
        pattern_dict = { 'count': info.count, 'methylation': to_json_pattern(info.binary) }
        if info.amplicon in json_dict:
            amplicon_dict = json_dict[info.amplicon]
            amplicon_dict['patterns'].append(pattern_dict)
        else:
            try:
                unique_sites = amplicon_unique_sites[info.amplicon]
            except KeyError:
                unique_sites = []
            amplicon_dict = { 'unique_id': unique_id
                            , 'amplicon': info.amplicon
                            , 'sites': unique_sites   # CPG sites (chrom positions)
                            , 'chr': info.chr
                            , 'start': info.start
                            , 'end': info.end
                            , 'patterns': [pattern_dict] }
            json_dict[info.amplicon] = amplicon_dict
            unique_id += 1

    make_site_totals(json_dict)
    make_html(args, amplicon_names, json_dict)

def make_site_totals(json_dict):
    '''For each site in each amplicon, count up the number
    of methylated, unmethylated and unknown samples
    Add the information to the amplicon dictionary.
    '''
    for amplicon, amplicon_dict in json_dict.items():
        site_methylation_totals = []
        for site_index, site in enumerate(amplicon_dict['sites']):
            methylated_count = 0
            unmethylated_count = 0
            unknown_count = 0
            for pattern in amplicon_dict['patterns']:
                methylation_code = pattern['methylation'][site_index]
                pattern_count = pattern['count']
                if methylation_code == 0:
                    unmethylated_count += pattern_count
                elif methylation_code == 1:
                    methylated_count += pattern_count
                else:
                    unknown_count += pattern_count
                total_count = float(unmethylated_count + methylated_count + unknown_count)
            # pass the site counts as percentages of the total count
            site_totals_dict = { 'site_unmethylated': unmethylated_count / total_count
                               , 'site_methylated': methylated_count / total_count
                               , 'site_unknown': unknown_count / total_count }
            site_methylation_totals.append(site_totals_dict)
        amplicon_dict['site_totals'] = site_methylation_totals


def to_json_pattern(binary):
    char_to_int = { '0': 0, '1': 1, '-': 2 }
    return [ char_to_int[c] for c in binary ]

if __name__ == '__main__':
    main()
