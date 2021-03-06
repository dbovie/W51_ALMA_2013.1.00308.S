import paths
import itertools
import numpy as np
from astropy import units as u
from astropy import constants
from astropy import coordinates
from astropy.utils.console import ProgressBar
from astropy import log
from astropy.io import fits
from astropy import wcs
import image_tools

from pyspeckit.spectrum.models import lte_molecule

from astroquery.vamdc import Vamdc
from vamdclib import specmodel

from astropy import modeling

import re
import glob

from line_to_image_list import line_to_image_list
frequencies = u.Quantity([float(row[1].strip('GHz'))
                          for row in line_to_image_list], u.GHz)
name_to_freq = {row[0]:frq for frq, row in zip(frequencies, line_to_image_list)}
freq_to_name = {frq:row[0] for frq, row in zip(frequencies, line_to_image_list)}

hnco = Vamdc.query_molecule('Isocyanic acid HNCO')
rt = hnco.data['RadiativeTransitions']
frqs = u.Quantity([(float(rt[key].FrequencyValue)*u.MHz).to(u.GHz,
                                                            u.spectral())
                   for key in rt])

frqs_to_ids = {frq: key for frq,key in zip(frqs, rt)}

upperStateRefs = [rt[key].UpperStateRef for key in rt]
degeneracies = [int(hnco.data['States'][upperStateRef].TotalStatisticalWeight)
                for upperStateRef in upperStateRefs]
einsteinAij = u.Quantity([float(rt[key].TransitionProbabilityA) for key in rt], 1/u.s)

# http://www.astro.uni-koeln.de/cdms/catalog#equations
# the units are almost certainly wrong; I don't know how to compute line strength
# from aij =(
line_strengths_smu2 = u.Quantity([(frq**-3 * deg / 1.16395e-20 * Aij).value
                                  for frq,deg,Aij in zip(frqs, degeneracies, einsteinAij)],
                                 u.esu*u.cm)


from ch3oh_rotational_diagram_maps import nupper_of_kkms, cutout_id_chem_map

def fit_tex(eupper, nupperoverg, verbose=False, plot=False, uplims=None,
            errors=None, min_nupper=1,
            replace_errors_with_uplims=False,
            max_uplims='half'):
    """
    Fit the Boltzmann diagram

    Parameters
    ----------
    max_uplims: str or number
        The maximum number of upper limits before the fit is ignored completely
        and instead zeros are returned
    """
    model = modeling.models.Linear1D()
    #fitter = modeling.fitting.LevMarLSQFitter()
    fitter = modeling.fitting.LinearLSQFitter()

    nupperoverg_tofit = nupperoverg.copy()

    if uplims is not None:
        upperlim_mask = nupperoverg < uplims

        # allow this magical keyword 'half'
        max_uplims = len(nupperoverg)/2. if max_uplims == 'half' else max_uplims

        if upperlim_mask.sum() > max_uplims:
            # too many upper limits = bad idea to fit.
            return 0*u.cm**-2, 0*u.K, 0, 0
        
        if errors is None:
            # if errors are not specified, we set the upper limits as actual values
            # (which gives a somewhat useful upper limit on the temperature)
            nupperoverg_tofit[upperlim_mask] = uplims[upperlim_mask]
        else:
            # otherwise, we set the values to zero-column and set the errors to
            # be whatever the upper limits are (hopefully a 1-sigma upper
            # limit)
            # 1.0 here becomes 0.0 in log and makes the relative errors meaningful
            nupperoverg_tofit[upperlim_mask] = 1.0
            if replace_errors_with_uplims:
                errors[upperlim_mask] = uplims[upperlim_mask]

    # always ignore negatives & really low values
    good = nupperoverg_tofit > min_nupper
    # skip any fits that have fewer than 50% good values
    if good.sum() < len(nupperoverg_tofit)/2.:
        return 0*u.cm**-2, 0*u.K, 0, 0

    if errors is not None:
        rel_errors = errors / nupperoverg_tofit
        weights = 1. / rel_errors**2
        log.debug("Fitting with data = {0}, weights = {1}, errors = {2},"
                  "relative_errors = {3}"
                  .format(np.log(nupperoverg_tofit[good]),
                          np.log(weights[good]),
                          errors[good],
                          rel_errors[good],
                         ))
    else:
        # want log(weight) = 1
        weights = np.exp(np.ones_like(nupperoverg_tofit))

    result = fitter(model, eupper[good], np.log(nupperoverg_tofit[good]),
                    weights=np.log(weights[good]))
    tex = -1./result.slope*u.K

    partition_func = specmodel.calculate_partitionfunction(hnco.data['States'],
                                                           temperature=tex.value)
    assert len(partition_func) == 1
    Q_rot = tuple(partition_func.values())[0]

    Ntot = np.exp(result.intercept + np.log(Q_rot)) * u.cm**-2

    if verbose:
        print(("Tex={0}, Ntot={1}, Q_rot={2}, nuplim={3}".format(tex, Ntot, Q_rot, upperlim_mask.sum())))

    if plot:
        import pylab as pl
        L, = pl.plot(eupper, np.log10(nupperoverg_tofit), 'ro',
                     markeredgecolor='none', alpha=0.5)
        L, = pl.plot(eupper, np.log10(nupperoverg), 'bo', alpha=0.2)
        if errors is not None:
            yerr = np.array([np.log10(nupperoverg_tofit)-np.log10(nupperoverg_tofit-errors),
                             np.log10(nupperoverg_tofit+errors)-np.log10(nupperoverg_tofit)])
            # if lower limit is nan, set to zero
            yerr[0,:] = np.nan_to_num(yerr[0,:])
            if np.any(np.isnan(yerr[1,:])):
                print("*** Some upper limits are NAN")
            pl.errorbar(eupper.value,
                        np.log10(nupperoverg_tofit),
                        yerr=yerr,
                        linestyle='none',
                        linewidth=0.5,
                        marker='.', zorder=-5)
        xax = np.array([0, eupper.max().value])
        line = (xax*result.slope.value +
                result.intercept.value)
        pl.plot(xax, np.log10(np.exp(line)), '-', color=L.get_color(),
                alpha=0.3,
                label='$T={0:0.1f}$ $\log(N)={1:0.1f}$'.format(tex, np.log10(Ntot.value)))
        pl.ylabel("log N$_u$ (cm$^{-2}$)")
        pl.xlabel("E$_u$ (K)")

        if (uplims is not None) and ((errors is None) or replace_errors_with_uplims):
            # if errors are specified, their errorbars will be better
            # representations of what's actually being fit
            pl.plot(eupper, np.log10(uplims), marker='_', alpha=0.5,
                    linestyle='none', color='k')

    return Ntot, tex, result.slope, result.intercept
