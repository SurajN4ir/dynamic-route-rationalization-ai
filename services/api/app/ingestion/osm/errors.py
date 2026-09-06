class OSMParseError(Exception):
    """The input file is not well-formed OSM XML at all - distinct from a
    single way being rejected (which is a normal, expected outcome
    recorded in IngestionStats, not an exception)."""
