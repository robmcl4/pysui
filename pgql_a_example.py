#    Copyright Frank V. Castellucci
#    SPDX-License-Identifier: Apache-2.0

# -*- coding: utf-8 -*-

"""Sample module for incremental buildout of Async Sui GraphQL RPC for Pysui 1.0.0."""

import asyncio
import base64

from pysui import SuiConfig, SuiRpcResult, AsyncClient
from pysui.sui.sui_txn import AsyncTransaction
from pysui.sui.sui_pgql.pgql_clients import AsyncSuiGQLClient
import pysui.sui.sui_pgql.pgql_query as qn
import pysui.sui.sui_pgql.pgql_types as ptypes


def handle_result(result: SuiRpcResult) -> SuiRpcResult:
    """."""
    if result.is_ok():
        if hasattr(result.result_data, "to_json"):
            print(result.result_data.to_json(indent=2))
        else:
            print(result.result_data)
    else:
        print(result.result_string)
        if result.result_data and hasattr(result.result_data, "to_json"):
            print(result.result_data.to_json(indent=2))
        else:
            print(result.result_data)
    return result


async def do_coin_meta(client: AsyncSuiGQLClient):
    """Fetch meta data about coins, includes supply."""
    # Defaults to 0x2::sui::SUI
    handle_result(await client.execute_query_node(with_node=qn.GetCoinMetaData()))


async def do_coins_for_type(client: AsyncSuiGQLClient):
    """Fetch coins of specific type for owner."""
    handle_result(
        await client.execute_query_node(
            with_node=qn.GetCoins(
                owner=client.config.active_address.address,
                coin_type="0x2::sui::SUI",
            )
        )
    )


async def do_gas(client: AsyncSuiGQLClient):
    """Fetch 0x2::sui::SUI (default) for owner."""
    result = handle_result(
        await client.execute_query_node(
            with_node=qn.GetCoins(owner=client.config.active_address.address)
        )
    )
    if result.is_ok():
        print(
            f"Total coins in page: {len(result.result_data.data)} has more: {result.result_data.next_cursor.hasNextPage}"
        )


async def do_sysstate(client: AsyncSuiGQLClient):
    """Fetch the most current system state summary."""
    handle_result(
        await client.execute_query_node(with_node=qn.GetLatestSuiSystemState())
    )


async def do_all_balances(client: AsyncSuiGQLClient):
    """Fetch all coin types and there total balances for owner.

    Demonstrates paging as well
    """
    result = await client.execute_query_node(
        with_node=qn.GetAllCoinBalances(owner=client.config.active_address.address)
    )
    handle_result(result)
    if result.is_ok():
        while result.result_data.next_cursor.hasNextPage:
            result = await client.execute_query_node(
                with_node=qn.GetAllCoinBalances(
                    owner=client.config.active_address.address,
                    next_page=result.next_cursor,
                )
            )
            handle_result(result)
        print("DONE")


async def do_object(client: AsyncSuiGQLClient):
    """Fetch specific object data."""
    handle_result(
        await client.execute_query_node(with_node=qn.GetObject(object_id="0x6"))
    )


async def do_objects(client: AsyncSuiGQLClient):
    """Fetch all objects help by owner."""
    handle_result(
        await client.execute_query_node(
            with_node=qn.GetObjectsOwnedByAddress(
                owner=client.config.active_address.address
            )
        )
    )


async def do_past_object(client: AsyncSuiGQLClient):
    """Fetch a past object.
    To run, change the objectID str and version int.
    """
    handle_result(
        await client.execute_query_node(
            with_node=qn.GetPastObject(
                object_id="0xdfa764b29d303acecc801828839108ea81a45e93c3b9ccbe05b0d9a697a2a9ed",
                version=17078252,
            )
        )
    )


async def do_multiple_past_object(client: AsyncSuiGQLClient):
    """Fetch a past object.
    To run, change the objectID str and version int.
    """
    past_objects = [
        {
            "objectId": "0xdfa764b29d303acecc801828839108ea81a45e93c3b9ccbe05b0d9a697a2a9ed",
            "version": 17078252,
        }
    ]
    handle_result(
        await client.execute_query_node(
            with_node=qn.GetMultiplePastObjects(for_versions=past_objects)
        )
    )


async def do_objects_for(client: AsyncSuiGQLClient):
    """Fetch specific objects by their ids.

    These are test IDs, replace to run.
    """
    handle_result(
        await client.execute_query_node(
            with_node=qn.GetMultipleObjects(
                object_ids=[
                    "0x0847e1e02965e3f6a8b237152877a829755fd2f7cfb7da5a859f203a8d4316f0",
                    "0x68e961e3af906b160e1ff21137304537fa6b31f5a4591ef3acf9664eb6e3cd2b",
                    "0x77851d73e7c1227c048fc7cbf21ff9053faa872950dd33f5d0cb5b40a79d9d99",
                ]
            )
        )
    )


