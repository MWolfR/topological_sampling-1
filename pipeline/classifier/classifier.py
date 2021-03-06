"""
toposampling - Topology-assisted sampling and analysis of activity data
Copyright (C) 2020 Blue Brain Project / EPFL & University of Aberdeen

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import os
import numpy
import h5py
import json

import importlib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from toposample import config, data


def make_classifier(clasifier_specs):
    module = importlib.import_module(clasifier_specs["classifier_module"])
    classifier_class = module.__dict__[clasifier_specs["classifier_class"]]
    return classifier_class(**clasifier_specs["init_kwargs"])


def write_results_file(scores, y_truth, y_predicted, out_root, results_fn, conds):
    out_fn = os.path.join(out_root, conds.get("sampling", "UNSPECIFIED"),
                          conds.get("specifier", "UNSPECIFIED"),
                          conds.get("index", "UNSPECIFIED"), results_fn)
    assert not os.path.exists(out_fn)
    if not os.path.exists(os.path.split(out_fn)[0]):
        os.makedirs(os.path.split(out_fn)[0])
    with h5py.File(out_fn, 'w') as h5:
        h5.create_dataset("scores", data=scores)
        h5.create_dataset("y_truth", data=y_truth)
        h5.create_dataset("y_pred", data=y_predicted)
    return out_fn


def execute_classifier(features, classifier_cfg):  # trials x features+y
    X = StandardScaler().fit_transform(features[:, :-1])  # TODO: Configured from config file
    y = features[:, -1]

    clf = make_classifier(classifier_cfg)
    # cv_scores = cross_val_score(clf, X, y, cv=stage_cfg["num_cv"])
    test_scores = []
    test_truth = []
    test_predictions = []

    for seed in classifier_cfg["cross_validation"]["random_seeds"]:
        X_train, X_test, y_train, y_test = train_test_split(X, y,
                                                            train_size=classifier_cfg["cross_validation"]["train_size"],
                                                            random_state=seed)
        fitted = clf.fit(X_train, y_train)
        prediction = fitted.predict(X_test)
        test_truth.append(y_test)
        test_predictions.append(prediction)
        test_scores.append(numpy.mean(prediction == y_test))
    return test_scores, test_truth, test_predictions


def execute_classifier_all(input_struc, label_struc, classifier_cfg, out_root, results_fn):
    result_lookup = {}
    for res in input_struc.contents:
        print("Evaluating for {0}".format(res.cond))
        scores, y_truth, y_pred = execute_classifier(res.res, classifier_cfg)
        out_fn = write_results_file(scores, y_truth, y_pred, out_root, results_fn, res.cond)
        spec_lvl = result_lookup.setdefault(res.cond["sampling"], {}).setdefault(res.cond["specifier"], {})
        chief = label_struc.get2(**res.cond)
        spec_lvl[res.cond["index"]] = {"data_fn": out_fn, "idv_label": chief}
    return result_lookup


def read_input(input_config, input_type, classifier_config):
    step_idx_fr = classifier_config.get("time_steps_to_use", {}).get("from", None)
    strp_idx_to = classifier_config.get("time_steps_to_use", {}).get("to", None)

    def read_reshape_stack(fn):
        import h5py
        all_X = []
        with h5py.File(fn, "r") as h5:
            grp = h5["per_stimulus"]
            for k in grp.keys():
                stim_id = int(k[4:])
                per_stim = numpy.array(grp[k])  # time x components x trials
                if step_idx_fr is not None:
                    per_stim = per_stim[step_idx_fr:strp_idx_to, :, :]
                X = per_stim.reshape((-1, per_stim.shape[-1]))  # time-components x trials
                X = numpy.vstack((X, stim_id * numpy.ones(X.shape[1]))).transpose()  # trials x time-components+y
                all_X.append(X)
        return numpy.vstack(all_X)  # trials x time-components+y

    functions_dict = {"data_fn": [read_reshape_stack, False]}
    res = data.TopoData(input_config[input_type],
                        follow_link_functions=functions_dict)
    return res


def read_filter_stack(fn):
    """Experimental alternative. Filters data to yield only the most informative time step for each component.
    TODO: Probably remove. We are not using this.
    """
    import h5py
    with h5py.File(fn, "r") as h5:
        grp = h5["per_stimulus"]
        stims = []
        time_series = []
        for k in grp.keys():
            stim_id = int(k[4:])
            per_stim = numpy.array(grp[k])  # time x components x trials
            time_series.append(per_stim)
            stims.append(stim_id)
        idxx = []
        for component in range(time_series[0].shape[1]):
            var_reduction = []
            for step in range(time_series[0].shape[0]):
                samples = [_x[step, component, :] for _x in time_series]
                var_before = numpy.var(numpy.hstack(samples))
                var_after = numpy.mean(numpy.hstack([numpy.var(_smpl) * numpy.ones_like(_smpl) for _smpl in samples]))
                var_reduction.append(var_before / (var_after + 0.1))
            idxx.append(numpy.argmax(var_reduction))
        time_series = [_x[idxx, range(len(idxx)), :] for _x in time_series]  # components x trials
        time_series = [numpy.vstack([_x, stim_id * numpy.ones(_x.shape[1])]).transpose()
                       for _x, stim_id in zip(time_series, stims)]  # trials x components + y
    return numpy.vstack(time_series)  # trials x components+y


def write_output(res_dict, fn_out):
    if os.path.exists(fn_out):
        with open(fn_out, "r") as fid:
            existing = json.load(fid)
        for k, v in res_dict.items():
            existing.setdefault(k, {}).update(v)
        with open(fn_out, "w") as fid:
            json.dump(existing, fid, indent=2)
    else:
        with open(fn_out, 'w') as fid:
            json.dump(res_dict, fid, indent=2)


def main(path_to_config, input_type, **kwargs):
    cfg = config.Config(path_to_config)
    stage = cfg.stage("classifier")
    if input_type not in stage["inputs"]:
        raise Exception("Input type {0} not known!".format(input_type))
    classifier_cfg = stage["config"]["classifiers"][stage["config"]["selected"][input_type]]

    class_data = read_input(stage["inputs"], input_type, classifier_cfg)
    res_dict = execute_classifier_all(class_data["data_fn"].filter(**kwargs),
                                      class_data["idv_label"].filter(**kwargs),
                                      classifier_cfg,
                                      stage["other"], "results_" + input_type + ".h5")
    write_output(res_dict,
                 stage["outputs"]["classifier_{0}_results".format(input_type)])


def parse_filter_arguments(*args):
    fltr_dict = {}
    for arg in args:
        if "=" in arg:
            splt = arg.split("=")
            fltr_dict[splt[0]] = splt[1]
    return fltr_dict


if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2], **parse_filter_arguments(*sys.argv[3:]))
