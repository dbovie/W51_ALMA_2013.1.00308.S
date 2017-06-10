import os
import socket

if socket.gethostname() == 'cleese':
    root = '/scratch/aginsbur/w51/alma/'
else:
    root = os.path.expanduser('~/work/w51/alma/')

datapath = os.path.join(root, 'FITS/')
texpath = os.path.join(root, 'tex/')
figurepath = os.path.join(root, 'figures/')
regpath = os.path.join(root, 'regions/')
analysispath = os.path.join(root, 'analysis/')
plotcodepath = os.path.join(root, 'plot_codes/')
observingpath = os.path.join(root, 'observing/')
tablepath = os.path.join(root, 'tables/')
vlapath = os.path.join(os.path.expanduser('~/work/w51/paper_w51_evla/'))
spectrum_path = os.path.join(root, 'FITS/12m/spectra')
merge_spectrum_path = os.path.join(root, 'FITS/merge/spectra')
perseus_synpath = os.path.join(root, 'perseus_synth')
simulation_path = os.path.join(root, 'simulations')

def path(x, basepath):
    return os.path.join(basepath, x)

def fpath(x, figurepath=figurepath):
    return os.path.join(figurepath, x)

def rpath(x, regpath=regpath):
    return os.path.join(regpath, x)

def opath(x, observingpath=observingpath):
    return os.path.join(observingpath, x)

def pcpath(x, plotcodepath=plotcodepath):
    return os.path.join(plotcodepath, x)

def apath(x, analysispath=analysispath):
    return os.path.join(analysispath, x)

def dpath(x, datapath=datapath):
    return os.path.join(datapath, x)

def dppath(x, datapath=datapath):
    return os.path.join(datapath, 'projections', x)

def tpath(x, tablepath=tablepath):
    return os.path.join(tablepath, x)

def texpath(x, texpath=texpath):
    return os.path.join(texpath, x)

def vpath(x, vlapath=vlapath):
    return os.path.join(vlapath, x)

def spath(x, spectrum_path=spectrum_path):
    return os.path.join(spectrum_path, x)

def merge_spath(x, spectrum_path=merge_spectrum_path):
    return os.path.join(spectrum_path, x)

def pspath(x):
    return path(x, perseus_synpath)

def simpath(x):
    return path(x, simulation_path)

def lbpath(x):
    return os.path.join(datapath, 'longbaseline', x)
