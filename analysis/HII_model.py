"""
============
UCHII Fitter
============

Fit a free-free spectrum to an SED.

.. moduleauthor:: Adam Ginsburg <adam.g.ginsburg@gmail.com>

"""
import pylab as pl
import numpy as np
try:
    from scipy import optimize
except ImportError:
    print("scipy not installed: UCHIIfitter may fail")
from pyspeckit import mpfit
from astropy import units as u
from astropy import constants
import radio_beam
from dust_emissivity import dust

#kb = 1.38e-16
#c=3e10
#mu = 1.4
#mh = 1.67e-24
#msun = 1.9889e33
#pc = 3.08568e18      # cm
#au = 1.496e13        # cm
#msun = 1.99e33       # g

unitfactor={'mJy':1e-26,'Jy':1e-23,'cgs':1.0}
freqfactor={'GHz':1e9,'Hz':1.0}
muh = 2.8

default_te = 8500*u.K
default_freq = 1*u.GHz
# using the value from http://www.cv.nrao.edu/~sransom/web/Ch4.html
alpha_b = 3e-13*u.cm**3*u.s**-1

def tnu(Te, nu, EM):
    """

    Parameters
    ----------
    Te : K
        excitation temperature
    nu : GHz
        frequency in GHz
    EM : pc cm^-6
        Emission Measure

    Calculates optical depth as a function of temperature, frequency, and
    emission measure from Rohlfs and Wilson 2000's eqns 9.33 and 9.34.

    """
#    nu0 = .3045 * Te**-.643 * EM**.476
    nu0 = Te**1.5 / 1000
    answer_highnu = (nu > nu0) * 3.014e-2 * Te**-1.5 * nu**-2 * EM
    gff_lownu = (np.log(4.955e-2 * nu**-1) + 1.5 * np.log(Te))  # <gff> Gaunt factor for free-free
    answer_lownu = (nu < nu0) * 3.014e-2 * Te**-1.5 * nu**-2 * EM * gff_lownu
    tau = answer_lownu+answer_highnu
    ## altenhoff version
    #tau = 8.235e-2 * Te**-1.35 * nu**-2.1 * EM
    return tau

def Inu(nu, tau, Te, I0=0):
    """
    Calculates flux for a given optical depth, frequency, and temperature
    assuming Rayleigh-Jeans

    nu - frequency in Hz
    tau - optical depth
    Te - excitation temperature (K)
    """
    if I0==0 and isinstance(nu,np.ndarray):
        whtau1 = np.argmin(np.abs(tau-1))
        nutau1 = nu[whtau1]
        taufactor = 1
    else:
        nutau1 = nu
        taufactor = tau
        """ assumes I0 is set"""
    I0 = 2 * constants.k_B * Te * nutau1**2 / constants.c**2 * taufactor
    thin = (tau < 1) * np.exp(1-tau) * I0
    thick = 2 * constants.k_B * Te * (nu * (tau > 1))**2 / constants.c**2
    return thin+thick

def inufit(nu, em, normfac, Te=8500, unit='mJy', frequnit='GHz'):
    """
    Computes the expected intensity as a function of frequency
    for a given emission measure and normalization factor
    nu - array of frequencies (array)
    em - emission measure (float)
    normfac - normalization factor (float)
            - 1/solid angle of source.  1000 AU at 1 kpc = 206265.

    Units: mJy
    """
    _nu = nu*freqfactor[frequnit]
    I0 = 2 * constants.k_B * Te * _nu[0]**2 / constants.c**2
    model_intensity = Inu(_nu,tnu(Te,_nu/1e9,em),Te,I0=I0)  # tnu takes GHz
    model_norm = normfac * model_intensity / unitfactor[unit]
    return model_norm


#def inorm(em,nu=freq[1],nu0=freq[0],intens0=flux[0],Te=8500):
#    """
#    Not used?
#    """
#    I0 = 2 * constants.k_B * Te * nu0**2 / c**2
#    model_intensity0 = Inu(nu0,tnu(Te,nu0,em),Te,I0=I0)
#    model_intensity = Inu(nu,tnu(Te,nu,em),Te,I0=I0)
#    model_norm = intens0/model_intensity0 * model_intensity
#    return model_norm

def inufit_dust(nu, em, normfac, alpha, normfac2, Te=8500):
    """
    inufit with dust added
    """
    I0 = 2 * constants.k_B * Te * nu[0]**2 / constants.c**2
    model_intensity = Inu(nu,tnu(Te,nu,em),Te,I0=I0)
    model_norm = normfac * model_intensity + normfac2*nu**alpha
    return model_norm

