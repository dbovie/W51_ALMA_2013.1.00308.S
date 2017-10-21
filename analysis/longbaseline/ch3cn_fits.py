"""
copied from Sgr B2
"""
import numpy as np
import pyspeckit
from astropy.utils.console import ProgressBar
from pyspeckit.spectrum.models import model
from pyspeckit.spectrum.models import lte_molecule
from spectral_cube import SpectralCube
from astropy import units as u
from astropy import constants
from astropy import log
from astropy.io import fits
from astroquery.splatalogue import Splatalogue
from astropy import modeling

from vamdclib import nodes
from vamdclib import request as r
from vamdclib import specmodel as m
from vamdclib import specmodel

tbl = Splatalogue.query_lines(210*u.GHz, 235*u.GHz, chemical_name='CH3CN',
                              energy_max=1840, energy_type='eu_k')
freqs = np.unique(tbl['Freq-GHz'])
vdiff = (np.array((freqs-freqs[0])/freqs[0])*constants.c).to(u.km/u.s)
slaim = Splatalogue.query_lines(210*u.GHz, 235*u.GHz, chemical_name='CH3CN',
                                energy_max=1840, energy_type='eu_k',
                                line_lists=['SLAIM'],
                                noHFS=True, # there seems to be a problem where HFS
                                # for K >= 6 is included *incorrectly*
                                show_upper_degeneracy=True)
freqs = np.array(slaim['Freq-GHz'])*u.GHz
aij = slaim['Log<sub>10</sub> (A<sub>ij</sub>)']
deg = slaim['Upper State Degeneracy']
EU = (np.array(slaim['E_U (K)'])*u.K*constants.k_B).to(u.erg).value
ref_freq = 220.74726*u.GHz
vdiff = (np.array(-(freqs-ref_freq)/ref_freq)*constants.c).to(u.km/u.s).value



nl = nodes.Nodelist()
nl.findnode('cdms')
cdms = nl.findnode('cdms')

request = r.Request(node=cdms)


# Retrieve all species from CDMS
result = request.getspecies()
molecules = result.data['Molecules']

ch3cn = [x for x in molecules.values()
         if hasattr(x,'MolecularWeight') and
         (x.StoichiometricFormula)==('C2H3N')
         and x.MolecularWeight=='41'][0]

ch3cn_inchikey = ch3cn.InChIKey

# query everything for ch3cn
query_string = "SELECT ALL WHERE VAMDCSpeciesID='%s'" % ch3cn.VAMDCSpeciesID
request.setquery(query_string)
result = request.dorequest()
vamdc_result = result



def ch3cn_model(xarr, vcen, width, tex, column, background=None, tbg=2.73):

    if hasattr(tex,'unit'):
        tex = tex.value
    if hasattr(tbg,'unit'):
        tbg = tbg.value
    if hasattr(column, 'unit'):
        column = column.value
    if column < 25:
        column = 10**column
    if hasattr(vcen, 'unit'):
        vcen = vcen.value
    if hasattr(width, 'unit'):
        width = width.value

    if background is not None:
        tbg = background

    # assume equal-width channels
    kwargs = dict(rest=ref_freq)
    equiv = u.doppler_radio(**kwargs)
    channelwidth = np.abs(xarr[1].to(u.Hz, equiv) - xarr[0].to(u.Hz, equiv)).value
    velo = xarr.to(u.km/u.s, equiv).value
    mol_model = np.zeros_like(xarr).value

    freqs_ = freqs.to(u.Hz).value

    Q = m.calculate_partitionfunction(result.data['States'],
                                      temperature=tex)[ch3cn.Id]

    jnu_bg = lte_molecule.Jnu_cgs(xarr.to(u.Hz).value, tbg)
    bg_model = np.ones_like(xarr).value * jnu_bg

    for voff, A, g, nu, eu in zip(vdiff, aij, deg, freqs_, EU):
        tau_per_dnu = lte_molecule.line_tau_cgs(tex,
                                                column,
                                                Q,
                                                g,
                                                nu,
                                                eu,
                                                10**A)
        s = np.exp(-(velo-vcen-voff)**2/(2*width**2))*tau_per_dnu/channelwidth
        jnu_mol = lte_molecule.Jnu_cgs(nu, tex)

        # the "emission" model is generally zero everywhere, so we can just
        # add to it as we move along
        mol_model = mol_model + jnu_mol*(1-np.exp(-s))

        # background is assumed to start as a uniform value, then each
        # absorption line multiplies to reduce it.  s is zero for most velocities,
        # so this is mostly bg_model *= 1
        bg_model *= np.exp(-s)

    if background:
        # subtract jnu_bg because we *must* rezero for the case of
        # having multiple components, otherwise the backgrounds add,
        # which is nonsense
        model = bg_model + mol_model - jnu_bg
    else:
        model = mol_model

    return model

