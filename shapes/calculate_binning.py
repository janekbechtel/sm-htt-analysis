#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ROOT
ROOT.PyConfig.IgnoreCommandLineOptions = True  # disable ROOT internal argument parser

import argparse
import numpy as np
import os

import logging
logger = logging.getLogger("calculate_binning.py")


def setup_logging(output_file, level=logging.DEBUG):
    logger.setLevel(level)
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    file_handler = logging.FileHandler(output_file, "w")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Calculate binning of final discriminator.")
    parser.add_argument(
        "--era",
        required=True,
        type=str,
        help="Analysis era")
    parser.add_argument(
        "--input",
        required=True,
        type=str,
        help="Input ROOT file with prefit shapes")
    return parser.parse_args()


def get(f, name):
    x = f.Get(name)
    if x == None:
        logger.critical("Key %s does not exist in %s.", name, f.GetName())
        raise Exception
    return x


def ams(s, b, u):
    ams = 0.0
    try:
        ams = np.sqrt(2*(
            (s+b) * np.log( ((s+b)*(b+(u**2))) / ((b**2)+(s+b)*(u**2)) ) - (b**2) / (u**2) * np.log( 1.0 + ((u**2)*s) / (b*(b+(u**2))) )
            ))
    except:
        ams = 0.0
    if np.isnan(ams):
        ams = 0.0
    return ams


def calculate_binning(sig, bkg, min_entries, bins_per_category):
    # Number of bins (without overflow and underflow bins)
    num_bins = sig.GetNbinsX()
    if not num_bins == bkg.GetNbinsX():
        logger.critical("Signal and background histograms have different number of bins.")
        raise Exception
    # Check that number of bins is multiple of bins per category
    if not num_bins % bins_per_category == 0:
        logger.critical("Number of bins in histogram %u is not multiple of bins per category %u.",
                num_bins, bins_per_category)
        raise Exception
    # Go from right to left and merge bins if ams increases
    this_ams = -1
    next_ams = -1
    s = 0.0
    b = 0.0
    u = 0.0
    bin_borders = [sig.GetBinLowEdge(num_bins+1)]
    for i in reversed(range(2, num_bins+1)):
        # AMS if we split on the low edge of this bin
        s = s+sig.GetBinContent(i)
        b = b+bkg.GetBinContent(i)
        u = np.sqrt(u**2+bkg.GetBinError(i)**2)
        this_ams = ams(s, b, u)

        # AMS if we split on the low edge of the next bin
        next_s = s+sig.GetBinContent(i-1)
        next_b = b+bkg.GetBinContent(i-1)
        next_u = np.sqrt(b**2 + bkg.GetBinError(i-1)**2)
        next_ams = ams(next_s, next_b, next_u)

        # Decide to split or not
        logger.debug("This AMS %f vs next AMS %f at bin %u.", this_ams, next_ams, i)
        if (i-1) % bins_per_category == 0: # Split at unrolling border
            bin_borders.insert(0, sig.GetBinLowEdge(i))
            s = 0.0
            b = 0.0
            u = 0.0
        if s+b < min_entries: # Require minimum amount of entries
            continue
        if next_ams < this_ams: # Make only new border if AMS would not increase
            bin_borders.insert(0, sig.GetBinLowEdge(i))
            s = 0.0
            b = 0.0
            u = 0.0
    bin_borders.insert(0, sig.GetBinLowEdge(1))
    return np.array(bin_borders)


def main(args):
    # Find categories and channels in ROOT file (for the given era)
    if not os.path.exists(args.input):
        logger.critical("Input file %s does not exist.", args.input)
        raise Exception
    f = ROOT.TFile(args.input)
    config = {}
    for key in f.GetListOfKeys():
        name = key.GetName()
        if not args.era in name:
            continue
        channel, category = name.split("_")[1:3]
        if not channel in config:
            config[channel] = {}
        if not category in config[channel]:
            config[channel][category] = None

    for channel in config:
        logger.info("Found channel %s with categories %s.", channel, config[channel].keys())

    # Get bins used per category per channel
    bins_per_category = {}
    for channel in config:
        min_bins = 1e6
        for category in config[channel]:
            name = "htt_{}_{}_Run{}_prefit".format(channel, category, args.era)
            directory = get(f, name)
            h = get(directory, "TotalBkg")
            num_bins = h.GetNbinsX()
            if min_bins > num_bins:
                min_bins = int(num_bins)
        bins_per_category[channel] = min_bins

    for channel in config:
        logger.info("Found for channel %s %u bins per category.", channel, bins_per_category[channel])

    # Go through channel and categories and find best binning
    for channel in config:
        for category in config[channel]:
            if not int(category) < 10:
                continue
            name = "htt_{}_{}_Run{}_prefit".format(channel, category, args.era)
            directory = get(f, name)
            sig = get(directory, "TotalSig")
            bkg  = get(directory, "TotalBkg")
            binning = calculate_binning(sig=sig, bkg=bkg,
                    min_entries=5, bins_per_category=bins_per_category[channel])
            config[channel][category] = binning
            logger.info("Binning for category %s in channel %s:\n%s", category, channel, binning)

    # Clean-up
    f.Close()


if __name__ == "__main__":
    args = parse_arguments()
    setup_logging("{}_calculate_binning.log".format(args.era), logging.INFO)
    main(args)
