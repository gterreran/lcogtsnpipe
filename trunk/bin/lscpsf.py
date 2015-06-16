#!/usr/bin/env python
description = ">> New automated psf version"
usage = "%prog image [options] "

# ###############################################################
# EC 2012 Feb 20  
# modified by SV for lsc 
################################################################
import os, sys, shutil, subprocess
import time
from optparse import OptionParser
from pyraf import iraf
import pyfits
import lsc
import re
import string
import traceback
import numpy as np

iraf.noao(_doprint=0)
iraf.obsutil(_doprint=0)


def runsex(img, fwhm, thresh, pix_scale):  ## run_sextractor  fwhm in pixel
    import lsc

    mina = 5.
    seeing = fwhm * pix_scale

    cdef = open(lsc.__path__[0] + '/standard/sex/default2.param')
    riga = cdef.readlines()
    cparam = []
    for r in riga:
        if r[0] != '#' and len(r.strip()) > 0: \
                cparam.append(r.split()[0])

    pid = subprocess.Popen("sex " + img + ".fits -catalog_name tmp.cat" + \
                           " -c  " + lsc.__path__[0] + '/standard/sex/default2.sex' \
                                                       " -PARAMETERS_NAME " + lsc.__path__[
                               0] + "/standard/sex/default2.param" + \
                           " -STARNNW_NAME " + lsc.__path__[0] + "/standard/sex/default2.nnw" + \
                           " -PIXEL_SCALE " + str(pix_scale) + \
                           " -DETECT_MINAREA " + str(mina) + \
                           " -DETECT_THRESH  " + str(thresh) + \
                           " -ANALYSIS_THRESH  " + str(thresh) + \
                           " -PHOT_FLUXFRAC 0.5" + \
                           " -SEEING_FWHM " + str(seeing),
                           stdout=subprocess.PIPE, shell=True)

    output, error = pid.communicate()

    csex = open("tmp.cat")
    tab = {}
    riga = csex.readlines()
    for k in cparam: tab[k] = []
    for r in riga:
        if r[0] != '#':
            for i in range(len(cparam)):
                tab[cparam[i]].append(float(r.split()[i]))
    for k in cparam: tab[k] = np.array(tab[k])

    xdim, ydim = iraf.hselect(img, 'i_naxis1,i_naxis2', 'yes', Stdout=1) \
        [0].split()

    xcoo, ycoo, ra, dec, magbest, classstar, fluxrad, bkg = [], [], [], [], [], [], [], []
    for i in range(len(tab['X_IMAGE'])):
        x, y = tab['X_IMAGE'][i], tab['Y_IMAGE'][i]
        if 5 < x < int(xdim) - 5 and 5 < y < int(ydim) - 5:  # trim border
            xcoo.append(x)
            ycoo.append(y)
            ra.append(tab['X_WORLD'][i])
            dec.append(tab['Y_WORLD'][i])
            magbest.append(tab['MAG_BEST'][i])
            classstar.append(tab['CLASS_STAR'][i])
            fluxrad.append(tab['FLUX_RADIUS'][i])
            bkg.append(tab['BACKGROUND'][i])

    return np.array(xcoo), np.array(ycoo), np.array(ra), np.array(dec), np.array(magbest), \
           np.array(classstar), np.array(fluxrad), np.array(bkg)


