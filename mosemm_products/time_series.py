#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Fri Mar 22 15:42:52 2019

@author: realrangel

Functions:
    * Open data_files
    * Open spatial filters
    * Apply spatial filters
    * Apply values filter
    * Aggregate by date
    * Export reports
"""
from pathlib2 import Path
import gdal
import numpy as np
import ogr
import xarray as xr

import mosemm_products.data_manager as dmgr


def vector2array(xmin, ymax, cols, rows, res, layer, nodata):
    # Create the destination data source
    targetDS = (
        gdal.GetDriverByName('MEM').Create(
            '', cols, rows, gdal.GDT_Byte
            )
        )

    targetDS.SetGeoTransform((xmin, res, 0, ymax, 0, - res))
    band = targetDS.GetRasterBand(1)
    band.SetNoDataValue(nodata)

    # Rasterize
    err = gdal.RasterizeLayer(
        targetDS,
        [1],
        layer,
        burn_values=[1],
        options=['ALL_TOUCHED=TRUE']
        )

    if err != 0:
        print("error:", err)

    # Read as array
    array = band.ReadAsArray()
    array = array.astype(float)
    array[np.where(array == 0)] = np.nan
    return(np.flipud(array))


def intensity_area(input_data):
    dint_cats = {
        'd4': input_data <= -2,
        'd3': (-2 < input_data) & (input_data <= -1.6),
        'd2': (-1.6 < input_data) & (input_data <= -1.3),
        'd1': (-1.3 < input_data) & (input_data <= -0.8),
        'd0': (-0.8 < input_data) & (input_data <= -0.5),
        'normal': (-0.5 < input_data) & (input_data < 0.5),
        'w0': (0.5 <= input_data) & (input_data < 0.8),
        'w1': (0.8 <= input_data) & (input_data < 1.3),
        'w2': (1.3 <= input_data) & (input_data < 1.6),
        'w3': (1.6 <= input_data) & (input_data < 2),
        'w4': input_data >= 2
        }
    input_data_sum = xr.Dataset(
        data_vars={
            'd4': dint_cats['d4'].sum(dim=['lat', 'lon'], skipna=True),
            'd3': dint_cats['d3'].sum(dim=['lat', 'lon'], skipna=True),
            'd2': dint_cats['d2'].sum(dim=['lat', 'lon'], skipna=True),
            'd1': dint_cats['d1'].sum(dim=['lat', 'lon'], skipna=True),
            'd0': dint_cats['d0'].sum(dim=['lat', 'lon'], skipna=True),
            'normal': dint_cats['normal'].sum(dim=['lat', 'lon'], skipna=True),
            'w0': dint_cats['w0'].sum(dim=['lat', 'lon'], skipna=True),
            'w1': dint_cats['w1'].sum(dim=['lat', 'lon'], skipna=True),
            'w2': dint_cats['w2'].sum(dim=['lat', 'lon'], skipna=True),
            'w3': dint_cats['w3'].sum(dim=['lat', 'lon'], skipna=True),
            'w4': dint_cats['w4'].sum(dim=['lat', 'lon'], skipna=True)
            }
        )
    cells = float(input_data[{'time': -1}].notnull().sum().values)
    return((input_data_sum / cells) * 100)


def magnitude_area(input_data):
    dmag_cats = {
        'not_drought': input_data > 1,
        'm1': (input_data <= -1) & (-3 < input_data),
        'm2': (input_data <= -3) & (-6 < input_data),
        'm3': (input_data <= -6) & (-9 < input_data),
        'm4': (input_data <= -9) & (-12 < input_data),
        'm5': (input_data <= -12)
        }
    not_drought = dmag_cats['not_drought'].sum(
        dim=['lat', 'lon'],
        skipna=True
        )
    input_data_sum = xr.Dataset(
        data_vars={
            'not_drought': not_drought,
            'm1': dmag_cats['m1'].sum(dim=['lat', 'lon'], skipna=True),
            'm2': dmag_cats['m2'].sum(dim=['lat', 'lon'], skipna=True),
            'm3': dmag_cats['m3'].sum(dim=['lat', 'lon'], skipna=True),
            'm4': dmag_cats['m4'].sum(dim=['lat', 'lon'], skipna=True),
            'm5': dmag_cats['m5'].sum(dim=['lat', 'lon'], skipna=True)
            }
        )
    cells = float(input_data[{'time': -1}].notnull().sum().values)
    return((input_data_sum / cells) * 100)


def quantiles(input_data):
    p0 = input_data.quantile(q=0.00, dim=['lat', 'lon']).drop('quantile')
    p25 = input_data.quantile(q=0.25, dim=['lat', 'lon']).drop('quantile')
    p50 = input_data.quantile(q=0.50, dim=['lat', 'lon']).drop('quantile')
    p75 = input_data.quantile(q=0.75, dim=['lat', 'lon']).drop('quantile')
    p100 = input_data.quantile(q=1.00, dim=['lat', 'lon']).drop('quantile')
    return(xr.Dataset(
        data_vars={
            'p0': p0,
            'p25': p25,
            'p50': p50,
            'p75': p75,
            'p100': p100
            }
        ))


def export_ts(data_files, map_files, nodata, output_dir):
    print("    - Importing data.")
    data = xr.open_mfdataset(paths=data_files, concat_dim='time').load()
    dint_header = [
        'd4', 'd3', 'd2', 'd1', 'd0', 'normal', 'w0', 'w1', 'w2', 'w3', 'w4'
        ]
    dmag_header = ['not_drought', 'm1', 'm2', 'm3', 'm4', 'm5']
    quantile_header = ['p0', 'p25', 'p50', 'p75', 'p100']

    for path in map_files:
        vmap = ogr.Open(str(path))
        vmap_layer = vmap.GetLayer(0)
        feature = vmap_layer.GetFeature(0)
        vmap_field = feature.GetFieldDefnRef(0)
        vmap_layer.ResetReading()
        regions_in_map = vmap_layer.GetFeatureCount()
        output_subdir = (
            Path(output_dir) / '/'.join(path.parts[-2:]).split('.')[-2]
            )
        output_subdir.mkdir(parents=True, exist_ok=True)

        for f, vmap_feature in enumerate(vmap_layer):
            # We define an output in-memory OGR dataset
            mmap = ogr.GetDriverByName('Memory').CreateDataSource('out')
            mmap_layer = mmap.CreateLayer('', geom_type=ogr.wkbPolygon)

            # Apply the vmap_field definition from the original to the output
            mmap_layer.CreateField(vmap_field)
            mmap_featdef = mmap_layer.GetLayerDefn()

            # For each feature, get the geometry
            vmap_geom = vmap_feature.GetGeometryRef()

            # Create an output feature
            out_geom = ogr.Feature(mmap_featdef)
            out_geom.SetGeometry(vmap_geom)
            mmap_layer.CreateFeature(out_geom)

            # Create a mask
            res = data.attrs['LatitudeResolution']
            mask = vector2array(
                res=res,
                xmin=min(data.lon.values) - (res / 2),
                ymax=max(data.lat.values) + (res / 2),
                cols=len(data.lon.values),
                rows=len(data.lat.values),
                layer=mmap_layer,
                nodata=nodata
                )

            # Mask and trim the input data
            data_masked = data * mask
            notnulls_cols = (
                data_masked.Drought_intensity.isel(
                    time=-1
                    ).notnull().sum('lat') > 0
                ).values
            notnulls_rows = (
                data_masked.Drought_intensity.isel(
                    time=-1
                    ).notnull().sum('lon') > 0
                ).values
            data_trimmed = data_masked[{
                'lat': notnulls_rows,
                'lon': notnulls_cols
                }]

            # ---- Drought intensity: area fraction ----
            dint_area = intensity_area(
                input_data=data_trimmed.Drought_intensity
                )
            dint_area = dint_area.to_dataframe().reindex(
                labels=dint_header,
                axis=1
                )
            dint_area.index = [
                str(i.year)+str(i.month).zfill(2) for i in dint_area.index
                ]
            dint_area_fname = output_subdir / (
                'dint_area_{id01}_{id02}.csv'.format(
                    id01=vmap_feature.GetField('ID_01'),
                    id02=vmap_feature.GetField('ID_02')
                    )
                )
            dint_area.to_csv(dint_area_fname)

            # ---- Drought intensity: quantiles ----
            dint_quant = quantiles(input_data=data_trimmed.Drought_intensity)
            dint_quant = dint_quant.to_dataframe().reindex(
                labels=quantile_header,
                axis=1
                )
            dint_quant.index = [
                str(i.year)+str(i.month).zfill(2) for i in dint_quant.index
                ]
            dint_quant_fname = output_subdir / (
                'dint_{id01}_{id02}.csv'.format(
                    id01=vmap_feature.GetField('ID_01'),
                    id02=vmap_feature.GetField('ID_02')
                    )
                )
            dint_quant.to_csv(dint_quant_fname)

            # ---- Droght magnitude: area fraction ----
            dmag_area = magnitude_area(
                input_data=data_trimmed.Drought_magnitude
                )
            dmag_area = dmag_area.to_dataframe().reindex(
                labels=dmag_header,
                axis=1
                )
            dmag_area.index = [
                str(i.year)+str(i.month).zfill(2) for i in dmag_area.index
                ]
            dmag_area_fname = output_subdir / (
                'dmag_area_{id01}_{id02}.csv'.format(
                    id01=vmap_feature.GetField('ID_01'),
                    id02=vmap_feature.GetField('ID_02')
                    )
                )
            dmag_area.to_csv(dmag_area_fname)

            # ---- Drought magnitude: quantiles ----
            dmag_quant = quantiles(input_data=data_trimmed.Drought_magnitude)
            dmag_quant = dmag_quant.to_dataframe().reindex(
                labels=quantile_header,
                axis=1
                )
            dmag_quant.index = [
                str(i.year)+str(i.month).zfill(2) for i in dmag_quant.index
                ]
            dmag_quant_fname = output_subdir / 'dmag_{id01}_{id02}.csv'.format(
                id01=vmap_feature.GetField('ID_01'),
                id02=vmap_feature.GetField('ID_02')
                )
            dmag_quant.to_csv(dmag_quant_fname)

            # Progress message.
            dmgr.progress_message(
                current=f + 1,
                total=regions_in_map,
                message="- Processing '{}'".format(path.stem),
                units='feature'
                )

        # Clear things up
        out_geom.Destroy
        vmap_geom.Destroy

        # Reset the output layer to the 0th geometry
        mmap_layer.ResetReading()