async def do_dynamics(client: AsyncSuiGQLClient):
    """Get objects dynamic field and dynamic object fields.

    This is test ID, replace to run.
    """
    handle_result(
        await client.execute_query_node(
            with_node=qn.GetDynamicFields(
                object_id="0xdfa764b29d303acecc801828839108ea81a45e93c3b9ccbe05b0d9a697a2a9ed"
            )
        )
    )


async def do_event(client: AsyncSuiGQLClient):
    """."""
    handle_result(
        await client.execute_query_node(
            with_node=qn.GetEvents(event_filter={"sender": "0x0"})
        )
    )


async def do_configs(client: AsyncSuiGQLClient):
    """Fetch the GraphQL, Protocol and System configurations."""
    print(client.rpc_config.to_json(indent=2))


async def do_chain_id(client: AsyncSuiGQLClient):
    """Fetch the current environment chain_id.

    Demonstrates overriding serialization
    """
    print(client.chain_id)


async def do_tx(client: AsyncSuiGQLClient):
    """Fetch specific transaction by it's digest."""
    handle_result(
        await client.execute_query_node(
            with_node=qn.GetTx(digest="A8kCT1n8dmCWchz5WnKPsQ8x7U49ExgMEWJ13nRULpiz")
        )
    )


async def do_txs(client: AsyncSuiGQLClient):
    """Fetch transactions.

    We loop through 3 pages.
    """
    result = await client.execute_query_node(with_node=qn.GetMultipleTx())
    handle_result(result)
    if result.is_ok():
        max_page = 3
        in_page = 0
        while True:
            in_page += 1
            if in_page < max_page and result.result_data.next_cursor:
                result = await client.execute_query_node(
                    with_node=qn.GetMultipleTx(next_page=result.result_data.next_cursor)
                )
                handle_result(result)
            else:
                break
        print("DONE")


async def do_staked_sui(client: AsyncSuiGQLClient):
    """."""
    owner = client.config.active_address.address
    handle_result(
        await client.execute_query_node(with_node=qn.GetDelegatedStakes(owner=owner))
    )


async def do_latest_cp(client: AsyncSuiGQLClient):
    """."""
    qnode = qn.GetLatestCheckpointSequence()
    # print(qnode.query_as_string())
    handle_result(await client.execute_query_node(with_node=qnode))


async def do_sequence_cp(client: AsyncSuiGQLClient):
    """."""
    result = await client.execute_query_node(with_node=qn.GetLatestCheckpointSequence())
    if result.is_ok():
        cp: ptypes.CheckpointGQL = result.result_data
        handle_result(
            await client.execute_query_node(
                with_node=qn.GetCheckpointBySequence(sequence_number=cp.sequence_number)
            )
        )
    else:
        print(result.result_string)


async def do_digest_cp(client: AsyncSuiGQLClient):
    """."""
    result = await client.execute_query_node(with_node=qn.GetLatestCheckpointSequence())
    if result.is_ok():
        cp: ptypes.CheckpointGQL = result.result_data
        handle_result(
            await client.execute_query_node(
                with_node=qn.GetCheckpointByDigest(digest=cp.digest)
            )
        )
    else:
        print(result.result_string)


async def do_checkpoints(client: AsyncSuiGQLClient):
    """."""
    handle_result(await client.execute_query_node(with_node=qn.GetCheckpoints()))


async def do_refgas(client: AsyncSuiGQLClient):
    """Fetch the most current system state summary."""
    handle_result(await client.execute_query_node(with_node=qn.GetReferenceGasPrice()))


async def do_nameservice(client: AsyncSuiGQLClient):
    """Fetch the most current system state summary."""
    handle_result(
        await client.execute_query_node(
            with_node=qn.GetNameServiceAddress(name="gql-frank")
        )
    )


async def do_owned_nameservice(client: AsyncSuiGQLClient):
    """Fetch the most current system state summary."""
    handle_result(
        await client.execute_query_node(
            with_node=qn.GetNameServiceNames(owner=client.config.active_address.address)
        )
    )


async def do_validators_apy(client: AsyncSuiGQLClient):
    """Fetch the most current validators apy and identity."""
    handle_result(await client.execute_query_node(with_node=qn.GetValidatorsApy()))


async def do_validators(client: AsyncSuiGQLClient):
    """Fetch the most current validator detail."""
    handle_result(await client.execute_query_node(with_node=qn.GetCurrentValidators()))


async def do_protcfg(client: AsyncSuiGQLClient):
    """Fetch the most current system state summary."""
    handle_result(
        await client.execute_query_node(with_node=qn.GetProtocolConfig(version=30))
    )


async def do_struct(client: AsyncSuiGQLClient):
    """Fetch structure by package::module::struct_name.

    This is a testnet object!!!
    """
    result = await client.execute_query_node(
        with_node=qn.GetStructure(
            package="0x2",
            module_name="coin",
            structure_name="CoinMetadata",
        )
    )
    if result.is_ok():
        print(result.result_data.to_json(indent=2))