def pyspeckitfit(eupper, kkms, frequencies, degeneracies, einsteinAs,
                 verbose=False, plot=False, guess=(150,1e19)):
    """
    Fit the Boltzmann diagram (but do it right, with no approximations, just
    direct forward modeling)

    This doesn't seem to work, though: it can't reproduce its own output
    """

    bandwidth = (1*u.km/u.s/constants.c)*(frequencies)

    def model(tex, col, einsteinAs=einsteinAs, eupper=eupper):
        tex = u.Quantity(tex, u.K)
        col = u.Quantity(col, u.cm**-2)
        eupper = eupper.to(u.erg, u.temperature_energy())
        einsteinAs = u.Quantity(einsteinAs, u.Hz)

        partition_func = specmodel.calculate_partitionfunction(hnco.data['States'],
                                                               temperature=tex.value)
        assert len(partition_func) == 1
        Q_rot = tuple(partition_func.values())[0]
        return lte_molecule.line_brightness(tex, bandwidth, frequencies,
                                            total_column=col,
                                            partition_function=Q_rot,
                                            degeneracy=degeneracies,
                                            energy_upper=eupper,
                                            einstein_A=einsteinAs)

    def minmdl(args):
        tex, col = args
        return ((model(tex, col).value - kkms)**2).sum()

    from scipy import optimize
    result = optimize.minimize(minmdl, guess, method='Nelder-Mead')
    tex, Ntot = result.x

    if plot:
        import pylab as pl
        pl.subplot(2,1,1)
        pl.plot(eupper, kkms, 'o')
        order = np.argsort(eupper)
        pl.plot(eupper[order], model(tex, Ntot)[order])
        pl.subplot(2,1,2)
        xax = np.array([0, eupper.max().value])
        pl.plot(eupper, np.log(nupper_of_kkms(kkms, frequencies, einsteinAs, degeneracies).value), 'o')
        partition_func = specmodel.calculate_partitionfunction(hnco.data['States'],
                                                               temperature=tex)
        assert len(partition_func) == 1
        Q_rot = tuple(partition_func.values())[0]
        intercept = np.log(Ntot) - np.log(Q_rot)
        pl.plot(xax, np.log(xax*tex + intercept), '-',
                label='$T={0:0.1f} \log(N)={1:0.1f}$'.format(tex, np.log10(Ntot)))

    return Ntot, tex, result

