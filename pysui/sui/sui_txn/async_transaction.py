#    Copyright Frank V. Castellucci
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#        http://www.apache.org/licenses/LICENSE-2.0
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

# -*- coding: utf-8 -*-
# pylint: disable=too-many-instance-attributes

"""Sui asynchronous Transaction for building Programmable Transactions."""

from asyncio.format_helpers import _get_function_source
import logging
import base64
from typing import Optional, Union, Any, Callable, Awaitable
from deprecated.sphinx import versionadded, versionchanged

from pysui import (
    AsyncClient,
    ObjectID,
    SuiAddress,
    SuiRpcResult,
    handle_result,
)
from pysui.sui.sui_builders.base_builder import SuiRequestType
from pysui.sui.sui_builders.get_builders import GetFunction
from pysui.sui.sui_txresults.common import GenericRef
from pysui.sui.sui_types.collections import SuiArray
from pysui.sui.sui_types.scalars import SuiString
from pysui.sui.sui_types.scalars import SuiInteger, SuiString, SuiU64, SuiU8
from pysui.sui.sui_txn.signing_ms import SigningMultiSig
from pysui.sui.sui_txn.transaction import _SuiTransactionBase
import pysui.sui.sui_txn.transaction_builder as tx_builder
from pysui.sui.sui_txresults.complex_tx import TxInspectionResult
from pysui.sui.sui_txn.transaction import (
    _DebugInspectTransaction,
    _SuiTransactionBase,
)
from pysui.sui.sui_builders.exec_builders import (
    ExecuteTransaction,
)
from pysui.sui.sui_txresults.single_tx import (
    AddressOwner,
    ImmutableOwner,
    ObjectNotExist,
    ObjectRead,
    SharedOwner,
    StakedSui,
    SuiCoinObject,
)

from pysui.sui.sui_types import bcs

# Standard library logging setup
logger = logging.getLogger("pysui.async_transaction")
if not logging.getLogger().handlers:
    logger.addHandler(logging.NullHandler())
    logger.propagate = False


