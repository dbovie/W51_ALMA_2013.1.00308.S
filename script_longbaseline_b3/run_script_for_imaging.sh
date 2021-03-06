#!/bin/sh

# Script for running continuum imaging on NRAO machines

#This script is meant to be set in the COMMAND variable
#in the configure file to submit.  That submit script will create the
#clusterspec file for us in the WORK_DIR we specified in the configure file.
#PBS -l mem=30gb
#PBS -l nodes=1:ppn=8
#PBS -d /lustre/aoc/students/bmcclell/w51/2017.1.00293.S/uvdata
#PBS -N w51n_b3_cont
#PBS -m abe
# # Send mail on begin, end, abort, and fail

WORK_DIR='/lustre/aoc/students/bmcclell/w51/2017.1.00293.S/uvdata'
cd ${WORK_DIR}

# casa's python requires a DISPLAY for matplot so create a virtual X server
#xvfb-run -d casa-prerelease --nogui --nologger -c "field_list=['W51 North']; re_clear=False; execfile('$WORK_DIR/imaging_continuum_selfcal_incremental.py')"
#xvfb-run -d casa-prerelease --nogui --nologger -c "field_list=['W51e2w']; re_clear=False; execfile('$WORK_DIR/imaging_continuum_selfcal_incremental.py')"
xvfb-run -d casa-prerelease --nogui --nologger -c "execfile('$WORK_DIR/scriptForImaging_north.py')"
xvfb-run -d casa-prerelease --nogui --nologger -c "execfile('$WORK_DIR/scriptForImaging.py')"