def test_roundtrip(cubefrequencies=[218.44005, 234.68345, 220.07849, 234.69847, 231.28115]*u.GHz,
                   degeneracies=[9, 9, 17, 11, 21],
                   xaxis=[45.45959683,  60.92357159,  96.61387286, 122.72191958, 165.34856457]*u.K,
                   indices=[3503, 1504, 2500, 116, 3322],
                  ):

    # integrated line over 1 km/s (see dnu)
    onekms = 1*u.km/u.s / constants.c
    kkms = lte_molecule.line_brightness(tex=100*u.K,
                                        total_column=1e15*u.cm**-2,
                                        partition_function=1185,
                                        degeneracy=degeneracies,
                                        frequency=cubefrequencies,
                                        energy_upper=xaxis.to(u.erg,
                                                              u.temperature_energy()),
                                        einstein_A=einsteinAij[indices],
                                        dnu=onekms*cubefrequencies) * u.km/u.s
    col, tem, slope, intcpt = fit_tex(xaxis, nupper_of_kkms(kkms,
                                                            cubefrequencies,
                                                            einsteinAij[indices],
                                                            degeneracies).value,
                                      plot=True)
    print("temperature = {0} (input was 100)".format(tem))
    print("column = {0} (input was 1e15)".format(np.log10(col.value)))