def psffit2(img, fwhm, psfstars, hdr, _datamax=45000, psffun='gauss'):
    import lsc

    iraf.digiphot(_doprint=0)
    iraf.daophot(_doprint=0)
    zmag = 0.
    varord = 0  # -1 analitic 0 - numeric
    a1, a2, a3, a4, = int(fwhm + 0.5), int(fwhm * 2 + 0.5), int(fwhm * 3 + 0.5), int(fwhm * 4 + 0.5)
    iraf.fitskypars.annulus = a4
    iraf.fitskypars.salgori = 'mean'  #mode,mean,gaussian
    iraf.photpars.apertures = '%d,%d,%d' % (a2, a3, a4)
    iraf.datapars.datamin = -100
    iraf.datapars.datamax = _datamax
    iraf.datapars.readnoise = lsc.util.readkey3(hdr, 'ron')
    iraf.datapars.epadu = lsc.util.readkey3(hdr, 'gain')
    iraf.datapars.exposure = 'EXPTIME'  #lsc.util.readkey3(hdr,'exptime')
    iraf.datapars.airmass = ''
    iraf.datapars.filter = ''
    iraf.photpars.zmag = zmag
    iraf.centerpars.calgori = 'centroid'
    iraf.centerpars.cbox = a2
    iraf.daopars.recenter = 'yes'
    iraf.delete('_psf2.ma*', verify=False)

    iraf.phot(img, '_psf2.coo', '_psf2.mag', interac=False, verify=False, verbose=False)

    iraf.daopars.psfrad = a4
    iraf.daopars.functio = psffun
    iraf.daopars.fitrad = a1
    iraf.daopars.fitsky = 'yes'
    iraf.daopars.sannulus = a4
    iraf.daopars.recenter = 'yes'
    iraf.daopars.varorder = varord
    iraf.delete("_als,_psf.grp,_psf.nrj", verify=False)
    iraf.group(img, '_psf2.mag', img + '.psf', '_psf.grp', verify=False, verbose=False)
    iraf.nstar(img, '_psf.grp', img + '.psf', '_als', '_psf.nrj', verify=False, verbose=False)
    photmag = iraf.txdump("_psf2.mag", 'xcenter,ycenter,id,mag,merr', expr='yes', Stdout=1)
    fitmag = iraf.txdump("_als", 'xcenter,ycenter,id,mag,merr', expr='yes', Stdout=1)
    return photmag, fitmag


def psffit(img, fwhm, psfstars, hdr, interactive, _datamax=45000, psffun='gauss'):
    import lsc

    iraf.digiphot(_doprint=0)
    iraf.daophot(_doprint=0)
    zmag = 0.
    varord = 0  # -1 analitic 0 - numeric

    a1, a2, a3, a4, = int(fwhm + 0.5), int(fwhm * 2 + 0.5), int(fwhm * 3 + 0.5), int(fwhm * 4 + 0.5)
    iraf.fitskypars.annulus = a4
    iraf.fitskypars.salgori = 'mean'  #mode,mean,gaussian
    iraf.photpars.apertures = '%d,%d,%d' % (a2, a3, a4)
    iraf.datapars.datamin = -100
    iraf.datapars.datamax = _datamax
    iraf.datapars.readnoise = lsc.util.readkey3(hdr, 'ron')
    iraf.datapars.epadu = lsc.util.readkey3(hdr, 'gain')
    iraf.datapars.exposure = 'EXPTIME'
    iraf.datapars.airmass = ''
    iraf.datapars.filter = ''
    iraf.centerpars.calgori = 'centroid'
    iraf.centerpars.cbox = a2
    iraf.daopars.recenter = 'yes'
    iraf.photpars.zmag = zmag

    iraf.delete('_psf.ma*,' + img + '.psf.fit?,_psf.ps*,_psf.gr?,_psf.n*,_psf.sub.fit?', verify=False)
    iraf.phot(img, '_psf.coo', '_psf.mag', interac=False, verify=False, verbose=False)

    iraf.daopars.psfrad = a4
    iraf.daopars.functio = psffun
    iraf.daopars.fitrad = a1
    iraf.daopars.fitsky = 'yes'
    iraf.daopars.sannulus = a4
    iraf.daopars.recenter = 'yes'
    iraf.daopars.varorder = varord

    if interactive:
        shutil.copyfile('_psf.mag', '_psf.pst')
        print '_' * 80
        print '>>> Mark good stars with "a" or "d"-elete. Then "f"-it,' + \
              ' "w"-write and "q"-uit (cursor on ds9)'
        print '-' * 80
    else:
        iraf.pstselect(img, '_psf.mag', '_psf.pst', psfstars, interac=False, verify=False)

    iraf.psf(img, '_psf.mag', '_psf.pst', img + '.psf', '_psf.psto', '_psf.psg', interac=interactive,
             verify=False, verbose=False)
    iraf.group(img, '_psf.mag', img + '.psf', '_psf.grp', verify=False, verbose=False)
    iraf.nstar(img, '_psf.grp', img + '.psf', '_psf.nst', '_psf.nrj', verify=False, verbose=False)

    photmag = iraf.txdump("_psf.mag", 'xcenter,ycenter,id,mag,merr', expr='yes', Stdout=1)
    pst = iraf.txdump("_psf.pst", 'xcenter,ycenter,id', expr='yes', Stdout=1)
    fitmag = iraf.txdump("_psf.nst", 'xcenter,ycenter,id,mag,merr', expr='yes', Stdout=1)
    return photmag, pst, fitmag


