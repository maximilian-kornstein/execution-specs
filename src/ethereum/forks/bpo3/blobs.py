"""
Blob gas meters the data that blob-carrying transactions, introduced in
[EIP-4844], attach to a block.

Blob gas is accounted for separately from execution gas and has its own fee
market. Each block records its _excess blob gas_, which tracks how far blob
gas usage has run above the per-block target (see
[`calculate_excess_blob_gas`][excess]). The price of blob gas rises
exponentially with that excess (see [`calculate_blob_gas_price`][price]).

[EIP-4844]: https://eips.ethereum.org/EIPS/eip-4844
[excess]: ref:ethereum.forks.bpo3.blobs.calculate_excess_blob_gas
[price]: ref:ethereum.forks.bpo3.blobs.calculate_blob_gas_price
"""

from typing import Final

from ethereum_types.numeric import U64, Uint

from ethereum.forks.bpo2.blocks import Header as PreviousHeader
from ethereum.utils.numeric import taylor_exponential

from .blocks import Header
from .transactions import BlobTransaction, Transaction

GAS_PER_BLOB: Final[U64] = U64(2**17)
BLOB_SCHEDULE_TARGET: Final[U64] = U64(14)
BLOB_TARGET_GAS_PER_BLOCK: Final[U64] = GAS_PER_BLOB * BLOB_SCHEDULE_TARGET
BLOB_BASE_COST: Final[Uint] = Uint(2**13)
BLOB_SCHEDULE_MAX: Final[U64] = U64(21)
BLOB_MIN_GASPRICE: Final[Uint] = Uint(1)
BLOB_BASE_FEE_UPDATE_FRACTION: Final[Uint] = Uint(11684671)
MAX_BLOB_GAS_PER_BLOCK: Final[U64] = BLOB_SCHEDULE_MAX * GAS_PER_BLOB


def calculate_excess_blob_gas(
    parent_header: Header | PreviousHeader,
) -> U64:
    """
    Calculates the excess blob gas for the current block based
    on the gas used in the parent block.

    Parameters
    ----------
    parent_header :
        The parent block of the current block.

    Returns
    -------
    excess_blob_gas: `ethereum.base_types.U64`
        The excess blob gas for the current block.

    """
    # Defaults for a parent without blob gas fields.
    excess_blob_gas = U64(0)
    blob_gas_used = U64(0)
    base_fee_per_gas = Uint(0)

    if isinstance(parent_header, (Header, PreviousHeader)):
        # Read them from any parent that carries the fields, so
        # accumulated excess blob gas survives a fork transition.
        excess_blob_gas = parent_header.excess_blob_gas
        blob_gas_used = parent_header.blob_gas_used
        base_fee_per_gas = parent_header.base_fee_per_gas

    parent_blob_gas = excess_blob_gas + blob_gas_used
    if parent_blob_gas < BLOB_TARGET_GAS_PER_BLOCK:
        return U64(0)

    target_blob_gas_price = Uint(GAS_PER_BLOB)
    target_blob_gas_price *= calculate_blob_gas_price(excess_blob_gas)

    base_blob_tx_price = BLOB_BASE_COST * base_fee_per_gas
    if base_blob_tx_price > target_blob_gas_price:
        blob_schedule_delta = BLOB_SCHEDULE_MAX - BLOB_SCHEDULE_TARGET
        return (
            excess_blob_gas
            + blob_gas_used * blob_schedule_delta // BLOB_SCHEDULE_MAX
        )

    return parent_blob_gas - BLOB_TARGET_GAS_PER_BLOCK


def calculate_total_blob_gas(tx: Transaction) -> U64:
    """
    Calculate the total blob gas for a transaction.

    Parameters
    ----------
    tx :
        The transaction for which the blob gas is to be calculated.

    Returns
    -------
    total_blob_gas: `ethereum.base_types.Uint`
        The total blob gas for the transaction.

    """
    if isinstance(tx, BlobTransaction):
        return GAS_PER_BLOB * U64(len(tx.blob_versioned_hashes))
    else:
        return U64(0)


def calculate_blob_gas_price(excess_blob_gas: U64) -> Uint:
    """
    Calculate the blob gasprice for a block.

    Parameters
    ----------
    excess_blob_gas :
        The excess blob gas for the block.

    Returns
    -------
    blob_gasprice: `Uint`
        The blob gasprice.

    """
    return taylor_exponential(
        BLOB_MIN_GASPRICE,
        Uint(excess_blob_gas),
        BLOB_BASE_FEE_UPDATE_FRACTION,
    )


def calculate_data_fee(excess_blob_gas: U64, tx: Transaction) -> Uint:
    """
    Calculate the blob data fee for a transaction.

    Parameters
    ----------
    excess_blob_gas :
        The excess_blob_gas for the execution.
    tx :
        The transaction for which the blob data fee is to be calculated.

    Returns
    -------
    data_fee: `Uint`
        The blob data fee.

    """
    return Uint(calculate_total_blob_gas(tx)) * calculate_blob_gas_price(
        excess_blob_gas
    )