@versionchanged(
    version="0.30.0", reason="Separated sync and async SuiTransaction."
)
class SuiTransactionAsync(_SuiTransactionBase):
    """."""

    @versionchanged(
        version="0.29.1", reason="Eliminated redundant gas price RPC call"
    )
    def __init__(
        self,
        client: AsyncClient,
        merge_gas_budget: bool = False,
        initial_sender: Union[SuiAddress, SigningMultiSig] = False,
    ) -> None:
        """Transaction initializer."""
        super().__init__(client, merge_gas_budget, initial_sender)

    @versionchanged(version="0.17.0", reason="Only used internally.")
    @versionchanged(
        version="0.17.0", reason="Reworked using SignerBlock gas resolution."
    )
    @versionchanged(
        version="0.21.1", reason="Corrected using multisig senders."
    )
    @versionchanged(
        version="0.24.1",
        reason="Brought transaction cost inline, avoiding redundancy.",
    )
    @versionchanged(
        version="0.28.0",
        reason="Added optional 'use_gas_object'.",
    )
    async def _build_for_execute(
        self,
        gas_budget: Union[str, SuiString],
        use_gas_object: Optional[Union[str, ObjectID]] = None,
    ) -> bcs.TransactionData:
        """build_for_execute Generates the TransactionData object.

        Note: If wanting to execute, this structure needs to be serialized to a base64 string. See
        the execute method below

        :param gas_budget: The gas budget to use. An introspection of the transaciton is performed and
            and this method will use the larger of the two.
        :type gas_budget: Union[int, SuiInteger]
        :param use_gas_object: Explicit gas object to use for payment, defaults to None
        :type use_gas_object: Optional[Union[str, ObjectID]], optional
        :return: TransactionData object replete with all required fields for execution
        :rtype: bcs.TransactionData
        """
        # Get the transaction body
        tx_kind = self.raw_kind()
        # Get costs
        tx_kind_b64 = base64.b64encode(tx_kind.serialize()).decode()
        if self.signer_block.sender:
            for_sender: Union[
                SuiAddress, SigningMultiSig
            ] = self.signer_block.sender
            if not isinstance(for_sender, SuiAddress):
                for_sender = for_sender.multi_sig.as_sui_address
        else:
            for_sender = self.client.config.active_address
        try:
            logger.debug(f"Inspecting {tx_kind_b64}")
            result = await self.client.execute(
                _DebugInspectTransaction(
                    sender_address=for_sender, tx_bytes=tx_kind_b64
                )
            )
            if result.is_ok():
                result = SuiRpcResult(
                    True, "", TxInspectionResult.factory(result.result_data)
                )
            else:
                logger.exception(
                    f"Inspecting transaction failed with {result.result_string}"
                )
                raise ValueError(result.result_string)

        except KeyError as kexcp:
            logger.exception(
                f"Malformed inspection results {result.result_data}"
            )

            raise ValueError(result.result_data)

        # result = await self.client.execute(
        #     InspectTransaction(sender_address=for_sender, tx_bytes=tx_kind_b64)
        # )
        if result.is_ok():
            ispec: TxInspectionResult = result.result_data
            gas_budget = (
                gas_budget if isinstance(gas_budget, str) else gas_budget.value
            )
            gas_budget = max(ispec.effects.gas_used.total, int(gas_budget))
        if use_gas_object:
            test_gas_object = (
                use_gas_object
                if isinstance(use_gas_object, str)
                else use_gas_object.value
            )
            if test_gas_object in self.builder.objects_registry:
                raise ValueError(
                    f"use_gas_object {test_gas_object} in use in transaction."
                )
            use_coin: ObjectRead = handle_result(
                await self.client.get_object(test_gas_object)
            )
            if use_coin.balance < gas_budget:
                logger.exception(
                    f"Explicit use_gas_object {test_gas_object} with balance {use_coin.balance} insuffient for cost {gas_budget}"
                )
                raise ValueError(f"Insufficient gas")

            gas_object = bcs.GasData(
                [
                    bcs.ObjectReference(
                        bcs.Address.from_str(use_coin.object_id),
                        int(use_coin.version),
                        bcs.Digest.from_str(use_coin.digest),
                    )
                ],
                bcs.Address.from_str(use_coin.owner.address_owner),
                int(self._current_gas_price),
                int(gas_budget),
            )

        else:
            # Fetch the payment

            gas_object = await self._sig_block.get_gas_object_async(
                client=self.client,
                budget=gas_budget,
                objects_in_use=self.builder.objects_registry,
                merge_coin=self._merge_gas,
                gas_price=int(self._current_gas_price),
            )
        if isinstance(self.signer_block.sender, SuiAddress):
            who_sends = self.signer_block.sender.address
        else:
            who_sends = self.signer_block.sender.signing_address
        return bcs.TransactionData(
            "V1",
            bcs.TransactionDataV1(
                tx_kind,
                bcs.Address.from_str(who_sends),
                gas_object,
                bcs.TransactionExpiration("None"),
            ),
        )

    @versionadded(
        version="0.17.0", reason="Convenience for serializing and dry-running."
    )
    async def get_transaction_data(self, *, gas_budget) -> bcs.TransactionData:
        """."""
        return await self._build_for_execute(gas_budget)

    @versionchanged(
        version="0.16.1", reason="Added 'additional_signers' optional argument"
    )
    @versionchanged(
        version="0.17.0",
        reason="Revamped for all signature potentials and types.",
    )
    @versionchanged(
        version="0.25.0",
        reason="Made gas_budget optiona, defaults to 1M mists.",
    )
    @versionchanged(version="0.25.0", reason="Added execution options.")
    @versionchanged(
        version="0.28.0",
        reason="Added optional 'use_gas_object'.",
    )
    async def execute(
        self,
        *,
        gas_budget: Optional[Union[str, SuiString]] = "1000000",
        options: Optional[dict] = None,
        use_gas_object: Optional[Union[str, ObjectID]] = None,
    ) -> SuiRpcResult:
        """execute Finalizes transaction and submits for execution on the chain.

        :param gas_budget: The gas budget to use. An introspection of the transaciton is performed
            and this method will use the larger of the two, defaults to 1000000
        :type gas_budget: Optional[Union[str, SuiString]], optional
        :param options: An options dictionary to pass to sui_executeTransactionBlock to control the
            information results, defaults to None
        :type options: Optional[dict], optional
        :param use_gas_object: Explicit gas object to use for payment, defaults to None
            Will fail if provided object is marked as 'in use' in commands
        :type use_gas_object: Optional[Union[str, ObjectID]], optional
        :return: The result of running the transaction
        :rtype: SuiRpcResult
        """
        assert not self._executed, "Transaction already executed"
        gas_budget = gas_budget if gas_budget else "1000000"
        tx_data = await self._build_for_execute(gas_budget, use_gas_object)
        tx_b64 = base64.b64encode(tx_data.serialize()).decode()
        exec_tx = ExecuteTransaction(
            tx_bytes=tx_b64,
            signatures=self.signer_block.get_signatures(
                client=self.client, tx_bytes=tx_b64
            ),
            options=options,
            request_type=SuiRequestType.WAITFORLOCALEXECUTION,
        )
        iresult = await self.client.execute(exec_tx)
        self._executed = True
        return iresult

    @versionchanged(
        version="0.16.1",
        reason="Added returning SuiRpcResult if inspect transaction failed.",
    )
    async def inspect_all(self) -> Union[TxInspectionResult, SuiRpcResult]:
        """inspect_all Returns results of sui_devInspectTransactionBlock on the current Transaction.

        :param for_sender: Used for inspection. If not supplied, uses current Transaction sender, defaults to None
        :type for_sender: Union[str, SuiAddress], optional
        :return: The successful result or the SuiRpcResult if inspect transaction failed.
        :rtype: Union[TxInspectionResult, SuiRpcResult]
        """
        tx_bytes = self.build_for_inspection()
        if self.signer_block.sender:
            for_sender: Union[
                SuiAddress, SigningMultiSig
            ] = self.signer_block.sender
            if not isinstance(for_sender, SuiAddress):
                for_sender = for_sender.multi_sig.as_sui_address
        else:
            for_sender = self.client.config.active_address
        try:
            logger.debug(f"Inspecting {tx_bytes}")
            result = await self.client.execute(
                _DebugInspectTransaction(
                    sender_address=for_sender, tx_bytes=tx_bytes
                )
            )
            result = SuiRpcResult(
                True, "", TxInspectionResult.factory(result.result_data)
            )

        except KeyError as kexcp:
            logger.exception(
                f"Malformed inspection results {result.result_data}"
            )
            raise ValueError(result.result_data)

        # result = await self.client.execute(
        #     InspectTransaction(sender_address=for_sender, tx_bytes=tx_bytes)
        # )
        if result.is_ok():
            return result.result_data
        return result

    # Argument resolution to lower level types
    @versionadded(
        version="0.18.0", reason="Reuse for argument nested list recursion."
    )
    @versionchanged(version="0.29.0", reason="Handle scale of object fetch.")
    async def _resolve_objects(
        self, items: list, objref_indexes: list, objtup_indexes: list
    ):
        """Finalizes object ref types."""
        if objref_indexes:
            res = await self.client.get_objects_for(
                [items[x] for x in objref_indexes]
            )

            # res = await self.client.execute(
            #     GetMultipleObjects(
            #         object_ids=[items[x] for x in objref_indexes]
            #     )
            # )
            if res.is_ok():
                res_list = res.result_data
                if len(res_list) != len(objref_indexes):
                    raise ValueError(
                        f"Unable to find object in set {[items[x] for x in objref_indexes]}"
                    )
                # Update items list and register tuple conversion
                for index, result in enumerate(res_list):
                    items[objref_indexes[index]] = result
                    objtup_indexes.append(objref_indexes[index])
            else:
                raise ValueError(f"{res.result_string}")
        if objtup_indexes:
            for tindex in objtup_indexes:
                item = items[tindex]
                if isinstance(item.owner, (AddressOwner, ImmutableOwner)):
                    obj_ref = GenericRef(
                        item.object_id, item.version, item.digest
                    )
                    b_obj_arg = bcs.ObjectArg(
                        "ImmOrOwnedObject",
                        bcs.ObjectReference.from_generic_ref(obj_ref),
                    )
                elif isinstance(item.owner, SharedOwner):
                    b_obj_arg = bcs.ObjectArg(
                        "SharedObject",
                        bcs.SharedObjectReference.from_object_read(item),
                    )
                items[tindex] = (
                    bcs.BuilderArg(
                        "Object", bcs.Address.from_str(item.object_id)
                    ),
                    b_obj_arg,
                )

    @versionchanged(
        version="0.18.0", reason="Handle argument nested list recursion."
    )
    async def _resolve_arguments(self, items: list) -> list:
        """Process list intended as 'params' in move call."""
        objref_indexes: list[int] = []
        objtup_indexes: list[int] = []
        # Separate the index based on conversion types
        for index in range(len(items)):
            self._resolve_item(index, items, objref_indexes, objtup_indexes)
        await self._resolve_objects(items, objref_indexes, objtup_indexes)
        return items

    # TODO: Investigate functools LRU
    @versionchanged(
        version="0.20.2", reason="Capture function argument meta data as well"
    )
    async def _move_call_target_cache(
        self, target: str
    ) -> tuple[bcs.Address, str, str, list, int]:
        """Used to resolve information regarding a move call target.

        This caches the result of a GetFunction meta-data information essention to setting up
        the proper command return types.
        """
        if target in self._MC_RESULT_CACHE:
            return self._MC_RESULT_CACHE[target]
        package_id, module_id, function_id = target.split("::")
        result = await self.client.execute(
            GetFunction(
                package=package_id,
                module_name=module_id,
                function_name=function_id,
            )
        )
        if result.is_ok():
            reslen = len(result.result_data.returns)
            if reslen:
                pass
            res_tup = (
                bcs.Address.from_str(package_id),
                module_id,
                function_id,
                result.result_data.parameters,
                reslen,
            )
            # res_cnt: int = len(result.result_data.returns)
            # package_id = bcs.Address.from_str(package_id)
            self._MC_RESULT_CACHE[target] = res_tup
            return res_tup
        raise ValueError(f"Unable to find target: {target}")

    @versionchanged(
        version="0.19.0", reason="Check that only type Objects are passed"
    )
    @versionchanged(
        version="0.21.1", reason="Added optional item_type argument"
    )
    async def make_move_vector(
        self, items: list[Any], item_type: Optional[str] = None
    ) -> bcs.Argument:
        """Create a call to convert a list of objects to a Sui 'vector' of item_type."""

        def _first_non_argument_type(inner_list: list) -> Any:
            """."""
            result = None
            for inner_item in inner_list:
                if not isinstance(inner_item, bcs.Argument):
                    result = inner_item
                    break
            return result

        if item_type:
            type_tag = bcs.OptionalTypeTag(
                bcs.TypeTag.type_tag_from(item_type)
            )
        else:
            type_tag = bcs.OptionalTypeTag()
        if items:
            first_item = _first_non_argument_type(items)
            if first_item:
                # If not all arguments, ensure the remaining are consistent
                first_class = first_item.__class__.__name__
                if (
                    first_class != "Argument"
                    and first_class in self._PURE_CANDIDATES
                ):
                    raise ValueError(
                        f"make_move_vec is for Objects only. Found type {first_class}"
                    )
                for item in items:
                    item_class = item.__class__.__name__
                    if item_class == "Argument":
                        pass
                    else:
                        assert (
                            item_class == first_class
                        ), f"Expected {first_class} found {item_class}"
                return self.builder.make_move_vector(
                    type_tag, await self._resolve_arguments(items)
                )
            elif len(items) > 0:
                return self.builder.make_move_vector(type_tag, items)
        raise ValueError("make_vector requires a non-empty list")

    @versionchanged(
        version="0.17.0",
        reason="Target uses 'package_id::module::function' construct only",
    )
    @versionchanged(version="0.20.2", reason="Fixed #107")
    async def move_call(
        self,
        *,
        target: Union[str, SuiString],
        arguments: Union[list, SuiArray],
        type_arguments: Optional[Union[list, SuiArray]] = None,
    ) -> Union[bcs.Argument, list[bcs.Argument]]:
        """move_call Creates a command to invoke a move contract call. May or may not return results.

        :param target: String triple in form "package_object_id::module_name::function_name"
        :type target: Union[str, SuiString]
        :param arguments: Parameters that are passed to the move function
        :type arguments: Union[list, SuiArray]
        :param type_arguments: Optional list of type arguments for move function generics, defaults to None
        :type type_arguments: Optional[Union[list, SuiArray]], optional
        :return: The result which may or may not be used in subequent commands depending on the
            move method being called.
        :rtype: Union[bcs.Argument, list[bcs.Argument]]
        """
        assert not self._executed, "Transaction already executed"
        assert isinstance(target, (str, SuiString))
        target = target if isinstance(target, str) else target.value
        target_id = None
        module_id = None
        function_id = None
        # Standardize the input parameters
        (
            target_id,
            module_id,
            function_id,
            parameters,
            res_count,
        ) = await self._move_call_target_cache(target)
        # Standardize the arguments to list
        if arguments:
            arguments = (
                arguments if isinstance(arguments, list) else arguments.array
            )
            arguments = await self._resolve_arguments(arguments)
            for index, arg in enumerate(arguments):
                parm = parameters[index]
                if (
                    hasattr(parm, "is_mutable")
                    and parm.is_mutable
                    and isinstance(arg, tuple)
                ):
                    r_arg: bcs.ObjectArg = arg[1]
                    r_arg.value.Mutable = True
        else:
            arguments = []
        # Standardize the type_arguments to list
        if type_arguments:
            type_arguments = (
                type_arguments
                if isinstance(type_arguments, list)
                else type_arguments.array
            )
            type_arguments = [
                bcs.TypeTag.type_tag_from(x) for x in type_arguments
            ]
        else:
            type_arguments = []

        return self.builder.move_call(
            target=target_id,
            arguments=arguments,
            type_arguments=type_arguments,
            module=module_id,
            function=function_id,
            res_count=res_count,
        )

    async def _move_call(
        self,
        *,
        target: Union[str, SuiString],
        arguments: list[
            Union[bcs.Argument, tuple[bcs.BuilderArg, bcs.ObjectArg]]
        ],
        type_arguments: Optional[list[bcs.TypeTag]] = None,
    ) -> Union[bcs.Argument, list[bcs.Argument]]:
        """_move_call Internal move call when arguments and type_arguments already prepared.

        :param target: String triple in form "package_object_id::module_name::function_name"
        :type target: Union[str, SuiString]
        :param arguments: List of resolved bcs.Argument (pure) or tuple (object)
        :type arguments: list[Union[bcs.Argument, tuple[bcs.BuilderArg, bcs.ObjectArg]]]
        :param type_arguments: List of resolved type tags, defaults to None
        :type type_arguments: Optional[list[bcs.TypeTag]], optional
        :return: The result which may or may not be used in subequent commands depending on the
            move method being called.
        :rtype: Union[bcs.Argument, list[bcs.Argument]]
        """
        assert isinstance(target, (str, SuiString))
        # Standardize the input parameters
        target = target if isinstance(target, str) else target.value
        (
            target_id,
            module_id,
            function_id,
            parameters,
            res_count,
        ) = await self._move_call_target_cache(target)
        if arguments:
            for index, arg in enumerate(arguments):
                parm = parameters[index]
                if (
                    hasattr(parm, "is_mutable")
                    and parm.is_mutable
                    and isinstance(arg, tuple)
                ):
                    r_arg: bcs.ObjectArg = arg[1]
                    r_arg.value.Mutable = True

        type_arguments = (
            type_arguments if isinstance(type_arguments, list) else []
        )
        return self.builder.move_call(
            target=target_id,
            arguments=arguments,
            type_arguments=type_arguments,
            module=module_id,
            function=function_id,
            res_count=res_count,
        )

    @versionchanged(
        version="0.20.0",
        reason="Removed recipient. Transfer of UpgradeCap up to user as per Sui best practice.",
    )
    async def publish(
        self,
        *,
        project_path: str,
        with_unpublished_dependencies: bool = False,
        skip_fetch_latest_git_deps: bool = False,
        legacy_digest: bool = False,
    ) -> bcs.Argument:
        """publish Creates a publish command.

        :param project_path: path to project folder
        :type project_path: str
        :param with_unpublished_dependencies: Flag indicating inclusion of adding unpublished dependencies
            of package, defaults to False
        :type with_unpublished_dependencies: bool, optional
        :param skip_fetch_latest_git_deps: Flag indicating to skip compiliation fetch of
            package dependencies, defaults to False
        :type skip_fetch_latest_git_deps: bool, optional
        :return: A command result (UpgradeCap) that should used in a subsequent transfer commands
        :rtype: bcs.Argument
        """
        assert not self._executed, "Transaction already executed"
        modules, dependencies, _ = self._compile_source(
            project_path,
            with_unpublished_dependencies,
            skip_fetch_latest_git_deps,
            legacy_digest,
        )
        return self.builder.publish(modules, dependencies)

    async def _verify_upgrade_cap(self, upgrade_cap: str) -> ObjectRead:
        """Verify that the upgrade cap is valid."""
        resp = await self.client.get_object(upgrade_cap)
        if resp.is_ok() and not isinstance(resp.result_data, ObjectNotExist):
            upcap: ObjectRead = resp.result_data
            if not (
                upcap.object_type == self._STANDARD_UPGRADE_CAP_TYPE
                or upcap.object_type.endswith(self._UPGRADE_CAP_SUFFIX)
            ):
                raise ValueError(
                    f"{upcap.object_type} not recognized as UpgradeCap"
                )
            return upcap
        raise ValueError(f"Error in finding UpgradeCap on {upgrade_cap}")

    @versionchanged(
        version="0.17.0",
        reason="Dropped recipient as the resulting UpgradeCap goes to main signer.",
    )
    @versionchanged(
        version="0.20.0",
        reason="Added package compiled digest control as per Sui 1.0.0.",
    )
    async def publish_upgrade(
        self,
        *,
        project_path: str,
        package_id: Union[str, ObjectID],
        upgrade_cap: Union[str, ObjectID, ObjectRead],
        with_unpublished_dependencies: bool = False,
        skip_fetch_latest_git_deps: bool = False,
        legacy_digest: bool = False,
    ) -> bcs.Argument:
        """publish_upgrade Authorize, publish and commit upgrade of package.

        :param project_path: path to project folder
        :type project_path: str
        :param package_id: The current package id that is being upgraded
        :type package_id: Union[str, ObjectID]
        :param upgrade_cap: The upgrade capability object
        :type upgrade_cap: Union[str, ObjectID, ObjectRead]
        :param with_unpublished_dependencies: Flag indicating inclusion of adding unpublished dependencies
            of package, defaults to False
        :type with_unpublished_dependencies: bool, optional
        :param skip_fetch_latest_git_deps: Flag indicating to skip compiliation fetch of
            package dependencies, defaults to False
        :type skip_fetch_latest_git_deps: bool, optional
        :param legacy_digest: Flag indicating to create a digest the old way
        :type legacy_digest: bool, optional
        :return: The Result Argument
        :rtype: bcs.Argument
        """
        assert not self._executed, "Transaction already executed"
        assert isinstance(upgrade_cap, (str, ObjectID, ObjectRead))
        assert isinstance(package_id, (str, ObjectID))
        # Compile the new package
        modules, dependencies, digest = self._compile_source(
            project_path,
            with_unpublished_dependencies,
            skip_fetch_latest_git_deps,
            legacy_digest,
        )
        # Verify get/upgrade cap details
        if not isinstance(upgrade_cap, ObjectRead):
            upgrade_cap = (
                upgrade_cap
                if isinstance(upgrade_cap, str)
                else upgrade_cap.value
            )
            upgrade_cap = await self._verify_upgrade_cap(upgrade_cap)
        else:
            upgrade_cap = await self._verify_upgrade_cap(upgrade_cap.object_id)

        capability_arg = await self._resolve_arguments(
            [
                upgrade_cap,
                SuiU8(upgrade_cap.content.fields["policy"]),
                digest
                # bcs.Digest.from_bytes(compiled_package.package_digest),
            ]
        )

        # Trap the number of input_obj len:
        cap_arg = len(self.builder.inputs)
        # authorize
        auth_cmd = self.builder.authorize_upgrade(*capability_arg)
        package_id = bcs.Address.from_str(
            package_id if isinstance(package_id, str) else package_id.value
        )
        # Upgrade
        receipt = self.builder.publish_upgrade(
            modules, dependencies, package_id, auth_cmd
        )
        # Commit
        return self.builder.commit_upgrade(
            bcs.Argument("Input", cap_arg), receipt
        )

    @versionadded(version="0.20.0", reason="Support Sui 1.0.0 custom upgrades")
    async def custom_upgrade(
        self,
        *,
        project_path: str,
        package_id: Union[str, ObjectID],
        upgrade_cap: Union[str, ObjectID, ObjectRead],
        authorize_upgrade_fn: Callable[
            ["SuiTransactionAsync", ObjectRead, bcs.Digest],
            Awaitable[bcs.Argument],
        ],
        commit_upgrade_fn: Callable[
            ["SuiTransactionAsync", ObjectRead, bcs.Argument],
            Awaitable[bcs.Argument],
        ],
        with_unpublished_dependencies: bool = False,
        skip_fetch_latest_git_deps: bool = False,
        legacy_digest: bool = False,
    ) -> bcs.Argument:
        """custom_upgrade Support for custom authorization and commitments.

        :param project_path: path to project folder
        :type project_path: str
        :param package_id: The current package id that is being upgraded
        :type package_id: Union[str, ObjectID]
        :param upgrade_cap: The upgrade capability object
        :type upgrade_cap: Union[str, ObjectID, ObjectRead]
        :param authorize_upgrade_fn: Function to be called that generates custom authorization 'move_call'
        :type authorize_upgrade_fn: Callable[[&quot;SuiTransaction&quot;, ObjectRead, bcs.Digest], bcs.Argument]
        :param commit_upgrade_fn: Function to be called that generates custom commitment 'move_call'
        :type commit_upgrade_fn: Callable[[&quot;SuiTransaction&quot;, ObjectRead, bcs.Argument], bcs.Argument]
        :param with_unpublished_dependencies: Flag indicating inclusion of adding unpublished dependencies
            of package, defaults to False
        :type with_unpublished_dependencies: bool, optional
        :param skip_fetch_latest_git_deps: Flag indicating to skip compiliation fetch of
            package dependencies, defaults to False
        :type skip_fetch_latest_git_deps: bool, optional
        :param legacy_digest: Flag indicating to create a digest the old way
        :type legacy_digest: bool, optional
        :return: The Result Argument
        :rtype: bcs.Argument
        """
        assert authorize_upgrade_fn, "'authorize_upgrade_fn' is NoneType"
        assert commit_upgrade_fn, "'commit_upgrade_fn' is NoneType"
        # Compile the new package
        modules, dependencies, digest = self._compile_source(
            project_path,
            with_unpublished_dependencies,
            skip_fetch_latest_git_deps,
            legacy_digest,
        )
        # Verify get/upgrade cap details
        if not isinstance(upgrade_cap, ObjectRead):
            upgrade_cap = (
                upgrade_cap
                if isinstance(upgrade_cap, str)
                else upgrade_cap.value
            )
            upgrade_cap = await self._verify_upgrade_cap(upgrade_cap)
        else:
            upgrade_cap = await self._verify_upgrade_cap(upgrade_cap.object_id)

        upgrade_ticket = await authorize_upgrade_fn(self, upgrade_cap, digest)
        # Extrack the auth_cmd cap input
        package_id = bcs.Address.from_str(
            package_id if isinstance(package_id, str) else package_id.value
        )
        # Upgrade
        receipt = self.builder.publish_upgrade(
            modules, dependencies, package_id, upgrade_ticket
        )
        return await commit_upgrade_fn(self, upgrade_cap, receipt)

    async def stake_coin(
        self,
        *,
        coins: list[ObjectID],
        validator_address: Union[str, SuiAddress],
        amount: Optional[Union[int, SuiInteger]] = None,
    ) -> bcs.Argument:
        """stake_coin Stakes one or more coins to a specific validator.

        :param coins: One or more coins to stake.
        :type coins: list[ObjectID]
        :param validator_address: The validator to stake coins to
        :type validator_address: Union[str, SuiAddress]
        :param amount: Amount from coins to stake. If not stated, all coin will be staked, defaults to None
        :type amount: Optional[Union[int, SuiInteger]], optional
        :return: The command result.
        :rtype: bcs.Argument
        """
        assert not self._executed, "Transaction already executed"
        params: list = []
        params.append(self._SYSTEMSTATE_OBJECT)
        params.append(await self.make_move_vector(coins))
        if amount:
            amount = amount if isinstance(amount, int) else amount.value
            params.append(bcs.OptionalU64(amount))
        else:
            params.append(bcs.OptionalU64())
        params.append(
            validator_address
            if isinstance(validator_address, SuiAddress)
            else SuiAddress(validator_address)
        )
        return await self._move_call(
            target=self._STAKE_REQUEST_TARGET,
            arguments=await self._resolve_arguments(params),
        )

    async def unstake_coin(
        self, *, staked_coin: Union[str, ObjectID, StakedSui]
    ) -> bcs.Argument:
        """unstake_coin Unstakes a Staked Sui Coin.

        :param staked_coin: The coin being unstaked
        :type staked_coin: Union[str, ObjectID, StakedSui]
        :raises ValueError: If the staked coin is still in 'pending' state
        :return: The Result argument
        :rtype: bcs.Argument
        """
        assert not self._executed, "Transaction already executed"
        params: list = []
        params.append(self._SYSTEMSTATE_OBJECT)
        if isinstance(staked_coin, str):
            params.append(ObjectID(staked_coin))
        elif isinstance(staked_coin, StakedSui):
            if staked_coin.status != "Pending":
                params.append(ObjectID(staked_coin.staked_sui_id))
            else:
                raise ValueError(
                    f"Can not unstake non-activated staked coin {staked_coin}"
                )
        else:
            params.append(staked_coin)
        return await self._move_call(
            target=self._UNSTAKE_REQUEST_TARGET,
            arguments=await self._resolve_arguments(params),
        )

    @versionchanged(
        version="0.17.0", reason="Made 'amount' 'amounts' with list argument."
    )
    async def split_coin(
        self,
        *,
        coin: Union[str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument],
        amounts: list[Union[int, SuiInteger]],
    ) -> Union[bcs.Argument, list[bcs.Argument]]:
        """split_coin Creates a new coin(s) with the defined amount(s), split from the provided coin.

        Note: Returns the result that it can be used in subsequent commands. If only one amount
        is provided, a standard Result can be used as a singular argument to another command.
        But if more than 1 amount. For example  you can index to get a singular value or use the whole
        list.

        .. code-block:: python

            # Transfer all coins to one recipient
            txer = SuiTransaction(client)
            scres = txer.split_coin(coin=primary_coin, amounts=[1000000000, 1000000000])
            txer.transfer_objects(transfers=scres, recipient=client.config.active_address)

            # OR only transfer less than all
            txer.transfer_objects(transfers=[scres[0]],recipient=client.config.active_address)

        :param coin: The coin address (object id) to split from.
        :type coin: Union[str, ObjectID, ObjectRead,SuiCoinObject, bcs.Argument]
        :param amounts: The amount or list of amounts to split the coin out to
        :type amounts: list[Union[int, SuiInteger]]
        :return: A result or list of results types to use in subsequent commands
        :rtype: Union[list[bcs.Argument],bcs.Argument]
        """
        assert not self._executed, "Transaction already executed"
        assert isinstance(
            coin, (str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument)
        ), "invalid coin object type"
        amounts = amounts if isinstance(amounts, list) else [amounts]
        for amount in amounts:
            assert isinstance(amount, (int, SuiInteger))
        amounts = [
            tx_builder.PureInput.as_input(bcs.U64.encode(x))
            if isinstance(x, int)
            else x.value
            for x in amounts
        ]
        coin = (
            coin
            if isinstance(
                coin, (ObjectID, ObjectRead, SuiCoinObject, bcs.Argument)
            )
            else ObjectID(coin)
        )
        resolved = await self._resolve_arguments([coin])
        return self.builder.split_coin(resolved[0], amounts)

    @versionadded(
        version="0.16.1",
        reason="Expand Transaction builder ease of use capability.",
    )
    async def split_coin_equal(
        self,
        *,
        coin: Union[str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument],
        split_count: Union[int, SuiInteger],
        coin_type: Optional[str] = "0x2::sui::SUI",
    ) -> bcs.Argument:
        """split_coin_equal Splits a Sui coin into equal parts and transfers to transaction signer.

        :param coin: The coin to split
        :type coin: Union[str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument]
        :param split_count: The number of parts to split coin into
        :type split_count: Union[int, SuiInteger]
        :param coin_type: The coin type, defaults to a Sui coin type
        :type coin_type: Optional[str], optional
        :return: The command result. Because all splits are automagically transferred to
            signer, the result is not usable as input to subseqent commands.
        :rtype: bcs.Argument
        """
        assert not self._executed, "Transaction already executed"
        assert isinstance(
            coin, (str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument)
        ), "invalid coin object type"
        assert isinstance(
            split_count, (int, SuiInteger)
        ), "invalid amount type"
        split_count = (
            split_count if isinstance(split_count, int) else split_count.value
        )
        coin = (
            coin
            if isinstance(
                coin, (ObjectID, ObjectRead, SuiCoinObject, bcs.Argument)
            )
            else ObjectID(coin)
        )
        resolved = await self._resolve_arguments(
            [coin, tx_builder.PureInput.as_input(bcs.U64.encode(split_count))]
        )

        return await self._move_call(
            target=self._SPLIT_AND_KEEP,
            arguments=resolved,
            type_arguments=[bcs.TypeTag.type_tag_from(coin_type)],
        )

    async def split_coin_and_return(
        self,
        *,
        coin: Union[str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument],
        split_count: Union[int, SuiInteger],
        coin_type: Optional[str] = "0x2::sui::SUI",
    ) -> bcs.Argument:
        """split_coin_and_return Splits a Sui coin into equal parts and returns array of split_count-1 for user to transfer.

        :param coin: The coin to split
        :type coin: Union[str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument]
        :param split_count: The number of parts to split coin into
        :type split_count: Union[int, SuiInteger]
        :param coin_type: The coin type, defaults to a Sui coin type
        :type coin_type: Optional[str], optional
        :return: The command result which is a vector of coins split out and may be used in subsequent commands.
        :rtype: bcs.Argument
        """
        assert not self._executed, "Transaction already executed"
        assert isinstance(
            coin, (str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument)
        ), "invalid coin object type"
        assert isinstance(
            split_count, (int, SuiInteger)
        ), "invalid amount type"
        split_count = (
            split_count if isinstance(split_count, int) else split_count.value
        )
        if split_count < 2:
            raise ValueError(
                f"Split count {split_count} must be greater than 1"
            )
        coin = (
            coin
            if isinstance(
                coin, (ObjectID, ObjectRead, SuiCoinObject, bcs.Argument)
            )
            else ObjectID(coin)
        )
        resolved = await self._resolve_arguments(
            [coin, tx_builder.PureInput.as_input(bcs.U64.encode(split_count))]
        )

        # Split 1 coin into split_count total [orig, new 1, new 2]
        coin_type_tag = bcs.TypeTag.type_tag_from(coin_type)
        result_vector = await self._move_call(
            target=self._SPLIT_AND_RETURN,
            arguments=resolved,
            type_arguments=[coin_type_tag],
        )
        # Itemize the new coins
        if coin_type.count("<") == 0:
            coin_type_tag = bcs.TypeTag.type_tag_from(
                f"0x2::coin::Coin<{coin_type}>"
            )

        # We only want the new coins
        nreslist: list[bcs.Argument] = []
        for nrindex in range(split_count - 1):
            nreslist.append(
                await self._move_call(
                    target=self._VECTOR_REMOVE_INDEX,
                    arguments=[
                        result_vector,
                        tx_builder.PureInput.as_input(SuiU64(0)),
                    ],
                    type_arguments=[coin_type_tag],
                )
            )
        await self._move_call(
            target=self._VECTOR_DESTROY_EMPTY,
            arguments=[result_vector],
            type_arguments=[coin_type_tag],
        )
        return nreslist

    async def merge_coins(
        self,
        *,
        merge_to: Union[
            str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument
        ],
        merge_from: Union[
            list[
                Union[str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument]
            ],
            SuiArray,
        ],
    ) -> bcs.Argument:
        """merge_coins Merges one or more coins to a primary coin.

        :param merge_to: The coin to merge other coins to
        :type merge_to: Union[str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument]
        :param merge_from: One or more coins to merge to primary 'merge_to' coin
        :type merge_from: Union[list[Union[str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument]], SuiArray]
        :return: The command result. Can not be used as input in subsequent commands.
        :rtype: bcs.Argument
        """
        assert not self._executed, "Transaction already executed"
        assert isinstance(
            merge_to, (str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument)
        ), "Unsupported type for merge_to"
        if (
            isinstance(merge_to, bcs.Argument)
            and merge_to.enum_name == "GasCoin"
        ):
            self.signer_block._merging_to_gas()
        resolved = await self._resolve_arguments(
            [merge_to if not isinstance(merge_to, str) else ObjectID(merge_to)]
        )
        merge_to = resolved[0]
        # Depper from_coin type verification
        assert isinstance(
            merge_from, (list, SuiArray)
        ), "Unsupported merge_from collection type"
        parm_list: list = []
        merge_from = (
            merge_from if isinstance(merge_from, list) else merge_from.coins
        )
        for fcoin in merge_from:
            assert isinstance(
                fcoin, (str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument)
            ), "Unsupported entry in merge_from"
            parm_list.append(
                fcoin if not isinstance(fcoin, str) else ObjectID(fcoin)
            )
        return self.builder.merge_coins(
            merge_to, await self._resolve_arguments(parm_list)
        )

    async def public_transfer_object(
        self,
        *,
        object_to_send: Union[
            str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument
        ],
        recipient: SuiAddress,
        object_type: str,
    ) -> bcs.Argument:
        """public_transfer_object Public transfer of any object.

        :param object_to_send: Object being transferred
        :type object_to_send: Union[str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument]
        :param recipient: Address for recipient of object_to_send
        :type recipient: SuiAddress
        :param object_type: Type arguments
        :type object_type: str
        :return: Result of command which is non-reusable
        :rtype: bcs.Argument
        """
        assert not self._executed, "Transaction already executed"
        assert isinstance(
            object_to_send,
            (str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument),
        ), "invalid object type"
        assert isinstance(recipient, SuiAddress), "Invalid recipient type"
        obj_type_tag = bcs.TypeTag.type_tag_from(object_type)
        resolved_args = await self._resolve_arguments(
            [object_to_send, recipient]
        )
        return await self._move_call(
            target=self._PUBLIC_TRANSFER,
            arguments=resolved_args,
            type_arguments=[obj_type_tag],
        )

    async def transfer_objects(
        self,
        *,
        transfers: Union[
            list[
                Union[str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument]
            ],
            SuiArray,
        ],
        recipient: Union[ObjectID, SuiAddress],
    ) -> bcs.Argument:
        """transfer_objects Transfers one or more objects to a recipient.

        :param transfers: A list or SuiArray of objects to transfer
        :type transfers: Union[list[Union[str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument]], SuiArray]
        :param recipient: The recipient address that will receive the objects being transfered
        :type recipient: Union[ObjectID, SuiAddress]
        :return: The command result. Can NOT be used as input in subsequent commands.
        :rtype: bcs.Argument
        """
        assert not self._executed, "Transaction already executed"
        assert isinstance(
            transfers, (list, SuiArray, bcs.Argument)
        ), "Unsupported trasfers collection type"
        assert isinstance(
            recipient, (ObjectID, SuiAddress)
        ), "invalid recipient type"
        if isinstance(transfers, (list, SuiArray)):
            transfers = (
                transfers if isinstance(transfers, list) else transfers.array
            )
            coerced_transfers: list = []
            for txfer in transfers:
                assert isinstance(
                    txfer,
                    (str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument),
                ), "Unsupported entry in transfers"
                if isinstance(txfer, str):
                    coerced_transfers.append(ObjectID(txfer))
                else:
                    coerced_transfers.append(txfer)
            transfers = await self._resolve_arguments(coerced_transfers)
        return self.builder.transfer_objects(
            tx_builder.PureInput.as_input(recipient), transfers
        )

    async def transfer_sui(
        self,
        *,
        recipient: Union[ObjectID, SuiAddress],
        from_coin: Union[
            str, ObjectID, ObjectRead, SuiCoinObject, bcs.Argument
        ],
        amount: Optional[Union[int, SuiInteger]] = None,
    ) -> bcs.Argument:
        """transfer_sui Transfers a Sui coin object to a recipient.

        :param recipient: The recipient address that will receive the Sui coin being transfered
        :type recipient: Union[ObjectID, SuiAddress]
        :param from_coin: The Sui coin to transfer
        :type from_coin: Union[str, ObjectID, ObjectRead, SuiCoinObject]
        :param amount: Optional amount to transfer. Entire coin if not specified, defaults to None
        :type amount: Optional[Union[int, SuiInteger]], optional
        :raises ValueError: If unable to fetch the from_coin
        :raises ValueError: If from_coin is invalid
        :return: The command result. Can NOT be used as input in subsequent commands.
        :rtype: bcs.Argument
        """
        assert not self._executed, "Transaction already executed"
        assert isinstance(
            recipient, (ObjectID, SuiAddress)
        ), "invalid recipient type"
        if amount:
            assert isinstance(amount, (int, SuiInteger))
            amount = amount if isinstance(amount, int) else amount.value
            amount = tx_builder.PureInput.as_input(bcs.U64.encode(amount))
        if from_coin:
            if isinstance(from_coin, str):
                from_coin = ObjectID(from_coin)
            from_coin = await self._resolve_arguments([from_coin])
        else:
            raise ValueError(f"Invalid 'from_coin' {from_coin}")
        return self.builder.transfer_sui(
            tx_builder.PureInput.as_input(recipient), *from_coin, amount
        )
