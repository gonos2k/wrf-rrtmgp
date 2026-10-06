#!/usr/bin/env python3
"""Portable entry point for the exact scorer, binding packaged NOAA files."""
from pathlib import Path
import sys

import score_surfrad as scorer

PACKAGE = Path(__file__).resolve().parent
REPOSITORY = PACKAGE.parents[3]
scorer.OBS_DIR = PACKAGE / "surfrad"
scorer.PLAN_DIR = REPOSITORY / "build/udm-current-24h-plan"

raise SystemExit(scorer.main())
