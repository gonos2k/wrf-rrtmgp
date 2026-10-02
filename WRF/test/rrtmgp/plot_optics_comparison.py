#!/usr/bin/env python3
"""Plot recorded roughness and exploratory pinned-CCPP snow optics comparisons."""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def save(fig, root: Path, stem: str) -> None:
    fig.tight_layout()
    fig.savefig(root / f'{stem}.png', dpi=180)
    svg = root / f'{stem}.svg'
    fig.savefig(svg, metadata={'Date': None})
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results_dir', type=Path)
    args = parser.parse_args()
    root = args.results_dir
    matplotlib.rcParams['svg.hashsalt'] = 'wrf-rrtmgp-optics'
    runs = {}
    for category in (1, 2, 3):
        with (root / f'ice-roughness-{category}.csv').open(newline='') as stream:
            runs[category] = {row['scenario']: row for row in csv.DictReader(stream)
                              if int(row['ncol']) == 1}
    cases = ['ice-10um', 'ice-30um', 'ice-60um', 'snow-30um', 'snow-60um', 'snow-130um', 'mixed-phase']
    fig, ax = plt.subplots(figsize=(8, 4))
    for category in (2, 3):
        differences = [float(runs[category][case]['swdnb_w_m2']) -
                       float(runs[1][case]['swdnb_w_m2']) for case in cases]
        ax.plot(range(len(cases)), differences, marker='o', label=f'category {category} - category 1')
    ax.axhline(0, color='gray', lw=.8)
    ax.set_xticks(range(len(cases)), cases, rotation=25, ha='right')
    ax.set_ylabel('Surface downward SW difference (W m$^{-2}$)')
    ax.set_title('Fully cloudy test columns; existing ice-LUT snow approximation')
    ax.legend()
    save(fig, root, 'roughness-sensitivity')

    with (root / 'snow-optics-source-comparison.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    fig, axes = plt.subplots(2, 3, figsize=(10, 5), sharex='row')
    for col, radius in enumerate((30, 60, 130)):
        for row, phase in enumerate(('SW', 'LW')):
            selected = [entry for entry in rows if entry['phase'] == phase and
                        float(entry['snow_radius_um']) == radius and float(entry['roughness']) == 1]
            x = [int(float(entry['band'])) for entry in selected]
            lut = 'lut_scaled_tau' if phase == 'SW' else 'lut_raw_tau'
            ccpp = 'ccpp_scaled_tau' if phase == 'SW' else 'ccpp_raw_tau'
            axis = axes[row, col]
            axis.plot(x, [float(entry[lut]) for entry in selected], 'o-', ms=3,
                      label='Ice LUT (category 1)')
            axis.plot(x, [float(entry[ccpp]) for entry in selected], 's--', ms=3,
                      label='Pinned CCPP snow equation')
            axis.set_title(f'{phase}'+ (' (delta scaled)' if phase == 'SW' else '') + f', radius {radius} µm')
            axis.set_ylabel('Optical depth')
            axis.set_xlabel('Band')
            axis.grid(alpha=.2)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle('50 g m$^{-2}$; cf=1; same numeric radius, differing optical models', fontsize=11)
    save(fig, root, 'snow-optics-comparison')


if __name__ == '__main__':
    main()