async def do_structs(client: AsyncSuiGQLClient):
    """Fetch structures by package::module.

    This is a testnet object!!!
    """
    result = await client.execute_query_node(
        with_node=qn.GetStructures(
            package="0x2",
            module_name="coin",
        )
    )
    if result.is_ok():
        print(result.result_data.to_json(indent=2))


async def do_func(client: AsyncSuiGQLClient):
    """Fetch structures by package::module.

    This is a testnet object!!!
    """
    result = await client.execute_query_node(
        with_node=qn.GetFunction(
            package="0x2",
            module_name="coin",
            function_name="join",
        )
    )
    if result.is_ok():
        print(result.result_data.to_json(indent=2))


async def do_funcs(client: AsyncSuiGQLClient):
    """Fetch structures by package::module.

    This is a testnet object!!!
    """
    result = await client.execute_query_node(
        with_node=qn.GetFunctions(
            package="0x2",
            module_name="coin",
        )
    )
    if result.is_ok():
        print(result.result_data.to_json(indent=2))


async def do_module(client: AsyncSuiGQLClient):
    """Fetch a module from package.

    This is a testnet object!!!
    """
    result = await client.execute_query_node(
        with_node=qn.GetModule(
            package="0x2",
            module_name="coin",
        )
    )
    if result.is_ok():
        print(result.result_data.to_json(indent=2))


async def do_package(client: AsyncSuiGQLClient):
    """Fetch a module from package.

    This is a testnet object!!!
    """
    result = await client.execute_query_node(
        with_node=qn.GetPackage(
            package="0x2",
        )
    )
    if result.is_ok():
        print(result.result_data.to_json(indent=2))


async def do_dry_run(client: AsyncSuiGQLClient):
    """Execute a dry run."""
    if client.chain_environment == "testnet":
        txer = AsyncTransaction(client=AsyncClient(client.config))
        scres = await txer.split_coin(coin=txer.gas, amounts=[1000000000])
        await txer.transfer_objects(
            transfers=scres, recipient=client.config.active_address
        )

        tx_data = await txer.get_transaction_data()
        tx_b64 = base64.b64encode(tx_data.serialize()).decode()
        handle_result(
            await client.execute_query_node(
                with_node=qn.DryRunTransaction(tx_bytestr=tx_b64)
            )
        )


async def do_execute(client: AsyncSuiGQLClient):
    """Execute a transaction."""
    if client.chain_environment == "testnet":
        rpc_client = AsyncClient(client.config)
        txer = AsyncTransaction(client=rpc_client)
        scres = await txer.split_coin(coin=txer.gas, amounts=[1000000000])
        await txer.transfer_objects(
            transfers=scres, recipient=client.config.active_address
        )
        tx_b64 = await txer.deferred_execution(run_verification=True)
        print(tx_b64)
        sig_array = txer.signer_block.get_signatures(client=rpc_client, tx_bytes=tx_b64)
        rsig_array = [x.value for x in sig_array.array]
        print(rsig_array)
        handle_result(
            await client.execute_query_node(
                with_node=qn.ExecuteTransaction(tx_bytestr=tx_b64, sig_array=rsig_array)
            )
        )


async def main():
    """."""
    client_init = AsyncSuiGQLClient(
        write_schema=False,
        config=SuiConfig.default_config(),
    )
    print(f"Schema version {client_init.schema_version}")
    ## QueryNodes (fetch)
    # await do_coin_meta(client_init)
    # await do_coins_for_type(client_init)
    await do_gas(client_init)
    # await do_sysstate(client_init)
    # await do_all_balances(client_init)
    # await do_object(client_init)
    # await do_objects(client_init)
    # await do_past_object(client_init)
    # await do_multiple_past_object(client_init)
    # await do_objects_for(client_init)
    # await do_dynamics(client_init)
    # await do_event(client_init)
    # await do_tx(client_init)
    # await do_txs(client_init)
    # await do_staked_sui(client_init)
    # await do_latest_cp(client_init)
    # await do_sequence_cp(client_init)
    # await do_digest_cp(client_init)
    # await do_checkpoints(client_init)
    # await do_owned_nameservice(client_init)
    # await do_nameservice(client_init)
    # await do_refgas(client_init)
    # await do_struct(client_init)
    # await do_structs(client_init)
    # await do_func(client_init)
    # await do_funcs(client_init)
    # await do_module(client_init)
    # await do_package(client_init)
    # await do_dry_run(client_init)
    # await do_execute(client_init)
    ## Config
    # await do_chain_id(client_init)
    # await do_configs(client_init)
    # await do_protcfg(client_init)
    await client_init.client.close_async()


if __name__ == "__main__":
    asyncio.run(main())
