from astropy.table import Table, Column
from astropy import coordinates
from astropy import units as u
from latex_info import latexdict, format_float, round_to_n, strip_trailing_zeros
import natsort

tbl = Table.read('core_continuum_and_line.ipac', format='ascii.ipac')
inds = natsort.index_natsorted(tbl['SourceID'])
tbl = tbl[inds]

coords = coordinates.SkyCoord(tbl['RA'], tbl['Dec'], frame='fk5')
tbl.add_column(Column(name='RA_s', data=coords.ra.to(u.hourangle).to_string(sep=':')))
tbl.add_column(Column(name='Dec_s', data=coords.dec.to(u.deg).to_string(sep=':')))



tbl_towrite = tbl['SourceID', 'RA_s', 'Dec_s', 'cont_flux0p2arcsec',
                  'cont_flux0p4arcsec',
                  #'BrightestFittedPeakPixBrightness',
                  'BrightestFittedPeakPixBrightnessWithcont',
                  'T_corrected_0p2aperturemass',
                  'T_corrected_peakmass',
                  'Categories',
                  #'Classification',
                 ]
tbl_towrite.rename_column('RA_s','RA')
tbl_towrite.rename_column('Dec_s','Dec')
tbl_towrite['cont_flux0p2arcsec'] *= 1000
tbl_towrite['cont_flux0p4arcsec'] *= 1000
tbl_towrite['cont_flux0p2arcsec'].unit = u.mJy
tbl_towrite['cont_flux0p4arcsec'].unit = u.mJy


for row in tbl_towrite:
    if '_' in row['SourceID']:
        row['SourceID'] = row['SourceID'].replace("_"," ")

new_names = {'SourceID': 'Source ID',
             'cont_flux0p2arcsec': '$S_{\\nu}(0.2\\arcsec)$',
             'cont_flux0p4arcsec': '$S_{\\nu}(0.4\\arcsec)$',
             #'BrightestFittedPeakPixBrightness': '$T_{B,max}(\mathrm{line})$',
             'BrightestFittedPeakPixBrightnessWithcont': '$T_{B,max}$',#(\mathrm{line+cont})$',
             'T_corrected_0p2aperturemass': 'M$(T_B, 0.2\\arcsec)$',
             'T_corrected_peakmass': 'M$(T_B, \mathrm{peak})$',
            }

for old, new in new_names.items():             
    tbl_towrite.rename_column(old, new)

latexdict['tabletype'] = 'table*'
latexdict['header_start'] = '\label{tab:photometry}'
latexdict['caption'] = 'Continuum Source IDs and photometry'
latexdict['tablefoot'] = ("\par\n"
                          "The Categories column consists of three letter codes "
                          "as described in Section \\ref{sec:contsourcenature}.  "
                          "In column 1, "
                          "\\texttt{F} indicates a free-free dominated source, "
                          "\\texttt{f} indicates significant free-free contribution, "
                          "and \\texttt{-} means there is no detected cm continuum.  "
                          "In column 2, the peak brightness temperature is used to "
                          "classify the temperature category.  "
                          "\\texttt{H} is `hot' ($T>50$ K), "
                          "\\texttt{C} is `cold' ($T<20$ K), "
                          "and \\texttt{-} is indeterminate (either $20<T<50$K "
                          "or no measurement).  "
                          "In column 3, \\texttt{c} indicates compact sources, "
                          "and \\texttt{-} indicates a diffuse source."
                         )
#latexdict['tablefoot'] = ('\par\nJy-Kelvin gives the conversion factor from Jy '
#                          'to Kelvin given the synthesized beam size and '
#                          'observation frequency.')
latexdict['col_align'] = 'l'*len(tbl.columns)
#latexdict['tabletype'] = 'longtable'
#latexdict['tabulartype'] = 'longtable'
latexdict['units'] = {}

formats={'RA': lambda x: x,#'{0:0.4f}'.format(x),
         'Dec': lambda x: x,#'{0:0.4f}'.format(x),
         'RA_s': lambda x: x,#'{0:0.4f}'.format(x),
         'Dec_s': lambda x: x,#'{0:0.4f}'.format(x),
         '$S_{\\nu}(0.2\\arcsec)$': lambda x: strip_trailing_zeros('{0:0.2f}'.format(round_to_n(x,2))),
         '$S_{\\nu}(0.4\\arcsec)$': lambda x: strip_trailing_zeros('{0:0.2f}'.format(round_to_n(x,2))),
         '$T_{B,max}(\mathrm{line})$': lambda x: strip_trailing_zeros('{0:0.2f}'.format(round_to_n(x,2))),
         '$T_{B,max}(\mathrm{line+cont})$': lambda x: strip_trailing_zeros('{0:0.2f}'.format(round_to_n(x,2))),
         '$T_{B,max}$': lambda x: strip_trailing_zeros('{0:0.2f}'.format(round_to_n(x,2))),
         'M$(T_B, 0.2\\arcsec)$': lambda x: strip_trailing_zeros('{0:0.2f}'.format(round_to_n(x,2))),
         'M$(T_B, \mathrm{peak})$': lambda x: strip_trailing_zeros('{0:0.2f}'.format(round_to_n(x,2))),
        }

tbl_towrite.write('../paper1/photometry_table.tex',
                  latexdict=latexdict, format='ascii.latex', overwrite=True,
                  formats=formats)

latexdict['caption'] = 'Continuum Source IDs and photometry Part 2'
latexdict['header_start'] = '\label{tab:photometry2}'
tbl_towrite[35:].write('../paper1/photometry_table_2.tex',
                       latexdict=latexdict, format='ascii.latex', overwrite=True,
                       formats=formats)

latexdict['caption'] = 'Continuum Source IDs and photometry Part 1'
latexdict['header_start'] = '\label{tab:photometry1}'
latexdict['tablefoot'] = ''
tbl_towrite[:35].write('../paper1/photometry_table_1.tex',
                       latexdict=latexdict, format='ascii.latex', overwrite=True,
                       formats=formats)

