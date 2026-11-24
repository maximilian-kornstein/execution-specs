"""Test evm tracing functionality."""

from typing import List, cast

from ethereum_types.numeric import Uint

import ethereum.trace


def test_modify_evm_trace() -> None:
    """Tests that EVM trace handlers can be modified and work correctly."""
    trace1: List[ethereum.trace.TraceEvent] = []
    trace2: List[ethereum.trace.TraceEvent] = []

    def tracer1(
        evm: object,
        event: ethereum.trace.TraceEvent,
    ) -> None:
        del evm
        trace1.append(event)

    def tracer2(
        evm: object,
        event: ethereum.trace.TraceEvent,
    ) -> None:
        del evm
        trace2.append(event)

    ethereum.trace.set_evm_trace(tracer1)

    from ethereum.forks.prague.vm import Evm, Message
    from ethereum.forks.prague.vm.gas import charge_gas

    evm = Evm(
        pc=Uint(1),
        stack=[],
        memory=bytearray(),
        code=b"",
        gas_left=Uint(100),
        valid_jump_destinations=set(),
        logs=(),
        refund_counter=0,
        running=True,
        message=cast(Message, object()),
        output=b"",
        accounts_to_delete=set(),
        return_data=b"",
        error=None,
        accessed_addresses=set(),
        accessed_storage_keys=set(),
    )

    charge_gas(evm, Uint(5))

    assert not trace2
    assert isinstance(trace1[-1], ethereum.trace.GasAndRefund)
    assert trace1[-1].gas_cost == 5

    ethereum.trace.set_evm_trace(tracer2)

    charge_gas(evm, Uint(6))

    # Check that the old event is unmodified.
    assert isinstance(trace1[-1], ethereum.trace.GasAndRefund)
    assert trace1[-1].gas_cost == 5

    # Check that the new event is populated.
    assert isinstance(trace2[-1], ethereum.trace.GasAndRefund)
    assert trace2[-1].gas_cost == 6
