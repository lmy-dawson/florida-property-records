"""Shared record shaping across counties."""
from datetime import date

import pytest

from src import normalize as n


def test_addresses_compare_equal_after_normalising():
    assert n.norm_addr("123 North Main Street, Apt #4") == n.norm_addr("123 N MAIN ST APT 4")


@pytest.mark.parametrize("name,kind", [
    ("SMITH JOHN & MARY", "individual"),
    ("SUNSHINE HOLDINGS LLC", "entity"),
    ("JONES FAMILY TRUST", "entity"),
    ("CITY OF TAMPA", "entity"),
    (None, "individual"),
])
def test_owner_type(name, kind):
    assert n.owner_type(name) == kind


def test_confidential_owners_are_detected():
    assert n.is_confidential("CONFIDENTIAL PER F.S. 119.071")
    assert n.is_confidential("name exempt per fs 119")
    assert not n.is_confidential("JOHN SMITH")


@pytest.mark.parametrize("addr,usable", [
    ("101 E KENNEDY BLVD", True), ("", False), ("0", False),
    ("0 EGMONT KEY", False), ("12345", False), (None, False),
])
def test_has_usable_address(addr, usable):
    assert n.has_usable_address(addr) is usable


def test_numbers_tolerate_commas_blanks_and_junk():
    assert n.num("1,234.5") == 1234.5
    assert n.num("") is None and n.num("n/a") is None
    assert n.integer("43,560") == 43560


def test_dbase_and_excel_dates():
    assert n.dbf_date("20240229") == "2024-02-29"
    assert n.dbf_date("20230230") is None and n.dbf_date("2024") is None
    assert n.excel_date(45292) == "2024-01-01"
    assert n.excel_date(date(2025, 5, 6)) == "2025-05-06"
    assert n.excel_date(0) is None and n.excel_date(999999) is None


@pytest.mark.parametrize("desc,kind", [
    ("SINGLE FAMILY R", "Single Family"),
    ("VACANT RESIDENTIAL", "Vacant Land"),
    ("Pkg Lot (Comm)", "Commercial"),
    ("DUPLEX", "Multi-Family"),
    ("CONDOMINIUM", "Condominium"),
    ("", "Other"),
])
def test_property_type_maps_county_vocabularies(desc, kind):
    assert n.property_type(desc) == kind
