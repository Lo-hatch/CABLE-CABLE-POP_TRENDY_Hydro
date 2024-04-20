#!/usr/bin/env python3
"""
usage: sum_patchcasa.py [-h] [-o output_netcdf] [-v] [-z] [input_netcdf]

Copy Casa output summing the patches on the same grid point.

positional arguments:
  input_netcdf          input netcdf file.

optional arguments:
  -h, --help            show this help message and exit
  -o output_netcdf, --outfile output_netcdf
                        output netcdf file name (default: input-no_patch.nc).
  -v, --verbose         Feedback during copy (default: no feedback).
  -z, --zip             Use netCDF4 variable compression (default: same format
                        as input file).


Example
-------
  python sum_patchcasa.py -o cru_out_casa_2009_2011-no_patch.nc \
      cru_out_casa_2009_2011.nc


History
-------
Written  Matthias Cuntz, Apr 2020
    - from sum_patchfrac.py and casa2d.py
Modified Matthias Cuntz, Jul 2022
    - flake8 compatible
    - Take into account patchfrac, which is Casa output since rev 9053
"""
import sys
import argparse
import time as ptime
import numpy as np
import netCDF4 as nc
import cablepop as cp

# -------------------------------------------------------------------------
# Command line
#

ofile   = None
verbose = False
izip    = False
parser  = argparse.ArgumentParser(
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description=('Copy Casa output summing the patches on the same'
                 ' grid point.'))
parser.add_argument('-o', '--outfile', action='store',
                    default=ofile, dest='ofile', metavar='output_netcdf',
                    help='output netcdf file name (default:'
                    ' input-no_patch.nc).')
parser.add_argument('-v', '--verbose', action='store_true',
                    default=verbose, dest='verbose',
                    help='Feedback during copy (default: no feedback).')
parser.add_argument('-z', '--zip', action='store_true', default=izip,
                    dest='izip',
                    help=('Use netCDF4 variable compression'
                          ' (default: same format as input file).'))
parser.add_argument('ifile', nargs='?', default=None, metavar='input_netcdf',
                    help='input netcdf file.')
args    = parser.parse_args()
ofile   = args.ofile
verbose = args.verbose
izip    = args.izip
ifile   = args.ifile
del parser, args

if ifile is None:
    raise IOError('Input file must be given.')

if verbose:
    tstart = ptime.time()

# -------------------------------------------------------------------------
# Copy data
#

#
# Open files
#
fi = nc.Dataset(ifile, 'r')
if verbose:
    print('Input file:  ', ifile)
# check for patchfrac
if 'patchfrac' not in fi.variables:
    fi.close()
    raise ValueError('variable patchfrac not in input file')

if ofile is None:  # Default output filename
    ofile = cp.set_output_filename(ifile, '-no_patch')
if verbose:
    print('Output file: ', ofile)
if izip:
    fo = nc.Dataset(ofile, 'w', format='NETCDF4')
else:
    if 'file_format' in dir(fi):
        fo = nc.Dataset(ofile, 'w', format=fi.file_format)
    else:
        fo = nc.Dataset(ofile, 'w', format='NETCDF3_64BIT_OFFSET')

# patchfrac with different dimensions
# time is always the first and land the last dimension
patchfrac = fi.variables['patchfrac'][:]
patchfrac1 = patchfrac[0, :]
patchfrac2 = patchfrac[:, :]
patchfrac3 = patchfrac[:, np.newaxis, :]
patchfrac4 = patchfrac[:, np.newaxis, np.newaxis, :]

# Determine number of land points
lats = fi.variables['latitude'][:]
lons = fi.variables['longitude'][:]
sidx = np.zeros(lats.size, dtype=int)
lidx = np.ones(lats.size, dtype=int)
nidx = 0
for i in range(1, lons.size):
    if (lons[i] == lons[i - 1]) and (lats[i] == lats[i - 1]):
        lidx[nidx] += 1
    else:
        nidx += 1
        sidx[nidx] = i
        lidx[nidx] = 1
sidx = sidx[:nidx]
lidx = lidx[:nidx]

# Copy global attributes, adding script
cp.set_global_attributes(fi, fo,
                         add={'history': (ptime.asctime() + ': ' +
                                          ' '.join(sys.argv))})

# Copy dimensions
cp.create_dimensions(fi, fo, changedim={'land': nidx, 'ntile': nidx})

# create static variables (independent of time)
cp.create_variables(fi, fo, time=False, izip=izip, fill=True, chunksizes=False)

# create dynamic variables (time dependent)
cp.create_variables(fi, fo, time=True, izip=izip, fill=True, chunksizes=False)

#
# Copy variables from in to out, summing the patches
#

# copy static and dynamic variables
if verbose:
    print('Copy variables')
nvar = len(fi.variables.keys())
if nvar < 20:
    n10 = 1
else:
    n10 = nvar // 10
n = 0
for ivar in fi.variables.values():
    if verbose and (n > 0) and ((n % n10) == 0):
        print('  {:d}%'.format(int(n / nvar * 100.)))
    n += 1
    ovar  = fo.variables[ivar.name]
    # read whole field, otherwise execution time is increasing sharpely
    invar = ivar[:]
    if ('land' in ivar.dimensions) or ('ntile' in ivar.dimensions):
        if len(invar.shape) == 1:
            ipatchfrac = patchfrac1
        elif len(invar.shape) == 2:
            ipatchfrac = patchfrac2
        elif len(invar.shape) == 3:
            ipatchfrac = patchfrac3
        elif len(invar.shape) == 4:
            ipatchfrac = patchfrac4
        outshape = list(invar.shape)
        outshape[-1] = nidx
        # fill in memory, then write to disk in one go
        out = np.full(outshape, ovar._FillValue)
        if (ivar.name == 'latitude') or (ivar.name == 'longitude'):
            if len(outshape) == 1:
                for i in range(nidx):
                    out[i] = invar[sidx[i]]
            else:
                for i in range(nidx):
                    out[..., i] = invar[..., sidx[i]]
        elif (ivar.name == 'area_gridcell'):
            if len(outshape) == 1:
                for i in range(nidx):
                    out[i] = invar[sidx[i]:sidx[i] + lidx[i]].sum()
            else:
                for i in range(nidx):
                    out[..., i] = invar[..., sidx[i]:sidx[i] + lidx[i]].sum(
                        axis=-1)
        else:
            if len(outshape) == 1:
                for i in range(nidx):
                    out[i] = np.sum(
                        invar[sidx[i]:sidx[i] + lidx[i]] *
                        ipatchfrac[sidx[i]:sidx[i] + lidx[i]])
            else:
                for i in range(nidx):
                    out[..., i] = np.sum(
                        invar[..., sidx[i]:sidx[i] + lidx[i]] *
                        ipatchfrac[..., sidx[i]:sidx[i] + lidx[i]],
                        axis=-1)
    else:
        out = invar
    ovar[:] = out

fi.close()
fo.close()

# -------------------------------------------------------------------------
# Finish

if verbose:
    tstop = ptime.time()
    print('Finished in [s]: {:.2f}'.format(tstop - tstart))
