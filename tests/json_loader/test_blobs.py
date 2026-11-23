"""
Tests for the blob gas constants and calculations in each fork's `blobs`
module.
"""

from dataclasses import fields
from importlib import import_module
from types import ModuleType
from typing import Any

import pytest
from ethereum_types.bytes import Bytes0, Bytes32, FixedBytes
from ethereum_types.numeric import U64, Uint

BLOB_FORKS = (
    "cancun",
    "prague",
    "osaka",
    "bpo1",
    "bpo2",
    "bpo3",
    "bpo4",
    "bpo5",
    "amsterdam",
    "bogota",
)
"""Every fork that prices blob gas."""

MOVED_FROM_VM_GAS = (
    "MAX_BLOB_GAS_PER_BLOCK",
    "calculate_excess_blob_gas",
    "calculate_total_blob_gas",
    "calculate_blob_gas_price",
    "calculate_data_fee",
    "check_max_fee_per_blob_gas",
)
"""Blob gas names that `vm.gas` no longer defines."""


def blobs(fork: str) -> ModuleType:
    """Import the `blobs` module of `fork`."""
    return import_module(f"ethereum.forks.{fork}.blobs")


def build(cls: type, **values: Any) -> Any:
    """
    Instantiate the dataclass `cls`, filling every field missing from
    `values` with a zero value of its type.
    """
    arguments: dict[str, Any] = {}
    for field in fields(cls):
        if field.name in values:
            arguments[field.name] = values[field.name]
        elif isinstance(field.type, type) and issubclass(
            field.type, FixedBytes
        ):
            arguments[field.name] = field.type(bytes(field.type.LENGTH))
        elif field.type is bytes:
            arguments[field.name] = b""
        elif isinstance(field.type, type):
            arguments[field.name] = field.type(0)
        else:
            arguments[field.name] = ()
    return cls(**arguments)


@pytest.mark.parametrize(
    "fork, target_blobs, max_blobs, update_fraction",
    [
        ("cancun", 3, 6, 3338477),
        ("prague", 6, 9, 5007716),
        ("osaka", 6, 9, 5007716),
        ("bpo1", 10, 15, 8346193),
        ("bpo2", 14, 21, 11684671),
    ],
)
def test_blob_schedule_constants(
    fork: str, target_blobs: int, max_blobs: int, update_fraction: int
) -> None:
    """Pin the blob schedule of each fork with a mainnet schedule."""
    module = blobs(fork)
    assert module.GAS_PER_BLOB == U64(2**17)
    assert module.BLOB_TARGET_GAS_PER_BLOCK == U64(target_blobs * 2**17)
    assert module.MAX_BLOB_GAS_PER_BLOCK == U64(max_blobs * 2**17)
    assert module.BLOB_MIN_GASPRICE == Uint(1)
    assert module.BLOB_BASE_FEE_UPDATE_FRACTION == Uint(update_fraction)


@pytest.mark.parametrize(
    "fork, excess_blob_gas, expected",
    [
        ("cancun", 0, 1),
        ("cancun", 10_000_000, 19),
        ("prague", 10_000_000, 7),
        ("osaka", 10_000_000, 7),
        ("bpo1", 10_000_000, 3),
        ("bpo2", 10_000_000, 2),
    ],
)
def test_calculate_blob_gas_price(
    fork: str, excess_blob_gas: int, expected: int
) -> None:
    """Price blob gas at `e ** (excess / update fraction)`, rounded down."""
    price = blobs(fork).calculate_blob_gas_price(U64(excess_blob_gas))
    assert price == Uint(expected)


@pytest.mark.parametrize(
    "fork, parent_excess, parent_used, parent_base_fee, expected",
    [
        pytest.param("cancun", 0, 786432, 0, 393216, id="cancun-full"),
        pytest.param("cancun", 0, 262144, 0, 0, id="cancun-below-target"),
        pytest.param("cancun", 131072, 393216, 0, 131072, id="cancun-carry"),
        pytest.param("prague", 0, 1179648, 0, 393216, id="prague-full"),
        pytest.param("prague", 0, 655360, 0, 0, id="prague-below-target"),
        pytest.param("osaka", 0, 1048576, 0, 262144, id="osaka"),
        pytest.param("osaka", 0, 1048576, 10**9, 349525, id="osaka-reserve"),
        pytest.param("bpo1", 0, 1835008, 0, 524288, id="bpo1"),
        pytest.param("bpo1", 0, 1835008, 10**9, 611669, id="bpo1-reserve"),
        pytest.param("bpo2", 0, 2621440, 0, 786432, id="bpo2"),
        pytest.param("bpo2", 0, 2621440, 10**9, 873813, id="bpo2-reserve"),
    ],
)
def test_calculate_excess_blob_gas(
    fork: str,
    parent_excess: int,
    parent_used: int,
    parent_base_fee: int,
    expected: int,
) -> None:
    """
    Carry the parent's blob gas above target into the next block, and, from
    Osaka on, keep the excess growing while blob gas is priced below the
    execution cost of a blob (the `-reserve` cases).
    """
    header_type = import_module(f"ethereum.forks.{fork}.blocks").Header
    parent_header = build(
        header_type,
        excess_blob_gas=U64(parent_excess),
        blob_gas_used=U64(parent_used),
        base_fee_per_gas=Uint(parent_base_fee),
    )
    excess = blobs(fork).calculate_excess_blob_gas(parent_header)
    assert excess == U64(expected)


@pytest.mark.parametrize("fork", BLOB_FORKS)
def test_blob_gas_and_data_fee_of_transactions(fork: str) -> None:
    """Charge blob gas for each blob of a transaction, and only for blobs."""
    module = blobs(fork)
    transactions = import_module(f"ethereum.forks.{fork}.transactions")
    blob_tx = build(
        transactions.BlobTransaction,
        blob_versioned_hashes=(Bytes32(bytes(32)), Bytes32(bytes(32))),
    )
    legacy_tx = build(transactions.LegacyTransaction, to=Bytes0())

    assert module.calculate_total_blob_gas(blob_tx) == U64(262144)
    assert module.calculate_data_fee(U64(0), blob_tx) == Uint(262144)
    assert module.calculate_total_blob_gas(legacy_tx) == U64(0)
    assert module.calculate_data_fee(U64(0), legacy_tx) == Uint(0)


@pytest.mark.parametrize("fork", BLOB_FORKS)
def test_vm_gas_defines_no_blob_gas(fork: str) -> None:
    """
    Keep blob gas out of the EVM's gas module, which may only import it from
    `blobs`.
    """
    module = blobs(fork)
    gas = import_module(f"ethereum.forks.{fork}.vm.gas")
    for name in MOVED_FROM_VM_GAS:
        if hasattr(gas, name):
            assert getattr(gas, name) is getattr(module, name)
    assert not [
        name
        for name in vars(gas.GasCosts)
        if name == "PER_BLOB" or name.startswith("BLOB_")
    ]