def fit_all_tex(xaxis, cube, cubefrequencies, indices, degeneracies,
                ecube=None,
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
                uplims = nupper_of_kkms(replace_bad, cubefrequencies,
                                        einsteinAij[indices], degeneracies,).value
            else:
                uplims = None

            nuppers = nupper_of_kkms(cube[:,ii,jj], cubefrequencies,
                                     einsteinAij[indices], degeneracies,
                                    )
            if ecube is not None:
                nupper_error = nupper_of_kkms(ecube[:,ii,jj], cubefrequencies,
                                              einsteinAij[indices], degeneracies,).value
                uplims = 3 * nupper_error
                if replace_bad:
                    raise ValueError("replace_bad is ignored now...")
            else:
                nupper_error = None

            fit_result = fit_tex(xaxis, nuppers.value,
                                 errors=nupper_error,
                                 uplims=uplims)
            tmap[ii,jj] = fit_result[1].value
            Nmap[ii,jj] = fit_result[0].value
        pb.update(count)
        count+=1

    return tmap,Nmap

if __name__ == "__main__":

    import pylab as pl
    pl.matplotlib.rc_file('pubfiguresrc')

    # sigma ~0.055 - 0.065
    detection_threshold_jykms = 0.065 * 2
    approximate_jytok = 221

    sources = {'e2': coordinates.SkyCoord('19:23:43.963', '+14:30:34.53',
                                          frame='fk5', unit=(u.hour, u.deg)),
               'e8': coordinates.SkyCoord('19:23:43.891', '+14:30:28.13',
                                          frame='fk5', unit=(u.hour, u.deg)),
               'ALMAmm14': coordinates.SkyCoord('19:23:38.571', '+14:30:41.80',
                                                frame='fk5', unit=(u.hour,
                                                                   u.deg)),
               'north': coordinates.SkyCoord('19:23:39.906', '+14:31:05.33',
                                             frame='fk5', unit=(u.hour,
                                                                u.deg)),
              }
    radii = {'e2':2.5*u.arcsec,
             'e8':3.0*u.arcsec,
             'ALMAmm14':2.1*u.arcsec,
             'north':4.0*u.arcsec,
            }
    dthresh = {'e2': detection_threshold_jykms*approximate_jytok,
               'e8': detection_threshold_jykms*approximate_jytok,
               'north': detection_threshold_jykms*approximate_jytok,
               'ALMAmm14': 0.001*approximate_jytok, # not real, just for better fits..
              }

    # use precomputed moments from medsub_moments
    for sourcename, region in (('e2','e2e8'), ('e8','e2e8'), ('north','north'),
                               ('ALMAmm14','ALMAmm14'),):

        # use 3-sigma instead of arbitrary
        # replace_bad = dthresh[sourcename]
        replace_bad = False
                                
        _ = cutout_id_chem_map(source=sources[sourcename],
                               radius=radii[sourcename],
                               sourcename=sourcename,
                               filelist=glob.glob(paths.dpath('12m/moments/*medsub_moment0.fits')),
                               molecular_database=hnco,
                               radiative_transitions=rt,
                               frqs=frqs,
                               chem_name='HNCO',
                              )
        xaxis,cube,ecube,maps,map_error,energies,cubefrequencies,indices,degeneracies,header = _

        pl.figure(2, figsize=(12,12)).clf()
        sample_pos = np.linspace(0,1,7)[1:-1]
        nx = len(sample_pos)
        ny = len(sample_pos)
        for ii,(spy,spx) in enumerate(itertools.product(sample_pos,sample_pos)):
            rdx = int(spx*cube.shape[2])
            rdy = int(spy*cube.shape[1])
            plotnum = (nx*ny-(2*(ii//ny)*ny)+ii-ny)+1
            pl.subplot(nx,ny,plotnum)

            #uplims = nupper_of_kkms(replace_bad, cubefrequencies,
            #                        einsteinAij[indices], degeneracies,)
            nupper_error = nupper_of_kkms(ecube[:,rdy,rdx], cubefrequencies,
                                          einsteinAij[indices], degeneracies,)
            uplims = 3*nupper_error
            Ntot, tex, slope, intcpt = fit_tex(xaxis,
                                               nupper_of_kkms(cube[:,rdy,rdx],
                                                              cubefrequencies,
                                                              einsteinAij[indices],
                                                              degeneracies).value,
                                               errors=nupper_error.value,
                                               uplims=uplims.value,
                                               verbose=True,
                                               plot=True)
            pl.ylim(11, 15)
            pl.xlim(0, 850)
            #pl.annotate("{0:d},{1:d}".format(rdx,rdy), (0.5, 0.85), xycoords='axes fraction',
            #            horizontalalignment='center')
            pl.annotate("T={0:d}".format(int(tex.value)),
                        (0.65, 0.85), xycoords='axes fraction',
                        horizontalalignment='left', fontsize=12)
            pl.annotate("N={0:0.1f}".format(np.log10(Ntot.value)),
                        (0.65, 0.75), xycoords='axes fraction',
                        horizontalalignment='left', fontsize=12)
            pl.annotate("{0:0.2f},{1:0.2f}".format(spx,spy),
                        (0.05, 0.05), xycoords='axes fraction',
                        horizontalalignment='left', fontsize=12)

            # show upper limits
            # (this is automatically done now)
            #pl.plot(xaxis,
            #        np.log10(nupper_of_kkms(replace_bad,
            #                                cubefrequencies,
            #                                einsteinAij[indices],
            #                                degeneracies).value),
            #        linestyle='none', marker='_', color='k',
            #        markeredgewidth=2, alpha=0.5)

            if (plotnum-1) % ny == 0:
                pl.ylabel("log($N_u / g_u$)")
                if (plotnum-1) != (ny*(nx-1)):
                    ticks = pl.gca().get_yaxis().get_ticklocs()
                    pl.gca().get_yaxis().set_ticks(ticks[1:])
            else:
                pl.gca().get_yaxis().set_ticklabels([])
                pl.ylabel("")
            if (plotnum-1) >= (ny*(nx-1)):
                pl.xlabel("$E_u$ [K]")
                tl = pl.gca().get_yaxis().get_ticklabels()
                xax = pl.gca().get_xaxis()
                if (plotnum-1) == (nx*ny-1):
                    xax.set_ticks((0,200,400,600,800))
                else:
                    xax.set_ticks((0,200,400,600))
                xax.set_tick_params(labelsize=14)
            else:
                pl.gca().get_xaxis().set_ticklabels([])
                pl.xlabel("")
            #pl.legend(loc='best', fontsize='small')
        pl.subplots_adjust(hspace=0, wspace=0)
        pl.savefig(paths.fpath("chemistry/hnco_rotation_diagrams_{0}.png".format(sourcename)))

        if True:
            tmap,Nmap = fit_all_tex(xaxis, cube, cubefrequencies, indices, degeneracies,
                                    ecube=ecube,
                                    replace_bad=replace_bad)

            pl.figure(1).clf()
            pl.imshow(tmap, vmin=0, vmax=2000, cmap='hot')
            cb = pl.colorbar()
            cb.set_label("Temperature (K)")
            pl.savefig(paths.fpath("chemistry/hnco_temperature_map_{0}.png".format(sourcename)))
            pl.figure(3).clf()
            pl.imshow(np.log10(Nmap), vmin=16, vmax=19, cmap='viridis')
            cb = pl.colorbar()
            cb.set_label("log N(CH$_3$OH)")
            pl.savefig(paths.fpath("chemistry/hnco_column_map_{0}.png".format(sourcename)))

            hdu = fits.PrimaryHDU(data=tmap, header=header)
            hdu.writeto(paths.dpath('12m/moments/hnco_{0}_cutout_temperaturemap.fits'.format(sourcename)), clobber=True)

            hdu = fits.PrimaryHDU(data=Nmap, header=header)
            hdu.writeto(paths.dpath('12m/moments/hnco_{0}_cutout_columnmap.fits'.format(sourcename)), clobber=True)

            nr, bins, rprof = image_tools.radialprofile.azimuthalAverage(tmap,
                                                                         binsize=1.0,
                                                                         return_nr=True)
            mywcs = wcs.WCS(header)
            pixscale = (mywcs.pixel_scale_matrix.diagonal()**2).sum()**0.5
            pl.figure(4).clf()
            pl.plot(bins*pixscale*3600, rprof)
            pl.ylim(0,2000)
            pl.xlabel("Radius (arcsec)")
            pl.ylabel("Average Temperature (K)")
            pl.savefig(paths.fpath("chemistry/hnco_temperature_radial_profile_{0}.png".format(sourcename)))


    #log.setLevel("DEBUG")


    #for sourcename, region, xslice, yslice, vrange, rdposns in (
    #    ('e2','e2e8',(114,214),(367,467),(51,60),[(10,10),(60,84),]),
    #    #natural ('e2','e2e8',(42,118),(168,249),(51,60),[(10,10),(60,84),]),
    #    ('e8','e2e8',(119,239),(227,347),(52,63),[(10,60),(65,45),]),
    #    ('north','north',(152,350),(31,231),(54,64),[(100,80),(75,80),]),
    #    ('ALMAmm14','ALMAmm14',(80,180),(50,150),(58,67),[(65,40),(45,40),]),
    #):

    #    _ = cutout_id_chem_map(yslice=slice(*yslice), xslice=slice(*xslice),
    #                           vrange=vrange*u.km/u.s, sourcename=sourcename,
    #                           filelist=glob.glob(paths.dpath('merge/cutouts/W51_b6_7M_12M.*{0}*fits'.format(region))),
    #                           linere=re.compile("W51_b6_7M_12M.(.*).image.pbcor"),
    #                           chem_name='HNCO',
    #                          )
    #    xaxis,cube,maps,energies,cubefrequencies,indices,degeneracies,header = _

    #    import pylab as pl
    #    pl.matplotlib.rc_file('pubfiguresrc')

    #    pl.figure(2).clf()
    #    for rdx,rdy in rdposns:
    #        fit_tex(xaxis, nupper_of_kkms(cube[:,rdy,rdx], cubefrequencies,
    #                                      einsteinAij[indices],
    #                                      degeneracies).value, plot=True)
    #    pl.ylabel("log($N_u / g_u$)")
    #    pl.xlabel("$E_u$ [K]")
    #    pl.legend(loc='best')
    #    pl.savefig(paths.fpath("chemistry/hnco_rotation_diagrams_{0}.png".format(sourcename)))

    #    tmap,Nmap = fit_all_tex(xaxis, cube, cubefrequencies, indices, degeneracies)

    #    pl.figure(1).clf()
    #    pl.imshow(tmap, vmin=0, vmax=2000, cmap='hot')
    #    cb = pl.colorbar()
    #    cb.set_label("Temperature (K)")
    #    pl.savefig(paths.fpath("chemistry/hnco_temperature_map_{0}.png".format(sourcename)))
    #    pl.figure(3).clf()
    #    pl.imshow(np.log10(Nmap), vmin=14.5, vmax=19, cmap='viridis')
    #    cb = pl.colorbar()
    #    cb.set_label("log N(HNCO)")
    #    pl.savefig(paths.fpath("chemistry/hnco_column_map_{0}.png".format(sourcename)))

    #    hdu = fits.PrimaryHDU(data=tmap, header=header)
    #    hdu.writeto(paths.dpath('merge/cutouts/HNCO_{0}_cutout_temperaturemap.fits'.format(sourcename)), clobber=True)

    #    hdu = fits.PrimaryHDU(data=Nmap, header=header)
    #    hdu.writeto(paths.dpath('merge/cutouts/HNCO_{0}_cutout_columnmap.fits'.format(sourcename)), clobber=True)
