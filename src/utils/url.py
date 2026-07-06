# -*- coding: utf-8 -*-
"""
URL helper utilities for manipulating and constructing URLs.

This module provides simple, reusable functions for common URL-related tasks,
such as merging query parameters. It relies on the `requests` library for
robust and correct URL handling.
"""

# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------

from typing import Mapping, Optional

from requests import PreparedRequest

# --------------------------------------------------------------------------------------
# Public Functions
# --------------------------------------------------------------------------------------


def merge_query_params(url: str, params: Mapping[str, Optional[str]]) -> str:
    """
    Safely merges a dictionary of query parameters into a URL.

    This function takes a base URL and a dictionary of parameters, and it correctly
    appends them as a query string. It handles existing query parameters in the
    URL and filters out any `None` values from the `params` dictionary to avoid
    empty query keys.

    It leverages `requests.PreparedRequest` to ensure that the URL and parameters
    are combined according to web standards, which is safer than manual string
    concatenation.

    Args:
        url: The base URL, which may or may not have existing query parameters.
        params: A mapping of parameter keys to string values. Values of `None`
                will be ignored.

    Returns:
        The new URL with the merged query parameters.
    """
    # Filter out None values to prevent them from being added to the query string.
    # Example: {"a": "1", "b": None} becomes {"a": "1"}
    clean_params = {k: v for k, v in params.items() if v is not None}

    # If there are no parameters to add, return the original URL to avoid
    # unnecessary processing or adding a trailing '?'.
    if not clean_params:
        return url

    # Use the robust URL preparation logic from the `requests` library.
    # This correctly handles merging with existing query strings.
    req = PreparedRequest()
    req.prepare_url(url, clean_params)

    # `req.url` now contains the fully formed URL.
    # The type ignore is because `req.url` can be `None` if `prepare_url`
    # hasn't been called, but it is guaranteed to be a string here.
    return req.url  # type: ignore[return-value]
