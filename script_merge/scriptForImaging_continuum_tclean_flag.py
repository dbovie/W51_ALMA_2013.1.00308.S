phasecenter = "J2000 19:23:41.585 +14:30:41.00"
phasecenter = ""
# position angle: 44.5 deg
def my_clean(vis, imagename, **kwargs):
    tclean(vis = vis,
           imagename = imagename,
           phasecenter=phasecenter,
           mask='auto-pb', # masks at minpb=0.2.  0.4 or 0.5 are desired, but very difficult to configure
           **kwargs)
 #         field = '',
 #         spw = '', # there should be only one
 #         specmode = 'cube',
 #         width = width,
 #         start = startfreq,
 #         nchan = nchans_per_cube,
 #         veltype = 'radio',
 #         outframe = 'LSRK',
 #          gridder='mosaic',
 #          deconvolver='clark',
 #         interactive = F,
 #         niter = 25000,
 #         imsize = imsize,
 #         cell = cell,
 #         weighting = weighting,
 #         phasecenter = phasecenter,
 #         robust = robust,
 #         threshold = threshold,
 #         savemodel='none',
 #         overwrite=True)

def my_exportfits(contimagename):
    myimagebase = contimagename
    impbcor(imagename=myimagebase+'.image', pbimage=myimagebase+'.pb',
            outfile=myimagebase+'.image.pbcor', overwrite=True)
    exportfits(imagename=myimagebase+'.image.pbcor',
               fitsimage=myimagebase+'.image.pbcor.fits', overwrite=True,
               dropdeg=True)
    exportfits(imagename=myimagebase+'.pb',
               fitsimage=myimagebase+'.pb.fits', overwrite=True,
               dropdeg=True)
    exportfits(imagename=myimagebase+'.residual',
               fitsimage=myimagebase+'.residual.fits', overwrite=True,
               dropdeg=True)


"""
Attempt to image the continuum with flagging
"""

mergevis = 'continuum_7m12m.ms'
if not os.path.exists(mergevis):
    raise ValueError("Make sure to run scriptForImaging_continuum_flag.py first")

extensions = ['.flux', '.image', '.mask', '.model', '.pbcor', '.psf',
              '.residual', '.flux.pbcoverage', '.sumwt', '.weight', '.pb',
              '.pbcoverage']

contimagename = 'w51_spw3_continuum_7m12m_flagged_natural_tclean'

for ext in extensions:
    rmtables(contimagename+ext)

my_clean(vis=mergevis,
      imagename=contimagename,
      field='w51',
      specmode='mfs',
      deconvolver='clark',
      imsize = [1280,1280],
      cell= '0.15arcsec',
      weighting = 'natural',
      robust = 2.0,
      niter = 10000,
      threshold = '1.0mJy',
      interactive = False,
      gridder = 'mosaic',
      savemodel='none',
      )
my_exportfits(contimagename)


contimagename = 'w51_spw3_continuum_7m12m_flagged_natural_taper_tclean'

for ext in extensions:
    rmtables(contimagename+ext)

my_clean(vis=mergevis,
      imagename=contimagename,
      field='w51',
      specmode='mfs',
      deconvolver='clark',
      imsize = [1280,1280],
      cell= '0.15arcsec',
      weighting = 'natural',
      robust = 2.0,
      niter = 10000,
      threshold = '1.0mJy',
      interactive = False,
      gridder = 'mosaic',
      savemodel='none',
      uvtaper=['1.0arcsec'],
      )
my_exportfits(contimagename)



contimagename = 'w51_spw3_continuum_7m12m_flagged_r0_tclean'

for ext in extensions:
    rmtables(contimagename+ext)

my_clean(vis=mergevis,
      imagename=contimagename,
      field='w51',
      specmode='mfs',
      deconvolver='clark',
      imsize = [3072,3072],
      cell= '0.052arcsec',
      weighting = 'briggs',
      robust = 0.0,
      niter = 10000,
      threshold = '1.0mJy',
      interactive = False,
      gridder = 'mosaic',
      savemodel='none',
      )
my_exportfits(contimagename)

contimagename = 'w51_spw3_continuum_7m12m_flagged_r0_dirty_tclean'

for ext in extensions:
    rmtables(contimagename+ext)

my_clean(vis=mergevis,
      imagename=contimagename,
      field='w51',
      specmode='mfs',
      deconvolver='clark',
      imsize = [3072,3072],
      cell= '0.052arcsec',
      weighting = 'briggs',
      robust = 0.0,
      niter = 0,
      threshold = '1.0mJy',
      interactive = False,
      gridder = 'mosaic',
      savemodel='none',
      )
my_exportfits(contimagename)

contimagename = 'w51_spw3_continuum_7m12m_flagged_r0_multiscale_tclean'

for ext in extensions:
    rmtables(contimagename+ext)

my_clean(vis=mergevis,
      imagename=contimagename,
      field='w51',
      scales=[0,5,15,45],
      specmode='mfs',
      deconvolver='multiscale',
      imsize = [3072,3072],
      cell= '0.052arcsec',
      weighting = 'briggs',
      robust = 0.0,
      niter = 10000,
      threshold = '10.0mJy',
      interactive = False,
      gridder = 'mosaic',
      savemodel='none',
      )
my_exportfits(contimagename)

#contimagename = 'w51_spw3_continuum_7m12m_flagged_r0_MEM_tclean'
#
#for ext in extensions:
#    rmtables(contimagename+ext)
#
#my_clean(vis=mergevis,
#      imagename=contimagename,
#      field='w51',
#      scales=[0,3,6,9,12,15,18],
#      specmode='mfs',
#      deconvolver='mem',
#      imsize = [3072,3072],
#      cell= '0.052arcsec',
#      weighting = 'briggs',
#      robust = 0.0,
#      niter = 10000,
#      threshold = '10.0mJy',
#      interactive = False,
#      gridder = 'mosaic',
#      savemodel='none',
#      )
#my_exportfits(contimagename)


contimagename = 'w51_spw3_continuum_7m12m_flagged_uniform_tclean'

for ext in extensions:
    rmtables(contimagename+ext)

my_clean(vis=mergevis,
      imagename=contimagename,
      field='w51',
      specmode='mfs',
      deconvolver='clark',
      imsize = [3072,3072],
      cell= '0.052arcsec',
      weighting = 'briggs',
      robust = -2.0,
      niter = 50000,
      threshold = '20.0mJy',
      interactive = False,
      gridder = 'mosaic',
      savemodel='none',
      )
my_exportfits(contimagename)

