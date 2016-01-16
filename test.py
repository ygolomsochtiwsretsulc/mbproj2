from __future__ import division, print_function

import os
import numpy as N
import scipy.optimize

import mbproj2 as mb

indir='../jsproj/examples/pks0745'

cosmology = mb.Cosmology(0.1028)
annuli = mb.loadAnnuli(
    os.path.join(indir, 'sb_profile_1200_2500.dat.rebin'), cosmology)

nfw = mb.CmptMassNFW(annuli)

ne_cmpt = mb.CmptBinned('ne', annuli, log=True, defval=-2)
Z_cmpt = mb.CmptFlat('Z', annuli, defval=0.3, log=True)

model = mb.ModelHydro(annuli, nfw, ne_cmpt, Z_cmpt, NH_1022pcm2=0.378)
pars = model.defPars()

band1 = mb.loadBand(
    os.path.join(indir, 'sb_profile_500_1200.dat.rebin'),
    0.5, 1.2,
    os.path.join(indir, 'ann_0_total_rmf.fits'),
    os.path.join(indir, 'ann_0_total_arf.fits'))
band1.backrates = N.loadtxt(
    os.path.join(indir, 'sb_bgcomb_500_1200.dat.rebin.norm'))[:,2]

band2 = mb.loadBand(
    os.path.join(indir, 'sb_profile_1200_2500.dat.rebin'),
    1.2, 2.5,
    os.path.join(indir, 'ann_0_total_rmf.fits'),
    os.path.join(indir, 'ann_0_total_arf.fits'))
band2.backrates = N.loadtxt(
    os.path.join(indir, 'sb_bgcomb_1200_2500.dat.rebin.norm'))[:,2]

band3 = mb.loadBand(
    os.path.join(indir, 'sb_profile_2500_6000.dat.rebin'),
    2.5, 6.0,
    os.path.join(indir, 'ann_0_total_rmf.fits'),
    os.path.join(indir, 'ann_0_total_arf.fits'))
band3.backrates = N.loadtxt(
    os.path.join(indir, 'sb_bgcomb_2500_6000.dat.rebin.norm'))[:,2]

data = mb.Data([band1, band2, band3], annuli)

fit = mb.Fit(pars, model, data)

def fitfunc(vals):
    fit.updateThawed(vals)
    penalty = fit.penaltyTrimBounds()
    profs = fit.calcProfiles()
    like = fit.calcLikelihood(profs) - penalty*100
    print(penalty, like)
    return -like

thawedpars = fit.thawedVals()
fitpars = scipy.optimize.minimize(fitfunc, thawedpars)

print('B1',band1.cts)
print('B2',band2.cts)
print('B3',band3.cts)

fit.updateThawed(fitpars.x)
for p in fit.calcProfiles():
    print(p)