def nupper_of_kkms(kkms, freq, Aul, degeneracies):
    """ Derived directly from pyspeckit eqns..."""
    freq = u.Quantity(freq, u.GHz)
    Aul = u.Quantity(Aul, u.Hz)
    kkms = u.Quantity(kkms, u.K*u.km/u.s)
    #nline = 1.95e3 * freq**2 / Aul * kkms
    nline = 8 * np.pi * freq * constants.k_B / constants.h / Aul / constants.c**2
    # term2 = np.exp(-constants.h*freq/(constants.k_B*Tex)) -1
    # term2 -> kt / hnu
    # kelvin-hertz
    Khz = (kkms * (freq/constants.c)).to(u.K * u.MHz)
    return (nline * Khz / degeneracies).to(u.cm**-2)

def fit_tex(eupper, nupperoverg, errors=None, verbose=False, plot=False):
    """
    Fit the Boltzmann diagram
    """
    model = modeling.models.Linear1D()
    #fitter = modeling.fitting.LevMarLSQFitter()
    fitter = modeling.fitting.LinearLSQFitter()
    # ignore negatives
    good = nupperoverg > 0
    if good.sum() < len(nupperoverg)/2.:
        return 0*u.cm**-2, 0*u.K, 0, 0
    if errors is not None:
        weights = 1/errors**2
    else:
        weights=None
    result = fitter(model, eupper[good], np.log(nupperoverg[good]),
                    weights=weights[good])
    tex = -1./result.slope*u.K

    assert not np.isnan(tex)

    partition_func = specmodel.calculate_partitionfunction(vamdc_result.data['States'],
                                                           temperature=tex.value)[ch3cn.Id]
    Q_rot = partition_func

    Ntot = np.exp(result.intercept + np.log(Q_rot)) * u.cm**-2

    if verbose:
        print(("Tex={0}, Ntot={1}, Q_rot={2}".format(tex, Ntot, Q_rot)))

    if plot:
        import pylab as pl
        if errors is not None:
            L,_,_ = pl.errorbar(x=eupper.value, y=np.log10(nupperoverg),
                                marker='o', linestyle='none',
                                yerr=np.array([np.log10(nupperoverg)-np.log10(nupperoverg-errors),
                                               np.log10(nupperoverg+errors)-np.log10(nupperoverg)]))
        else:
            L, = pl.plot(eupper, np.log10(nupperoverg), 'o')
        xax = np.array([0, eupper.max().value])
        line = (xax*result.slope.value +
                result.intercept.value)
        pl.plot(xax, np.log10(np.exp(line)), '-', color=L.get_color(),
                label='$T={0:0.1f} \log(N)={1:0.1f}$'.format(tex, np.log10(Ntot.value)))

    return Ntot, tex, result.slope, result.intercept

