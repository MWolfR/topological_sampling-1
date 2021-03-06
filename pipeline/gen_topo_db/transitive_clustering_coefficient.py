"""
toposampling - Topology-assisted sampling and analysis of activity data
Copyright (C) 2020 Blue Brain Project / EPFL & University of Aberdeen

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import numpy as np
import progressbar
from pyflagsercontain import flagser_count


def compute(tribes, adj_matrix, conv, precision):

    # Transitive clustering coefficients of chiefs
    trccs = []

    simplexcontainment = flagser_count(adj_matrix)
    indegs = np.array(adj_matrix.sum(axis=0))[0]
    outdegs = np.array(adj_matrix.sum(axis=1))[:, 0]
    totdegs = np.array((adj_matrix + adj_matrix.transpose()).sum(axis=0))[0]
    recip_degs = indegs + outdegs - totdegs

    # This assumes tribes are in the order of adjacency matrix indexing
    pbar = progressbar.ProgressBar(maxval=len(indegs))
    for indeg, outdeg, totdeg, recip_deg, smplxcont in pbar(zip(indegs, outdegs,
                                                                totdegs, recip_degs,
                                                                simplexcontainment)):
        denom = totdeg*(totdeg-1)-(indeg*outdeg+recip_deg)

        if denom != 0 and len(smplxcont) > 2:
            # smplxcont[i][2] gives the number of directed 2-cliques that vertex i belongs to
            parameter = np.round(smplxcont[2] / denom, precision)
        else:
            parameter = 0
        trccs.append(parameter)

    return trccs
