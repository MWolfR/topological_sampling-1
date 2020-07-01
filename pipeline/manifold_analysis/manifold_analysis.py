import numpy
import os
import json
import h5py

from toposample import config
from toposample import TopoData


def read_input(input_config):
    tribes = TopoData(input_config["tribes"])
    tribal_chiefs = tribes["chief"]
    tribal_gids = tribes["gids"]
    spikes = numpy.load(input_config["raw_spikes"])
    stims = numpy.load(input_config["stimuli"])
    return spikes, stims, tribal_chiefs, tribal_gids


def spikes_to_y_vec(spikes, gids, t_bin_width):
    t_max = numpy.ceil(numpy.max(spikes[:, 0]) / t_bin_width) * t_bin_width
    spikes = spikes[numpy.in1d(spikes[:, 1], gids)]
    gid_bins = numpy.hstack([sorted(gids), numpy.max(gids) + 1])
    t_bins = numpy.arange(0, t_max + t_bin_width, t_bin_width)
    out = numpy.histogram2d(spikes[:, 1], spikes[:, 0], bins=(gid_bins, t_bins))[0]
    return out


def factor_analysis(y_mat, num_components):
    from sklearn.decomposition import FactorAnalysis
    F = FactorAnalysis(num_components)
    transformed = F.fit_transform(y_mat)
    components = F.components_
    mn = F.mean_
    noise_variance = F.noise_variance_
    return transformed, components, mn, noise_variance


def split_transformed_into_t_wins(transformed, stim_train):
    u_stims = numpy.unique(stim_train)
    tf_splt = numpy.split(transformed, len(stim_train), axis=1)
    per_stim_splt = [numpy.dstack([_splt for _splt, s in zip(tf_splt, stim_train)
                                   if s == i]) for i in numpy.unique(u_stims)]  # [stimulus] x component x time x trial
    per_stim_splt = [_splt.transpose([1, 0, 2]) for _splt in per_stim_splt]  # [stimulus] x time x component x trial
    return per_stim_splt


def write_results_file(transformed, tf_split, components, mn, noise_variance, chief_spec, out_root, conds):
    out_fn = os.path.join(out_root, conds.get("sampling", "UNSPECIFIED"),
                          conds.get("specifier", "UNSPECIFIED"),
                          conds.get("index", "UNSPECIFIED"), "results.h5")
    assert not os.path.exists(out_fn)
    if not os.path.exists(os.path.split(out_fn)[0]):
        os.makedirs(os.path.split(out_fn)[0])
    with h5py.File(out_fn, 'w') as h5:
        h5.create_dataset("transformed", data=transformed)
        h5.create_dataset("components", data=components)
        h5.create_dataset("mean", data=mn)
        h5.create_dataset("noise_variance", data=noise_variance)
        h5.attrs["chief"] = chief_spec
        grp = h5.require_group("per_stimulus")
        for i, res in enumerate(tf_split):
            grp.create_dataset("stim{0}".format(i), data=res)
    return out_fn


def transform_all(spikes, stims, tribal_chiefs, tribal_gids, stage_config, out_root):
    result_lookup = {}
    for res in tribal_gids.contents:
        gids = res.res
        y_vec = spikes_to_y_vec(spikes, gids, stage_config["t_bin_width"])
        transformed, components, mn, noise_variance = factor_analysis(y_vec, stage_config["n_components"])
        tf_split = split_transformed_into_t_wins(transformed, stims)
        chief = tribal_chiefs.get2(**res.cond)
        out_fn = write_results_file(transformed, tf_split, components, mn,
                                    noise_variance, chief, out_root, res.cond)
        spec_lvl = result_lookup.setdefault(res.cond["sampling"], {}).setdefault(res.cond["specifier"], {})
        spec_lvl[res.cond["index"]] = {"data_fn": out_fn, "chief": chief}
    return result_lookup


def write_output(data, output_config):
    fn_out = output_config["components"]
    if os.path.exists(fn_out):
        with open(fn_out, "r") as fid:
            existing = json.load(fid)
        for k, v in data.items():
            existing.setdefault(k, {}).update(v)
        with open(fn_out, "w") as fid:
            json.dump(existing, fid, indent=2)
    else:
        with open(fn_out, 'w') as fid:
            json.dump(data, fid, indent=2)


def main(path_to_config):
    # Read the meta-config file
    cfg = config.Config(path_to_config)
    # Get configuration related to the current pipeline stage
    stage = cfg.stage("struc_tribe_analysis")
    spikes, stims, tribal_chiefs, tribal_gids = read_input(stage["inputs"])
    res_lookup = transform_all(spikes, stims, tribal_chiefs, tribal_gids, stage["config"], stage["other"])
    write_output(res_lookup, stage["outputs"])


if __name__ == "__main__":
    import sys
    main(sys.argv[1])
