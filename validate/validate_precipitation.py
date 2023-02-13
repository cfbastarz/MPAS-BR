#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Feb  8 09:52:10 2023

@author: daniloceano
"""
import glob
import argparse
import f90nml
import datetime

import numpy as np
import pandas as pd
import xarray as xr
import cmocean.cm as cmo
import cartopy.crs as ccrs

import scipy.stats as st
import skill_metrics as sm

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from matplotlib import rcParams

def get_times_nml(namelist,model_data):
    ## Identify time range of simulation using namelist ##
    # Get simulation start and end dates as strings
    start_date_str = namelist['nhyd_model']['config_start_time']
    run_duration_str = namelist['nhyd_model']['config_run_duration']
    # Convert strings to datetime object
    start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d_%H:%M:%S')
    
    run_duration = datetime.datetime.strptime(run_duration_str,'%d_%H:%M:%S')
    # Get simulation finish date as object and string
    finish_date  = start_date + datetime.timedelta(days=run_duration.day,
                                                   hours=run_duration.hour)
    ## Create a range of dates ##
    times = pd.date_range(start_date,finish_date,periods=len(model_data.Time)+1)[1:]
    return times

def get_exp_name(bench):
    expname = bench.split('/')[-1].split('run.')[-1]
    microp = expname.split('.')[0].split('_')[-1]
    cumulus = expname.split('.')[-1].split('_')[-1] 
    return microp+'_'+cumulus

def get_model_accprec(model_data):
    if ('rainnc' in model_data.variables
        ) and ('rainc' in model_data.variables):
        acc_prec = model_data['rainnc']+model_data['rainc']
    # Get only micrphysics precipitation
    elif ('rainnc' in model_data.variables
        ) and ('rainc' not in model_data.variables):
        acc_prec = model_data['rainnc']
    # Get convective precipitation
    elif ('rainnc' not in model_data.variables
        ) and ('rainc' in model_data.variables):
        acc_prec = model_data['rainc'] 
    elif ('rainnc' not in model_data.variables
        ) and ('rainc' not in model_data.variables):
        acc_prec = model_data.uReconstructMeridional[0]*0
    return acc_prec[-1]

def plot_taylor(sdevs,crmsds,ccoefs,experiments):
    '''
    Produce the Taylor diagram
    Label the points and change the axis options for SDEV, CRMSD, and CCOEF.
    Increase the upper limit for the SDEV axis and rotate the CRMSD contour 
    labels (counter-clockwise from x-axis). Exchange color and line style
    choices for SDEV, CRMSD, and CCOEFF variables to show effect. Increase
    the line width of all lines.
    For an exhaustive list of options to customize your diagram, 
    please call the function at a Python command line:
    >> taylor_diagram
    '''
    # Set the figure properties (optional)
    rcParams.update({'font.size': 14}) # font size of axes text
    STDmax = round(np.amax(sdevs))
    RMSmax = round(np.amax(crmsds))
    tickRMS = np.linspace(0,round(RMSmax*1.2,1),6)
    axismax = round(STDmax*1.2,1)
    sm.taylor_diagram(sdevs,crmsds,ccoefs,
                      markerLabelColor = 'b', 
                      markerLabel = experiments,
                      markerColor = 'r', markerLegend = 'on', markerSize = 15, 
                      tickRMS = tickRMS, titleRMS = 'off', widthRMS = 2.0,
                      colRMS = '#728B92', styleRMS = '--',  
                      widthSTD = 2, styleSTD = '--', colSTD = '#8A8A8A',
                      titleSTD = 'on',
                      colCOR = 'k', styleCOR = '-',
                      widthCOR = 1.0, titleCOR = 'off',
                      colObs = 'k', markerObs = '^',
                      titleOBS = 'IMERG', styleObs =':',
                      axismax = axismax, alpha = 1)

## Parser options ##
parser = argparse.ArgumentParser()

parser.add_argument('-bdir','--bench_directory', type=str, required=True,
                        help='''path to benchmark directory''')
parser.add_argument('-i','--imerg', type=str, default=None, required=True,
                        help='''path to IMERG data''')
parser.add_argument('-o','--output', type=str, default=None,
                        help='''output name to append file''')

args = parser.parse_args()

## Start the code ##
benchs = glob.glob(args.bench_directory+'/run*')
# Dummy for getting model times
model_output = benchs[0]+'/latlon.nc'
namelist_path = benchs[0]+"/namelist.atmosphere"
# open data and namelist
model_data = xr.open_dataset(model_output)
namelist = f90nml.read(glob.glob(namelist_path)[0])
times = get_times_nml(namelist,model_data)

first_day = datetime.datetime.strftime(times[0], '%Y-%m-%d')
last_day = datetime.datetime.strftime(times[-2], '%Y-%m-%d')
imerg = xr.open_dataset(args.imerg).sel(lat=slice(model_data.latitude[-1],
                 model_data.latitude[0]),lon=slice(model_data.longitude[0],
                model_data.longitude[-1])).sel(time=slice(first_day,last_day))
imerg_accprec = imerg.precipitationCal.cumsum(dim='time')[-1]

print('Opening all data and putting it into a dictionary...')
data = {}
data['IMERG'] = imerg_accprec
for bench in benchs:
    
    experiment = get_exp_name(bench)
    print(experiment)
    
    model_data = xr.open_dataset(bench+'/latlon.nc')
    model_data = model_data.assign_coords({"Time":times})

    acc_prec = get_model_accprec(model_data)
    acc_prec_interp = acc_prec.interp(latitude=imerg_accprec.lat,
                                      longitude=imerg_accprec.lon,
                                      method='cubic')
    data[experiment] = {}
    data[experiment]['data'] = acc_prec
    data[experiment]['interp'] = acc_prec_interp

# =============================================================================
# Plot acc prec maps and bias
# =============================================================================
print('\nPlotting maps...')
plt.close('all')
fig1 = plt.figure(figsize=(10, 16))
fig2 = plt.figure(figsize=(8, 16))
gs1 = gridspec.GridSpec(6, 3)
gs2 = gridspec.GridSpec(6, 3)
datacrs = ccrs.PlateCarree()

i = 0
for col in range(3):
    for row in range(6):
        
        bench = benchs[i]
        experiment = get_exp_name(bench)
        print('\n',experiment)
        
        prec = data[experiment]['data']
        prec_interp = data[experiment]['interp']
        
        ax1 = fig1.add_subplot(gs1[row, col], projection=datacrs,frameon=True)
        ax2 = fig2.add_subplot(gs1[row, col], projection=datacrs,frameon=True)
        
        for ax in [ax1,ax2]:
            ax.set_extent([-55, -30, -20, -35], crs=datacrs) 
            gl = ax.gridlines(draw_labels=True,zorder=2,linestyle='dashed',
                              alpha=0.8, color='#383838')
            gl.xlabel_style = {'size': 12, 'color': '#383838'}
            gl.ylabel_style = {'size': 12, 'color': '#383838'}
            gl.right_labels = None
            gl.top_labels = None
            if row != 5:
                gl.bottom_labels = None
            if col != 0:
                gl.left_labels = None
        
            ax.text(-50,-19,experiment)
            
            if ax == ax1:
                print('Plotting accumulate prec..')
                cf1 = ax.contourf(prec.longitude, prec.latitude, prec,
                                  cmap=cmo.rain, vmin=0)
                fig1.colorbar(cf1, ax=ax1, fraction=0.03, pad=0.1,
                              orientation='vertical')
            else:
                print('Plotting bias..')
                bias = prec_interp-imerg_accprec
                cf2 = ax.contourf(imerg_accprec.lon, imerg_accprec.lat,bias,
                                 cmap=cmo.balance_r,
                                 levels=np.linspace(-700,400,21))
                print('bias limits:',float(bias.min()), float(bias.max()))
            ax.coastlines(zorder = 1)
        
        i+=1
    
cb_axes = fig2.add_axes([0.85, 0.18, 0.04, 0.6])
fig2.colorbar(cf2, cax=cb_axes, orientation="vertical")    

fig1.subplots_adjust(wspace=0.4,hspace=-0.15)
fig2.subplots_adjust(wspace=0.1,hspace=-0.3, right=0.8)
    
if args.output is not None:
    fname = args.output
else:
    fname = (args.bench_directory).split('/')[-2].split('.nc')[0]
fname1 = fname+'_acc_prec'
fname2 = fname+'_acc_prec_bias'
fig1.savefig(fname1+'.png', dpi=500)
fig2.savefig(fname2+'.png', dpi=500)
print(fname1,'and',fname1,'saved')

# =============================================================================
# Plot IMERG ac prec
# =============================================================================
print('\nPlotting CHIRPS data..')
plt.close('all')
fig = plt.figure(figsize=(10, 10))
datacrs = ccrs.PlateCarree()
ax = fig.add_subplot(111, projection=datacrs,frameon=True)
ax.set_extent([-55, -30, -20, -35], crs=datacrs) 
gl = ax.gridlines(draw_labels=True,zorder=2,linestyle='dashed',
                  alpha=0.8, color='#383838')
gl.xlabel_style = {'size': 12, 'color': '#383838'}
gl.ylabel_style = {'size': 12, 'color': '#383838'}
gl.right_labels = None
gl.top_labels = None
cf = ax.contourf(imerg_accprec.lon, imerg_accprec.lat,
                 imerg_accprec.T, cmap=cmo.rain, vmin=0,
                 levels=np.linspace(0,imerg_accprec.T.max(),21))
fig.colorbar(cf, ax=ax, fraction=0.03, pad=0.1)
ax.coastlines(zorder = 1)

imergname = args.imerg.split('/')[-1].split('.nc')[0]
fig.savefig(imergname+'.png', dpi=500)
print(imergname,'saved')

# =============================================================================
# PDFs
# =============================================================================
print('\nPlotting PDFs..')
nbins = 100
params_imerg = st.gamma.fit(imerg_accprec.values.ravel())
x_imerg = np.linspace(st.gamma.ppf(0.01, *params_imerg),
                st.gamma.ppf(0.99, *params_imerg), nbins)
pdf_imerg = st.gamma.pdf(x_imerg, *params_imerg)

plt.close('all')
fig = plt.figure(figsize=(10, 16))
gs = gridspec.GridSpec(6, 3)

ccoef, crmsd, sdev = [], [], []

i = 0
for col in range(3):
    for row in range(6):
    
        ax = fig.add_subplot(gs[row, col], frameon=True)
    
        bench = benchs[i]
        experiment = get_exp_name(bench)
        print('\n',experiment)
        
        reference = imerg_accprec.values.ravel()
        predicted = prec_interp.values.ravel()
        
        stats = sm.taylor_statistics(predicted,reference)
        ccoef.append(stats['ccoef'][1])
        crmsd.append(stats['crmsd'][1])
        sdev.append(stats['sdev'][1])
        
        if experiment != 'off_off':
        
            prec_interp = data[experiment]['interp']
            
            params = st.gamma.fit(prec_interp.values.ravel())
            x = np.linspace(st.gamma.ppf(0.01, *params),
                            st.gamma.ppf(0.99, *params), nbins)
            pdf = st.gamma.pdf(x, *params)
    
            # Plot imerg PDF
            ax.plot(x_imerg, pdf_imerg, 'tab:blue', lw=0.5, alpha=0.3,
                    label='IMERG', zorder=1)
            ax.fill_between(x_imerg, pdf_imerg, 0, alpha=0.3,
                            facecolor='tab:blue',zorder=2)
            # Plot MPAS PDF
            ax.plot(x, pdf, 'tab:red', lw=0.5, alpha=0.3, label=experiment,
                    zorder=100)
            ax.fill_between(x, pdf, 0, alpha=0.3, facecolor='tab:red',
                            zorder=101)
                    
            # ax.set_xscale('log')
            ax.set_yscale('log')         
            ax.legend()
            
            i+=1
            
            
fig.subplots_adjust(hspace=0.25)
fig.savefig(fname+'_PDF.png', dpi=500)    
print(fname+'_PDF','saved')

## Plot Taylor Diagrams ##
ccoef, crmsd, sdev = np.array(ccoef),np.array(crmsd),np.array(sdev)
print('plotting taylor diagrams..')
fig = plt.figure(figsize=(10,10))
plot_taylor(sdev,crmsd,ccoef,list(data.keys()))
plt.tight_layout(w_pad=0.1)
fig.savefig(fname+'_prec-taylor.png', dpi=500)    
print(fname+'_prec-taylor created!')