def inufit_dustT(nu, em, normfac, beta, normfac2, dustT, Te=8500):
    I0 = 2 * constants.k_B * Te * nu[0]**2 / constants.c**2
    model_intensity = Inu(nu,tnu(Te,nu,em),Te,I0=I0)
    dustem = 2*constants.h*(nu)**(3+beta) / constants.c**2 * (np.exp(constants.h*nu*1e9/(constants.k_B*np.abs(dustT))) - 1)**-1
    model_norm = normfac * model_intensity + normfac2/np.abs(dustT)*dustem
    return model_norm


def mpfitfun(freq,flux,err=None,dust=False,dustT=False):
    """ wrapper around inufit to be passed into mpfit """
    if dust:
        if err is None:
            def f(p,fjac=None): return [0,(flux-inufit_dust(freq,*p))]
        else:
            def f(p,fjac=None): return [0,(flux-inufit_dust(freq,*p))/err]
        return f
    elif dustT:
        if err is None:
            def f(p,fjac=None): return [0,(flux-inufit_dustT(freq,*p))]
        else:
            def f(p,fjac=None): return [0,(flux-inufit_dustT(freq,*p))/err]
        return f
    else:
        if err is None:
            def f(p,fjac=None): return [0,(flux-inufit(freq,*p))]
        else:
            def f(p,fjac=None): return [0,(flux-inufit(freq,*p))/err]
        return f

def emtau(freq, flux, err=None, EMguess=1e7, Te=8500, normfac=5e-6, quiet=1):
    """
    Returns emission measure & optical depth given radio continuum data points
    at frequency freq with flux density flux.

    return bestEM,nu(tau=1),chi^2
    """
    mp = mpfit(mpfitfun(freq,flux,err),xall=[EMguess,normfac],quiet=quiet)
    mpp = mp.params
    mpperr = mp.perror
    chi2 = mp.fnorm
    bestEM = mpp[0]
    normfac = mpp[1]
    nu_tau = (Te**1.35 / bestEM / 8.235e-2)**(-1/2.1)

    return bestEM,nu_tau,normfac,chi2

class HIIregion(object):
    """
    An HII region has properties frequency, flux, and error, which must be
    numpy ndarrays of the same length
    """

    def __init__(self, nu, flux, fluxerr, fluxunit='mJy', frequnit='GHz',
                 beamsize_as2=0.25, dist_kpc=1.0, resolved=False, Te=8500,
                 **kwargs):
        order = np.argsort(np.asarray(nu))
        self.nu           = np.asarray(nu)[order]
        self.flux         = np.asarray(flux)[order]
        self.fluxerr      = np.asarray(fluxerr)[order]
        self.frequnit     = frequnit
        self.fluxunit     = fluxunit
        self.beamsize_as2 = beamsize_as2
        self.dist_kpc = dist_kpc
        self.resolved = resolved
        self.Te = Te
        self.em, self.nutau, self.normfac, self.chi2 = emtau(self.nu,
                                                             self.flux,
                                                             self.fluxerr,
                                                             Te=self.Te,
                                                             **kwargs)

    def refit(self,**kwargs):
        """ refit, presumably using different inputs to emtau """
        self.em,self.nutau,self.normfac,self.chi2 = emtau(self.nu,self.flux,self.fluxerr,Te=self.Te,**kwargs)

    def loglogplot(self,numin=1.0*u.GHz,numax=10.0*u.GHz,plottitle='',do_annotations=True,**kwargs):
        x = np.linspace(numin,numax,500)
        y = inufit(x,self.em,self.normfac)
        pl.loglog(x,y)
        pl.xlabel('Frequency (GHz)')
        pl.ylabel('Flux Density (mJy)')
        pl.title(plottitle)

        pl.errorbar(self.nu,self.flux,yerr=self.fluxerr,fmt=',',**kwargs)

        self.physprops()
        if do_annotations:
            pl.annotate("size (as): %0.2g" % (self.srcsize/au), [.8, .3],textcoords='axes fraction',xycoords='axes fraction')
            pl.annotate("size (au): %0.2g" % (self.srcsize/au), [.8, .3],textcoords='axes fraction',xycoords='axes fraction')
            pl.annotate("mass (msun): %0.2g" % self.mass, [.8, .25],textcoords='axes fraction',xycoords='axes fraction')
            pl.annotate("EM: %0.2g" % self.em, [.8, .2],textcoords='axes fraction',xycoords='axes fraction')
            pl.annotate("Nu(Tau=1): %0.2g" % self.nutau, [.8, .15],textcoords='axes fraction',xycoords='axes fraction')
            pl.annotate("N(lyc): %0.2g" % self.Nlyc, [.8,.1],textcoords='axes fraction',xycoords='axes fraction')
            pl.annotate("dens: %0.2g" % self.dens, [.8,.05],textcoords='axes fraction',xycoords='axes fraction')

    def physprops(self):
        """
        Get the source size (au), density (cm^-3),
        mass (msun), and Nlyc of the UCHII

        Also return EM and nutau

        ERROR IN CURRENT VERSION
        """
        if self.resolved:
            self.srcsize = self.beamsize_as2 * (self.dist_kpc*1000.0*au)**2
        else:
            self.srcsize = np.sqrt(self.flux[0]*unitfactor[self.fluxunit]/(2*constants.k_B*self.Te)
                                   * (constants.c/(self.nu[0]*freqfactor[self.frequnit]))**2
                                   * (self.dist_kpc*1e3*u.pc)**2 / np.pi)
        self.dens = np.sqrt(self.em/(self.srcsize))
        self.mass = self.dens * 4.0/3.0 * np.pi * self.srcsize**3 * muh * constants.m_p / u.Msun

        U = self.dens**(2/3.) * self.srcsize/u.pc
        self.Nlyc = 8.04e46*self.Te**-.85 * U**3

        return self.srcsize/u.au,self.dens,self.mass,self.Nlyc,self.em,self.nutau



    # Cara test data:
    # nu = array([1.4,5,8.33]); flux=array([4.7,9.2,9.1]); err=array([.52,.24,.07])
    # em,nutau,normfac,chi2 = UCHIIfitter.emtau(nu,flux,err)

