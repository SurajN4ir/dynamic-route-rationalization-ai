"""Shared prediction data/feature foundation - see
docs/architecture/TASK205_DESIGN.md.

Not one of doc 10's reserved `ml/<model>/` directories - a new,
explicitly-flagged addition (same pattern as TASK-202's ingestion
placement decision) holding the feature-contract, static/temporal/
telemetry-derived feature computation, target definitions, dataset
generation, and chronological splitting logic every future `ml/<model>/
features.py` will import from, rather than duplicating (doc 07 §7.7
explicitly warns against duplicated feature logic across models).
"""