def fit_all_tex(xaxis, cube, cubefrequencies, degeneracies,
                einsteinAij,
                errorcube=None,
                replace_bad=False):
    """
    Parameters
    ----------
    replace_bad : bool
        Attempt to replace bad (negative) values with their upper limits?
    """

    tmap = np.empty(cube.shape[1:])
    Nmap = np.empty(cube.shape[1:])

    yy,xx = np.indices(cube.shape[1:])
    pb = ProgressBar(xx.size)
    count=0

    for ii,jj in (zip(yy.flat, xx.flat)):
        if any(np.isnan(cube[:,ii,jj])):
            tmap[ii,jj] = np.nan
        else:
            if replace_bad:
                neg = cube[:,ii,jj] <= 0
                cube[neg,ii,jj] = replace_bad
            nuppers = nupper_of_kkms(cube[:,ii,jj], cubefrequencies,
                                     einsteinAij, degeneracies)
            if errorcube is not None:
                enuppers = nupper_of_kkms(errorcube[:,ii,jj], cubefrequencies,
                                          einsteinAij, degeneracies)
            fit_result = fit_tex(xaxis, nuppers.value, errors=enuppers.value)
            tmap[ii,jj] = fit_result[1].value
            Nmap[ii,jj] = fit_result[0].value
        pb.update(count)
        count+=1

    return tmap,Nmap

#def ch3cn_noline_model(xarr, tex, column, width=1*u.km/u.s, tbg=2.73):
#    """
#    Model for the integrated CH3CN line parameters
#    (fitting the integrated lines independently from the gaussians
#    prevents the model from underestimating line profiles)
#    """
#
#    if hasattr(tex,'unit'):
#        tex = tex.value
#    if hasattr(tbg,'unit'):
#        tbg = tbg.value
#    if hasattr(column, 'unit'):
#        column = column.value
#    if column < 25:
#        column = 10**column
#
#    model = np.zeros_like(xarr).value
#
#    freqs_ = freqs.to(u.Hz).value
#
#    Q = m.calculate_partitionfunction(result.data['States'],
#                                      temperature=tex)[ch3cn.Id]
#
#    for voff, A, g, nu, eu in zip(vdiff, aij, deg, freqs_, EU):
#        tau_per_dnu = lte_molecule.line_tau_cgs(tex,
#                                                column,
#                                                Q,
#                                                g,
#                                                nu,
#                                                eu,
#                                                10**A)
#
#        # jnu in kelvin
#        jnu_tex = lte_molecule.Jnu_cgs(nu, tex)
#        jnu_tbg = lte_molecule.Jnu_cgs(nu, tbg)
#
#        # ii...
#        model[ii] = (jnu_tex-jnu_tbg)*(1-np.exp(-tau_per_dnu))
#
#    return model

line_names = ["HNCO 1019_918", "CH3CN 12_7", "CH3CN 12_6", "CH13CN 12_3",
              "CH13CN 12_2", "CH3CN 12_5", "unknown",
              "CH13CN 12_1", "CH13CN 12_0",
              "CH3CN 12_4",
              "CH3CN 12_3", "CH3CN 12_2", "CH3CN 12_1", "CH3CN 12_0"]
frequencies = [220.58476, 220.53933,  220.59443, 220.59999, 220.62114,
               220.64109, 220.619030262,
               220.63384,
               220.63807,
               220.67929, 220.70902, 220.73026,
               220.74301, 220.74726]
line_name_dict = dict(zip(line_names, frequencies))

line_eu = {line: EU[np.argmin(np.abs(freqs-line_name_dict[line]*u.GHz))]
           for line in line_name_dict if 'CH3CN' in line}
line_deg = {line: deg[np.argmin(np.abs(freqs-line_name_dict[line]*u.GHz))]
            for line in line_name_dict if 'CH3CN' in line}
line_aij = {line: aij[np.argmin(np.abs(freqs-line_name_dict[line]*u.GHz))]
            for line in line_name_dict if 'CH3CN' in line}

def multigaussian_model(xarr, vcen, width, amp1, amp2, amp3, amp4, amp5, amp6,
                        amp7, amp8, amp9, amp10, amp11, amp12, amp13, amp14,
                        background=0.0):
    log.debug("lines = {0}".format(zip(line_names, frequencies)))

    xarr_frq = xarr.as_unit(u.GHz).value

    model = np.zeros(xarr.shape) + background
    for freq,amp in zip(frequencies, (amp1, amp2, amp3, amp4, amp5, amp6, amp7,
                                      amp8, amp9, amp10, amp11, amp12, amp13,
                                      amp14)):
        fcen = freq*(1-u.Quantity(vcen, u.km/u.s) / constants.c).decompose().value
        fwidth = (u.Quantity(width,u.km/u.s)/constants.c).decompose().value * fcen
        model += amp * np.exp(-(xarr_frq-fcen)**2 / (2*fwidth**2))

    return model