def ecpsf(img, ofwhm, threshold, psfstars, distance, interactive, ds9, psffun='gauss'):
    try:
        import lsc, string

        hdr = lsc.util.readhdr(img + '.fits')
        instrument = lsc.util.readkey3(hdr, 'instrume')
        print 'INSTRUMENT:', instrument

        if 'PIXSCALE' in hdr:
            pixelscale = lsc.util.readkey3(hdr, 'PIXSCALE')
        elif 'CCDSCALE' in hdr:
            if 'CCDXBIN' in hdr:
                pixelscale = lsc.util.readkey3(hdr, 'CCDSCALE') * lsc.util.readkey3(hdr, 'CCDXBIN')
            elif 'CCDSUM' in hdr:
                pixelscale = lsc.util.readkey3(hdr, 'CCDSCALE') * int(string.split(lsc.util.readkey3(hdr, 'CCDSUM'))[0])

        if instrument in ['kb05', 'kb70', 'kb71', 'kb73', 'kb74', 'kb75', 'kb76', 'kb77', 'kb78', 'kb79']:
            scale = pixelscale
            _datamax = 45000
        elif instrument in ['fl02', 'fl03', 'fl04', 'fl07', 'fl06']:
            scale = pixelscale
            _datamax = 120000
        elif instrument in ['fs01', 'em03']:
            scale = pixelscale
            _datamax = 65000
        elif instrument in ['fs02', 'fs03']:
            scale = pixelscale
            _datamax = 65000
        elif instrument in ['em01']:
            scale = pixelscale
            _datamax = 65000

        _wcserr = lsc.util.readkey3(hdr, 'wcserr')
        print _wcserr
        if float(_wcserr) == 0:
            if instrument in ['kb05', 'kb70', 'kb71', 'kb73', 'kb74', 'kb75', 'kb76', 'kb77', 'kb78', 'kb79']:
                seeing = float(lsc.util.readkey3(hdr, 'L1FWHM')) * .75
            elif instrument in ['fl02', 'fl03', 'fl04', 'fl07', 'fl06']:
                seeing = float(lsc.util.readkey3(hdr, 'L1FWHM')) * .75
            elif instrument in ['fs01', 'fs02', 'fs03', 'em03', 'em01']:
                if 'L1FWHM' in hdr:
                    seeing = float(lsc.util.readkey3(hdr, 'L1FWHM')) * .75
                elif 'L1SEEING' in hdr:
                    seeing = float(lsc.util.readkey3(hdr, 'L1SEEING')) * scale
                else:
                    seeing = 3
            else:
                seeing = 3
        else:
            seeing = float(lsc.util.readkey3(hdr, 'PSF_FWHM'))
            sys.exit('astrometry not good')
        #except:  sys.exit('astrometry not good')

        fwhm = seeing / scale
        print 'FWHM[header]  ', fwhm, '   in pixel'
        if ofwhm: fwhm = float(ofwhm)
        print '    FWHM[input]  ', fwhm, ' in pixel'

        if interactive:
            iraf.display(img, 1, fill=True)
            iraf.delete('tmp.lo?', verify=False)
            print '_' * 80
            print '>>> Mark reference stars with "a". Then "q"'
            print '-' * 80
            iraf.imexamine(img, 1, wcs='logical', logfile='tmp.log', keeplog=True)
            xyrefer = iraf.fields('tmp.log', '1,2,6,15', Stdout=1)
            xns, yns, _fws = [], [], []
            ff = open('_psf.coo', 'w')
            for i in range(len(xyrefer)):
                xns.append(float(xyrefer[i].split()[0]))
                yns.append(float(xyrefer[i].split()[1]))
                _fws.append(float(xyrefer[i].split()[3]))
                ff.write('%10.3f %10.3f %7.2f \n' % (xns[i], yns[i], float(_fws[i])))
            ff.close()
            fwhm = np.median(_fws)

            ###################
            xdim, ydim = iraf.hselect(img, 'i_naxis1,i_naxis2', 'yes', Stdout=1)[0].split()
            print img, fwhm, threshold, scale
            xs, ys, ran, decn, magbest, classstar, fluxrad, bkg = runsex(img, fwhm, threshold, scale)
            dflux = fluxrad - np.median(fluxrad)
            fstar = np.compress(dflux < np.std(fluxrad), fluxrad)

            tot = np.compress(abs(np.array(fluxrad) * 1.6 - fwhm) / fwhm < .5, fluxrad)
            print len(tot)

            ff = open('tmp.cursor', 'w')
            for i in range(len(xs)):
                _xs = np.delete(xs, i)
                _ys = np.delete(ys, i)
                dist2 = np.sqrt((_xs - xs[i]) ** 2 + (_ys - ys[i]) ** 2)
                # star, not near other object
                if abs(fluxrad[i] * 1.6 - fwhm) / fwhm < .5 and min(dist2) > distance * fwhm:
                    x1, x2 = int(xs[i] - fwhm * 3), int(xs[i] + fwhm * 3)
                    y1, y2 = int(ys[i] - fwhm * 3), int(ys[i] + fwhm * 3)
                    if x1 < 1: x1 = 1
                    if y1 < 1: y1 = 1
                    if x2 > int(xdim): x2 = int(xdim)
                    if y2 > int(ydim): y2 = int(ydim)
                    sect = '[' + str(x1) + ':' + str(x2) + ',' + str(y1) + ':' + str(y2) + ']'
                    fmax = iraf.imstat(img + sect, fields='max', Stdout=1)[1]
                    if float(fmax) < 45000:  # not saturated
                        ff.write('%10.3f %10.3f 1 m \n' % (xs[i], ys[i]))
            ff.close()

            iraf.delete('tmp.lo?,tmp.sta?,tmp.gk?', verify=False)
            iraf.psfmeasure(img, imagecur='tmp.cursor', logfile='tmp.log', radius=int(fwhm), iter=3, display=False,
                            StdoutG='tmp.gki')
            ff = open('tmp.log')
            righe = ff.readlines()
            xn = [float(righe[3].split()[1])]
            yn = [float(righe[3].split()[2])]
            _fw = [float(righe[3].split()[4])]
            for r in righe[4:-2]:
                if len(r) > 0:
                    xn.append(float(r.split()[0]))
                    yn.append(float(r.split()[1]))
                    _fw.append(float(r.split()[3]))

        else:
            xdim, ydim = iraf.hselect(img, 'i_naxis1,i_naxis2', 'yes', Stdout=1)[0].split()
            print img, fwhm, threshold, scale
            xs, ys, ran, decn, magbest, classstar, fluxrad, bkg = runsex(img, fwhm, threshold, scale)
            dflux = fluxrad - np.median(fluxrad)
            fstar = np.compress(dflux < np.std(fluxrad), fluxrad)
            tot = np.compress(np.abs(np.array(fluxrad) * 1.6 - fwhm) / fwhm < .5, fluxrad)
            print len(tot)
            if len(tot) < 5:
                print 'warning: fwhm from sexractor different from fwhm computed during pre-reduction'
                print 'try using option --fwhm xxx'

            ff = open('tmp.cursor', 'w')
            for i in range(len(xs)):
                _xs = np.delete(xs, i)
                _ys = np.delete(ys, i)
                dist2 = np.sqrt((_xs - xs[i]) ** 2 + (_ys - ys[i]) ** 2)
                # star, not near other object
                if np.abs(fluxrad[i] * 1.6 - fwhm) / fwhm < .5 and min(dist2) > distance * fwhm:
                    x1, x2 = int(xs[i] - fwhm * 3), int(xs[i] + fwhm * 3)
                    y1, y2 = int(ys[i] - fwhm * 3), int(ys[i] + fwhm * 3)
                    if x1 < 1: x1 = 1
                    if y1 < 1: y1 = 1
                    if x2 > int(xdim): x2 = int(xdim)
                    if y2 > int(ydim): y2 = int(ydim)
                    sect = '[' + str(x1) + ':' + str(x2) + ',' + str(y1) + ':' + str(y2) + ']'
                    fmax = iraf.imstat(img + sect, fields='max', Stdout=1)[1]
                    if float(fmax) < _datamax:  # not saturated
                        ff.write('%10.3f %10.3f 1 m \n' % (xs[i], ys[i]))
            ff.close()

            iraf.delete('tmp.lo?,tmp.sta?,tmp.gk?', verify=False)
            iraf.psfmeasure(img, imagecur='tmp.cursor', logfile='tmp.log', radius=int(fwhm), iter=3,
                            display=False, StdoutG='tmp.gki')

            ff = open('tmp.log')
            righe = ff.readlines()
            xn = [float(righe[3].split()[1])]
            yn = [float(righe[3].split()[2])]
            _fw = [float(righe[3].split()[4])]
            for r in righe[4:-2]:
                if len(r) > 0:
                    xn.append(float(r.split()[0]))
                    yn.append(float(r.split()[1]))
                    _fw.append(float(r.split()[3]))
            print 'FWHM: ', righe[-1].split()[-1]
            print 80 * "#"
            ######
            xns, yns, _fws = [xn[0]], [yn[0]], [_fw[0]]
            for i in range(1, len(xn)):  # eliminate double object identification
                if abs(xn[i] - xn[i - 1]) > .2 and abs(yn[i] - yn[i - 1]) > .2:
                    xns.append(xn[i])
                    yns.append(yn[i])
                    _fws.append(_fw[i])

            fw = []
            ff = open('_psf.coo', 'w')
            for i in range(len(xns)):
                if abs(_fws[i] - fwhm) / fwhm < .3:
                    ff.write('%10.3f %10.3f %7.2f \n' % (xns[i], yns[i], float(_fws[i])))
                    fw.append(_fws[i])
            ff.close()  ## End automatic selection
            ###
            ff = open('_psf2.coo', 'w')
            for i in range(len(xn)):
                ff.write('%10.3f %10.3f %7.2f \n' % (xn[i], yn[i], float(_fw[i])))
            ff.close()  ## End automatic selection
            fwhm = np.median(fw)

            print "Median FWHM %5.2f +/-%5.2f  nsource=%d  " \
                  % (np.median(fw), np.std(fw), len(fw))

        print 80 * "#"
        photmag, pst, fitmag = psffit(img, fwhm, psfstars, hdr, interactive, _datamax, psffun)

        photmag2, fitmag2 = psffit2(img, fwhm, psfstars, hdr, _datamax, psffun)

        radec = iraf.wcsctran(input='STDIN', output='STDOUT', Stdin=photmag,
                              Stdout=1, image=img, inwcs='logical', outwcs='world', columns="1 2",
                              format='%13.3H %12.2h', min_sig=9, mode='h')[3:]

        radec2 = iraf.wcsctran(input='STDIN', output='STDOUT', Stdin=photmag2,
                               Stdout=1, image=img, inwcs='logical', outwcs='world', columns="1 2",
                               format='%13.3H %12.2h', min_sig=9, mode='h')[3:]

        if ds9 == 0 and interactive:
            iraf.set(stdimage='imt1024')
            iraf.display(img, 1, fill=True, Stdout=1)
            iraf.tvmark(1, coords='STDIN', mark='circle', radii=15, label=False, Stdin=photmag)
            iraf.tvmark(1, coords='STDIN', mark='rectangle', length=35, label=False, Stdin=pst)
            iraf.tvmark(1, coords='STDIN', mark='cross', length=35, label=False, Stdin=fitmag2, color=204)

        idpsf = []
        for i in range(len(pst)):
            idpsf.append(pst[i].split()[2])
        dmag = []
        for i in range(len(radec)):
            ra, dec, idph, magp2, magp3, magp4, merrp2, merrp3, merrp4 = radec[i].split()
            dmag.append(9.99)
            for j in range(len(fitmag)):
                raf, decf, idf, magf, magerrf = fitmag[j].split()
                if idph == idf and idph in idpsf and \
                                magp3 != 'INDEF' and magf != 'INDEF':
                    dmag[i] = float(magp3) - float(magf)
                    break

        _dmag = np.compress(np.array(dmag) < 9.99, np.array(dmag))

        print '>>> Aperture correction (phot)   %6.3f +/- %5.3f %3d ' % \
              (np.mean(_dmag), np.std(_dmag), len(_dmag))
        if len(_dmag) > 3:
            _dmag = np.compress(np.abs(_dmag - np.median(_dmag)) < 2 * np.std(_dmag), _dmag)
            print '>>>         2 sigma rejection)   %6.3f +/- %5.3f %3d  [default]' \
                  % (np.mean(_dmag), np.std(_dmag), len(_dmag))
            print '>>>     fwhm   %s  ' % (str(fwhm))
        for i in range(len(dmag)):
            if dmag[i] == 9.99:
                dmag[i] = ''
            else:
                dmag[i] = '%6.3f' % (dmag[i])

        exptime = lsc.util.readkey3(hdr, 'exptime')
        object = lsc.util.readkey3(hdr, 'object').replace(' ', '')
        filtro = lsc.util.readkey3(hdr, 'filter')

        #######################################
        rap, decp, magp2, magp3, magp4, smagf, merrp3, smagerrf = [], [], [], [], [], [], [], []
        rap0, decp0 = [], []
        for i in range(len(radec2)):
            aa = radec2[i].split()
            rap.append(aa[0])
            decp.append(aa[1])
            rap0.append(lsc.lscabsphotdef.deg2HMS(ra=aa[0]))
            decp0.append(lsc.lscabsphotdef.deg2HMS(dec=aa[1]))
            idp = aa[2]
            magp2.append(aa[3])
            magp3.append(aa[4])
            magp4.append(aa[5])
            merrp3.append(aa[7])
            _smagf, _smagerrf = 9999, 9999
            for j in range(len(fitmag2)):
                raf, decf, idf, magf, magerrf = fitmag2[j].split()
                if idf == idp:
                    _smagf = magf
                    _smagerrf = magerrf
                    break
            smagf.append(_smagf)
            smagerrf.append(_smagerrf)
        tbhdu = pyfits.new_table(pyfits.ColDefs([pyfits.Column(name='ra', format='20A', array=np.array(rap)),
                                                 pyfits.Column(name='dec', format='20A', array=np.array(decp)),
                                                 pyfits.Column(name='ra0', format='E', array=np.array(rap0)),
                                                 pyfits.Column(name='dec0', format='E', array=np.array(decp0)),
                                                 pyfits.Column(name='magp2', format='E',
                                                               array=np.array(np.where((np.array(magp2) != 'INDEF'),
                                                                                       np.array(magp2), 9999), float)),
                                                 pyfits.Column(name='magp3', format='E',
                                                               array=np.array(np.where((np.array(magp3) != 'INDEF'),
                                                                                       np.array(magp3), 9999), float)),
                                                 pyfits.Column(name='merrp3', format='E',
                                                               array=np.array(np.where((np.array(merrp3) != 'INDEF'),
                                                                                       np.array(merrp3), 9999), float)),
                                                 pyfits.Column(name='magp4', format='E',
                                                               array=np.array(np.where((np.array(magp4) != 'INDEF'),
                                                                                       np.array(magp4), 9999), float)),
                                                 pyfits.Column(name='smagf', format='E',
                                                               array=np.array(np.where((np.array(smagf) != 'INDEF'),
                                                                                       np.array(smagf), 9999), float)),
                                                 pyfits.Column(name='smagerrf', format='E',
                                                               array=np.array(np.where((np.array(smagerrf) != 'INDEF'),
                                                                                       np.array(smagerrf), 9999),
                                                                              float)),
        ]))
        hdu = pyfits.PrimaryHDU(header=hdr)
        thdulist = pyfits.HDUList([hdu, tbhdu])
        lsc.util.delete(img + '.sn2.fits')
        thdulist.writeto(img + '.sn2.fits')
        lsc.util.updateheader(img + '.sn2.fits', 0, {'APCO': [np.mean(_dmag), 'Aperture correction']})
        lsc.util.updateheader(img + '.sn2.fits', 0, {'APCOERR': [np.std(_dmag), 'Aperture correction error']})
        lsc.util.updateheader(img + '.sn2.fits', 0, {'XDIM': [lsc.util.readkey3(hdr, 'naxis1'), 'x number of pixels']})
        lsc.util.updateheader(img + '.sn2.fits', 0, {'YDIM': [lsc.util.readkey3(hdr, 'naxis2'), 'y number of pixels']})
        lsc.util.updateheader(img + '.sn2.fits', 0,
                              {'PSF_FWHM': [fwhm * scale, 'FWHM (arcsec) - computed with daophot']})
        os.chmod(img + '.sn2.fits', 0664)
        os.chmod(img + '.psf.fits', 0664)
        result = 1

    except:
        result = 0
        fwhm = 0.0
        traceback.print_exc()
    return result, fwhm * scale

