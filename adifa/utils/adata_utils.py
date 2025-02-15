import os
import re

from flask import current_app
from scipy.sparse import spmatrix
from sqlalchemy import exc
import scanpy as sc
import numpy as np
import pandas as pd

from adifa import models
from adifa.resources.errors import (
    InvalidDatasetIdError,
    DatabaseOperationError,
    DatasetNotExistsError,
)


def get_annotations(adata):
    annotations = {"obs": {}, "obsm": [], "var": [], "has_masks": False}

    switcher = {
        "category": type_category,
        "bool": type_bool,
        "int": type_numeric,
        "float": type_numeric,
        "complex": type_numeric,
    }

    obs_cat = {}
    if "column_ordering" in adata.uns:
        for k in adata.uns["column_ordering"]:
            for v in adata.uns["column_ordering"][k]:
                obs_cat[v] = k

    for name in adata.obs:
        # Map numpy dtype to a simple type for switching
        dtype = re.sub(r"[^a-zA-Z]", "", adata.obs[name].dtype.name)
        # Get the function from switcher dictionary
        func = switcher.get(dtype, type_discrete)
        # Define an API key safe
        slug = re.sub(r"[^a-zA-Z0-9]", "", name).lower()
        annotations["obs"][slug] = func(adata.obs[name])
        annotations["obs"][slug]["name"] = name
        annotations["obs"][slug]["category"] = obs_cat.get(name, "")

    annotations["obsm"] = adata.obsm_keys()
    annotations["var"] = adata.var_names.tolist()

    if "masks" in adata.uns and len(adata.uns["masks"].keys()):
        annotations["has_masks"] = True

    return annotations


def get_degs(adata):
    try:
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
        adata.var.sort_values(by=["means"], ascending=False)
        df = (
            adata.var[adata.var["highly_variable"] == True]
            .sort_values(by=["means"], ascending=False)
            .head(10)
        )
        return df.index.tolist()
    except Exception as e:
        return False


def get_bounds(datasetId, obsm):
    if not datasetId > 0:
        raise InvalidDatasetIdError

    try:
        dataset = models.Dataset.query.get(datasetId)
    except exc.SQLAlchemyError as e:
        raise DatabaseOperationError

    try:
        adata = current_app.adata[dataset.filename]
    except (ValueError, AttributeError) as e:
        raise DatasetNotExistsError

    # Normalised [-1,1] @TODO
    adata.obsm[obsm] = (
        2.0 * (adata.obsm[obsm] - np.min(adata.obsm[obsm])) / np.ptp(adata.obsm[obsm])
        - 1
    )

    # Embedded coordinate bounds
    output = {
        "x": {
            "min": adata.obsm[obsm][:, 0].min().item(),
            "max": adata.obsm[obsm][:, 0].max().item(),
        },
        "y": {
            "min": adata.obsm[obsm][:, 1].min().item(),
            "max": adata.obsm[obsm][:, 1].max().item(),
        },
    }

    return output


def get_coordinates(datasetId, obsm):
    if not datasetId > 0:
        raise InvalidDatasetIdError

    try:
        dataset = models.Dataset.query.get(datasetId)
    except exc.SQLAlchemyError as e:
        raise DatabaseOperationError

    try:
        adata = current_app.adata[dataset.filename]
    except (ValueError, AttributeError) as e:
        raise DatasetNotExistsError

    # Normalised [-1,1] @TODO
    adata.obsm[obsm] = (
        2.0 * (adata.obsm[obsm] - np.min(adata.obsm[obsm])) / np.ptp(adata.obsm[obsm])
        - 1
    )

    # True resolution sample generation
    output = []
    for x in adata.obsm[obsm]:
        # output.append(x[:2].tolist())
        output.append([round(num, 4) for num in x[:2].tolist()])

    return output


def get_masks(datasetId):
    dataset = models.Dataset.query.get(datasetId)
    adata = current_app.adata[dataset.filename]

    if "masks" in adata.uns:
        return list(adata.uns["masks"].keys())
    else:
        return []