def ch3cn_spw_fitter():
    """
    Generator for a multigaussian fitter covering the target spw
    """

    myclass = model.SpectralModel(multigaussian_model, 17,
            parnames=['shift','width', "HNCO 1019_918", "CH3CN 12_7",
                      "CH3CN 12_6", "CH13CN 12_3", "CH13CN 12_2", "CH3CN 12_5",
                      "unknown", "CH13CN 12_1", "CH13CN 12_0", "CH3CN 12_4",
                      "CH3CN 12_3", "CH3CN 12_2", "CH3CN 12_1", "CH3CN 12_0",
                      'background'],
            parlimited=[(False,False),(True,False)]+[(False,False)]*14+[(True,False)],
            parlimits=[(0,0),]*17,
            shortvarnames=(r'\Delta x',r'\sigma',
                           "HNCO 1019_918", "CH3CN 12_7",
                           "CH3CN 12_6", "CH_3^{13}CN 12_3", "CH_3^{13}CN 12_2", "CH3CN 12_5",
                           "unknown", "CH_3^{13}CN 12_1", "CH_3^{13}CN 12_0", "CH3CN 12_4",
                           "CH3CN 12_3", "CH3CN 12_2", "CH3CN 12_1", "CH3CN 12_0",
                           'T_{BG}'),
            centroid_par='shift',)
    myclass.__name__ = "multigauss"
    
    return myclass

pyspeckit.spectrum.fitters.default_Registry.add_fitter('ch3cn_spw',ch3cn_spw_fitter(),17)

def ch3cn_fitter():
    """
    Generator for CH3CN fitter class
    """

    myclass = model.SpectralModel(ch3cn_model, 4,
            parnames=['shift','width','tex','column'],
            parlimited=[(False,False),(True,False),(True,False),(True,False)],
            parlimits=[(0,0), (0,0), (0,0),(0,0)],
            shortvarnames=(r'\Delta x',r'\sigma','T_{ex}','N'),
            centroid_par='shift',
            )
    myclass.__name__ = "ch3cn"
    
    return myclass

pyspeckit.spectrum.fitters.default_Registry.add_fitter('ch3cn',ch3cn_fitter(),4)

def ch3cn_absorption_fitter():
    """
    Generator for CH3CN absorption fitter class
    """

    myclass = model.SpectralModel(ch3cn_model, 5,
            parnames=['shift','width','tex','column','background'],
            parlimited=[(False,False),(True,False),(True,False),(True,False),(True,False)],
            parlimits=[(0,0), (0,0), (0,0),(0,0),(0,0)],
            shortvarnames=(r'\Delta x',r'\sigma','T_{ex}','N','T_{BG}'),
            centroid_par='shift',
            )
    myclass.__name__ = "ch3cn_absorption"
    
    return myclass

pyspeckit.spectrum.fitters.default_Registry.add_fitter('ch3cn_absorption',ch3cn_absorption_fitter(),5)


if __name__ == "__main__" and False:
    import paths
    cube = SpectralCube.read(paths.dpath('longbaseline/W51e2e_CH3CN_cutout.fits'))
    sp_ = cube[:,43,43]
    hdr = sp_.header
    hdr['BUNIT'] = 'K'
    sphdu = fits.PrimaryHDU(data=sp_.to(u.K, u.brightness_temperature(cube.beam,
                                                                      cube.wcs.wcs.restfrq*u.Hz)).value,
                            header=hdr)
    sp = pyspeckit.Spectrum.from_hdu(sphdu)
    sp.data -= np.percentile(sp.data, 25)
    sp.plotter()
    sp.specfit(fittype='ch3cn', guesses=[62, 2, 500, 1e16])

    # do it again, excluding k=0 and k=1
    sp2 = sp[:400]
    sp2.plotter()
    sp2.specfit(fittype='ch3cn', guesses=[62, 2, 500, 1e16])

    F = False
    T = True

    sp.specfit(fittype='ch3cn_spw', guesses=[62, 2,]+[100]*14 + [0],
               fixed=[F]*16+[T])