###########################################################################
if __name__ == "__main__":
    start_time = time.time()
    parser = OptionParser(usage=usage, description=description)
    parser.add_option("-f", "--fwhm", dest="fwhm", default='', help='starting FWHM  \t\t\t %default')
    parser.add_option("-t", "--threshold", dest="threshold", default=10., type='float',
                      help='Source detection threshold \t\t\t %default')
    parser.add_option("-p", "--psfstars", dest="psfstars", default=6, type='int',
                      help='Maximum number of psf stars \t\t\t %default')
    parser.add_option("-d", "--distance", dest="distance", default=5,
                      type='int', help='Minimum star separation (in unit of FWHM) \t\t %default')
    parser.add_option("--function", dest="psffun", default='gauss', type='str',
                      help='psf function (gauss,auto,moffat15,moffat25,penny1,penny2,lorentz) \t\t %default')
    parser.add_option("-r", "--redo", action="store_true", dest='redo', default=False,
                      help='Re-do \t\t\t\t [%default]')
    parser.add_option("-i", "--interactive", action="store_true", dest='interactive', default=False,
                      help='Interactive \t\t\t [%default]')
    parser.add_option("-s", "--show", dest="show", action='store_true',
                      default=False, help='Show PSF output \t\t [%default]')
    parser.add_option("-X", "--xwindow", action="store_true", dest='xwindow', default=False,
                      help='xwindow \t\t\t [%default]')

    option, args = parser.parse_args()
    if len(args) < 1: sys.argv.append('--help')
    option, args = parser.parse_args()
    imglist = lsc.util.readlist(args[0])
    _xwindow = option.xwindow
    psffun = option.psffun
    if psffun not in ['gauss', 'auto', 'lorentz', 'moffat15', 'moffat25', 'penny1', 'penny2']:
        sys.argv.append('--help')
    option, args = parser.parse_args()

    if _xwindow:
        from stsci.tools import capable

        capable.OF_GRAPHICS = False

    for img in imglist:
        if '.fits' in img: img = img[:-5]
        if os.path.exists(img + '.sn2.fits') and not option.redo:
            print img + ': psf already calculated'
        else:
            ds9 = os.system("ps -U" + str(os.getuid()) + "|grep -v grep | grep ds9")
            if option.interactive and ds9 != 0:
                pid = subprocess.Popen(['ds9']).pid
                time.sleep(2)
                ds9 = 0

            result, fwhm = ecpsf(img, option.fwhm, option.threshold, option.psfstars,
                                 option.distance, option.interactive, ds9, psffun)
            print '\n### ' + str(result)
            if option.show:
                lsc.util.marksn2(img + '.fits', img + '.sn2.fits', 1, '')
                iraf.delete('tmp.psf.fit?', verify=False)
                iraf.seepsf(img + '.psf', '_psf.psf')
                iraf.surface('_psf.psf')
                aa = raw_input('>>>good psf [[y]/n] ? ')
                if not aa: 
                    aa = 'y'
                if aa in ['n', 'N', 'No', 'NO']: 
                    result = 0

            iraf.delete("tmp.*", verify="no")
            iraf.delete("_psf.*", verify="no")
            print  "********** Completed in ", int(time.time() - start_time), "sec"
            print result
            try:
                if result == 1:
                    lsc.mysqldef.updatevalue('photlco', 'psf', string.split(img, '/')[-1] + '.psf.fits',
                                             string.split(img, '/')[-1] + '.fits')
                    lsc.mysqldef.updatevalue('photlco', 'fwhm', fwhm, string.split(img, '/')[-1] + '.fits')
                    lsc.mysqldef.updatevalue('photlco', 'mag', 9999, string.split(img, '/')[-1] + '.fits')
                    lsc.mysqldef.updatevalue('photlco', 'psfmag', 9999, string.split(img, '/')[-1] + '.fits')
                    lsc.mysqldef.updatevalue('photlco', 'apmag', 9999, string.split(img, '/')[-1] + '.fits')
                    if os.path.isfile(img + '.diff.fits') and os.path.isfile(img + '.sn2.fits'):
                        # update diff info is file available
                        os.system('cp ' + img + '.sn2.fits ' + img + '.diff.sn2.fits')
                        lsc.mysqldef.updatevalue('photlco', 'psf', string.split(img, '/')[-1] + '.psf.fits',
                                                 string.split(img, '/')[-1] + '.diff.fits')
                        lsc.mysqldef.updatevalue('photlco', 'fwhm', fwhm, string.split(img, '/')[-1] + '.diff.fits')
                        lsc.mysqldef.updatevalue('photlco', 'mag', 9999, string.split(img, '/')[-1] + '.diff.fits')
                        lsc.mysqldef.updatevalue('photlco', 'psfmag', 9999, string.split(img, '/')[-1] + '.diff.fits')
                        lsc.mysqldef.updatevalue('photlco', 'apmag', 9999, string.split(img, '/')[-1] + '.diff.fits')
                else:
                    print 'psf not good, database not updated '
                    lsc.mysqldef.updatevalue('photlco', 'psf', 'X', string.split(img, '/')[-1] + '.fits')
                    if os.path.isfile(img + '.diff.fits'):
                        lsc.mysqldef.updatevalue('photlco', 'psf', 'X', string.split(img, '/')[-1] + '.diff.fits')
            except:
                print 'module mysqldef not found'