def get_labels(datasetId, obsm, gene="", obs=""):
    dataset = models.Dataset.query.get(datasetId)
    adata = current_app.adata[dataset.filename]

    if gene:
        try:
            # expression = adata[:,gene].X/max(1,adata[:,gene].X.max())
            gene_idx = adata.var_names.get_loc(gene)
            output = [
                str(round(float(x), 4))
                for x in (
                    adata.X[:, gene_idx].toarray().reshape(-1)
                    if isinstance(adata.X, spmatrix)
                    else adata.X[:, gene_idx]
                )
            ]
        except KeyError:
            # @todo HANDLE ERROR
            output = [0] * len(adata.obs.index)
        except IndexError:
            # @todo HANDLE ERROR
            output = [0] * len(adata.obs.index)
    elif obs:
        try:
            output = adata.obs[obs].fillna(np.nan).astype(str).tolist()
        except KeyError:
            # @todo HANDLE ERROR
            output = [0] * len(adata.obs.index)
        except IndexError:
            # @todo HANDLE ERROR
            output = [0] * len(adata.obs.index)

    return output


def search_genes(datasetId, searchterm):
    dataset = models.Dataset.query.get(datasetId)
    adata = current_app.adata[dataset.filename]
    # adata = current_app.adata
    output = [g for g in adata.var_names if searchterm.lower() in g.lower()]

    return output


def gene_search(datasetId, searchterm):
    dataset = models.Dataset.query.get(datasetId)
    adata = current_app.adata[dataset.filename]
    # adata = current_app.adata
    genes = [g for g in adata.var_names if searchterm in g]

    output = []
    for gene in genes:
        sample = {"name": gene}
        output.append(sample)

    return output


def categorised_expr(datasetId, cat, gene, func="mean"):
    dataset = models.Dataset.query.get(datasetId)
    adata = current_app.adata[dataset.filename]

    data = adata[:, [gene]].to_df()
    grouping = data.join(adata.obs[cat]).groupby(cat)

    if func == "mean":
        expr = grouping.mean()
    elif func == "median":
        expr = grouping.median()

    # counts = grouping.count()/grouping.count().sum()
    # 'count': counts.loc[group,gene]
    output = [
        {"gene": gene, "cat": group, "expr": float(expr.loc[group, gene])}
        for group in grouping.groups.keys()
    ]

    return output


def cat_expr_w_counts(datasetId, cat, gene, func="mean"):
    from numpy import NaN

    dataset = models.Dataset.query.get(datasetId)
    adata = current_app.adata[dataset.filename]

    groupall = adata[:, [gene]].to_df().join(adata.obs[cat]).groupby(cat)
    groupexpr = (
        adata[:, [gene]]
        .to_df()
        .replace(float(adata[:, [gene]].X.min()), NaN)
        .join(adata.obs[cat])
        .groupby(cat)
    )

    if func == "mean":
        expr = groupexpr.mean()
    elif func == "median":
        expr = groupexpr.median()

    countpc = (groupexpr.count() * 100 / groupall.count()).astype(int)

    output = [
        {
            "gene": gene,
            "cat": group,
            "expr": float(expr.loc[group, gene]),
            "count": int(countpc.loc[group, gene]),
        }
        for group in groupall.groups.keys()
    ]

    return output


def mode(d):
    from scipy import stats as s

    mode = s.mode(d)
    return int(mode[0])


def type_category(obs):
    categories = [str(i) for i in obs.cat.categories.values.flatten()]

    if pd.api.types.is_string_dtype(obs.cat.categories.dtype):
        if all(
            obs.str.match(
                "^(\d{4})-(0[1-9]|1[0-2]|[1-9])-([1-9]|0[1-9]|[1-2]\d|3[0-1])$"
            )
        ):
            obs_type = "date"
        else:
            obs_type = "categorical"

    if len(categories) > 100:
        return {
            "type": obs_type,
            "is_truncated": True,
            "values": dict(enumerate(categories[:99], 1)),
        }

    return {
        "type": obs_type,
        "is_truncated": False,
        "values": dict(enumerate(categories, 1)),
    }


def type_bool(obs):
    return {"type": "boolean", "values": {0: "True", 1: "False"}}


def type_numeric(obs):
    accuracy = 4
    return {
        "type": "continuous",
        "min": round(series_min(obs), accuracy),
        "max": round(series_max(obs), accuracy),
        "mean": round(series_mean(obs), accuracy),
        "median": round(series_median(obs), accuracy),
    }


def type_discrete(obs):
    return {"type": "discrete"}


def series_max(s):
    if s.isna().all():
        return 0
    else:
        return s.max().item()


def series_min(s):
    if s.isna().all():
        return 0
    else:
        return s.min().item()


def series_mean(s):
    if s.isna().all():
        return 0
    else:
        return s.mean().item()


def series_median(s):
    if s.isna().all():
        return 0
    else:
        return s.median().item()


def disease_filename():
    return os.path.join(current_app.root_path, "data", "disease.csv")
