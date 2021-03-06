"""
toposampling - Topology-assisted sampling and analysis of activity data
Copyright (C) 2020 Blue Brain Project / EPFL & University of Aberdeen

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import numpy
from toposample import config


def execute_split(spikes, stimuli, data_cfg):
    assert len(numpy.unique(stimuli)) == data_cfg["num_stimuli"]
    splt_t = data_cfg["stim_duration_ms"]
    t_bins = numpy.arange(data_cfg["t_stim_start"], numpy.max(spikes[:, 0]) + splt_t, splt_t)
    t_bin_idx = numpy.digitize(spikes[:, 0], bins=t_bins) - 1
    assert numpy.max(t_bin_idx) < len(stimuli)

    list_of_lists = [[] for _ in range(data_cfg["num_stimuli"])]
    for i, stim in enumerate(stimuli):
        curr_t_start = i * splt_t
        curr_t_end = curr_t_start + splt_t
        win = spikes[t_bin_idx == i]
        if len(win) == 0:
            print("Warning: no spikes between {0} and {1} ms".format(curr_t_start, curr_t_end))
        win[:, 0] = win[:, 0] - curr_t_start - data_cfg["t_stim_start"]
        list_of_lists[stim].append(win)
    return list_of_lists


def read_input(input_config):
    spikes = numpy.load(input_config["raw_spikes"])
    stims = numpy.load(input_config["stimuli"])
    return spikes, stims


def write_output(data, output_config):
    numpy.save(output_config["split_spikes"], data)


def main(path_to_config):
    # Read the meta-config file
    cfg = config.Config(path_to_config)
    # Get configuration related to the current pipeline stage
    stage = cfg.stage("split_spikes")
    spikes, stims = read_input(stage["inputs"])
    split_spikes = execute_split(spikes, stims, stage["config"])
    write_output(split_spikes, stage["outputs"])


if __name__ == "__main__":
    import sys
    main(sys.argv[1])
