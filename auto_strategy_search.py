#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backward-compatible CLI wrapper for the HIVM strategy search tool.

The implementation lives in the ``strategy_search`` package so the codebase can
be maintained and tested as normal modules. Existing commands such as
``python auto_strategy_search.py ...`` continue to work.
"""
from __future__ import annotations

from strategy_search.core import *  # re-export legacy public API for old tests/scripts
from strategy_search.core import main


if __name__ == "__main__":
    main()