def dens(Qlyc=1e45*u.s**-1, R=0.1*u.pc, alpha_b=alpha_b):
    return (((3 * Qlyc)/(4 * np.pi * R**3 * alpha_b))**0.5).to(u.cm**-3)

def EM(Qlyc=1e45*u.s**-1, R=0.1*u.pc, alpha_b=2e-13*u.cm**3*u.s**-1):
    return (R * (((3 * Qlyc)/(4 * np.pi * R**3 *
                              alpha_b))**0.5)**2).to(u.cm**-6*u.pc)

def tau(nu, EM, Te=default_te):
    return (3.28e-7 * (Te/(1e4*u.K))**-1.35 * (nu/u.GHz)**-2.1 *
            (EM/(u.cm**-6*u.pc)))

def Tb(Te=default_te, nu=95*u.GHz, EM=EM()):
    return Te * (1-np.exp(-tau(nu=nu, EM=EM, Te=Te)))
    #return (8.235e-2 * (Te/(u.K))**-0.35 * (nu/u.GHz)**-2.1 * (EM/u.cm**-6/u.pc)*u.K).to(u.K)

def Tb_beamdiluted(Te=default_te, nu=95*u.GHz, R=0.1*u.pc, Qlyc=1e45*u.s**-1,
                   beam=4000*u.au):
    tb = Tb(Te=Te, nu=nu, EM=EM(R=R, Qlyc=Qlyc))
    if beam < R:
        return tb
    else:
        return (tb * (R/beam)**2).to(u.K)

def Snu(Te=default_te, nu=95*u.GHz, R=0.1*u.pc, Qlyc=1e45*u.s**-1, beam=4000*u.au,
        angular_beam=0.5*u.arcsec):
    tb = Tb(Te=Te, nu=nu, EM=EM(R=R, Qlyc=Qlyc))
    if beam < R:
        return tb.to(u.mJy,
                     u.brightness_temperature(radio_beam.Beam(angular_beam),
                                              nu))
    else:
        return (tb * (R/beam)**2).to(u.mJy,
                                     u.brightness_temperature(radio_beam.Beam(angular_beam),
                                                              nu))

def snu_dust(density=1e4*u.cm**-3, Td=40*u.K, radius=4000*u.au,
             distance=8.4*u.kpc, cfreq=95*u.GHz):
    mass = (density * 2.8 * u.Da * 4/3. * radius**3).to(u.M_sun)
    print(mass)
    beam = radio_beam.Beam((radius/distance).to(u.arcsec,
                                                u.dimensionless_angles()))
    flux = dust.snuofmass(nu=cfreq, mass=mass, beamomega=beam, temperature=Td,
                          distance=distance)
    return flux

def EM_of_T(TB, Te=default_te, nu=default_freq):
    " eqn 4.61 of Condon & Ransom inverted "
    return (-3.05e6 * (Te/(1e4*u.K))**1.35 * (nu/u.GHz)**2.1 * np.log(1-TB/Te)
            * u.cm**-6 * u.pc)
    
def qlyc_of_tb(TB, Te=default_te, nu=default_freq, radius=1*u.pc):
    EM = EM_of_T(TB, Te=Te, nu=nu)
    result = (4/3. * np.pi * radius**3 * alpha_b * EM / radius)
    return result.to(u.s**-1)
    return (-4/3. * np.pi * radius**3 * alpha_b * (3.28e-7)**-1 *
            (Te/(1e4*u.K))**1.35 * (nu/u.GHz)**2.1 * np.log(1-TB/Te) * u.cm**-6 *
            u.pc).to(u.s**-1)

__all__ = [tnu,Inu,unitfactor,freqfactor,inufit,emtau,mpfitfun,HIIregion]
