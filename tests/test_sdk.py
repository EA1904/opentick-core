import pytest
from tvdata.get import catalog
from tvdata.get import get_ohlcv

def test_imports_and_sdk_initialization():
    """
    Ensure that the basic SDK modules can be imported without errors,
    verifying that standard libraries and third-party dependencies are present.
    """
    import tvdata
    assert tvdata is not None
    assert get_ohlcv is not None
    assert catalog is not None

def test_catalog_query_returns_dataframe():
    """
    Test that calling the catalog() function returns a pandas DataFrame.
    If the database is completely empty or missing, it should return an empty DataFrame,
    not throw an exception.
    """
    df = catalog()
    import pandas as pd
    assert isinstance(df, pd.DataFrame)
