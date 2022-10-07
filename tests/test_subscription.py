# Copyright 2021 Google LLC.
# Copyright (c) Microsoft Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from _helpers import *


@pytest.mark.asyncio
async def test_subscribeWithoutContext_subscribesToEventsInAllContexts(
      websocket, context_id):
    result = await execute_command(websocket, {
        "method": "session.subscribe",
        "params": {
            "events": [
                "browsingContext.load"]}})
    assert result == {}

    # Navigate to some page.
    await send_JSON_command(websocket, {
        "id": get_next_command_id(),
        "method": "browsingContext.navigate",
        "params": {
            "url": "data:text/html,<h2>test</h2>",
            "wait": "complete",
            "context": context_id}})

    # Wait for `browsingContext.load` event.
    resp = await read_JSON_message(websocket)
    assert resp["method"] == "browsingContext.load"
    assert resp["params"]["context"] == context_id


@pytest.mark.asyncio
async def test_subscribeWithContext_subscribesToEventsInGivenContext(
      websocket, context_id):
    result = await execute_command(websocket, {
        "method": "session.subscribe",
        "params": {
            "events": [
                "browsingContext.load"],
            "contexts": [
                context_id]}})
    assert result == {}

    # Navigate to some page.
    await send_JSON_command(websocket, {
        "id": get_next_command_id(),
        "method": "browsingContext.navigate",
        "params": {
            "url": "data:text/html,<h2>test</h2>",
            "wait": "complete",
            "context": context_id}})

    # Wait for `browsingContext.load` event.
    resp = await read_JSON_message(websocket)
    assert resp["method"] == "browsingContext.load"
    assert resp["params"]["context"] == context_id


@pytest.mark.asyncio
async def test_subscribeWithContext_doesNotSubscribeToEventsInAnotherContexts(
      websocket, context_id):
    # 1. Get 2 contexts.
    # 2. Subscribe to event `browsingContext.load` on the first one.
    # 3. Navigate waiting complete loading in both contexts.
    # 4. Verify `browsingContext.load` emitted only for the first context.

    first_context_id = context_id

    result = await execute_command(websocket, {
        "method": "browsingContext.create",
        "params": {"type": "tab"}})
    second_context_id = result["context"]

    await subscribe(websocket, ["browsingContext.load"], [first_context_id])

    # 3.1 Navigate first context.
    command_id_1 = get_next_command_id()
    await send_JSON_command(websocket, {
        "id": command_id_1,
        "method": "browsingContext.navigate",
        "params": {
            "url": "data:text/html,<h2>test</h2>",
            "wait": "complete",
            "context": first_context_id}})
    # 4.1 Verify `browsingContext.load` is emitted for the first context.
    resp = await read_JSON_message(websocket)
    assert resp["method"] == "browsingContext.load"
    assert resp["params"]["context"] == first_context_id

    # Verify first navigation finished.
    resp = await read_JSON_message(websocket)
    assert resp["id"] == command_id_1

    # 3.2 Navigate second context.
    command_id_2 = get_next_command_id()
    await send_JSON_command(websocket, {
        "id": command_id_2,
        "method": "browsingContext.navigate",
        "params": {
            "url": "data:text/html,<h2>test</h2>",
            "wait": "complete",
            "context": second_context_id}})

    # 4.2 Verify second navigation finished without emitting
    # `browsingContext.load`.
    resp = await read_JSON_message(websocket)
    assert resp["id"] == command_id_2


@pytest.mark.asyncio
async def test_subscribeToOneChannel_eventReceivedWithProperChannel(
      websocket, context_id):
    # Subscribe and unsubscribe in `CHANNEL_1`.
    await execute_command(websocket, {
        "method": "session.subscribe",
        "channel": "CHANNEL_1",
        "params": {
            "events": ["log.entryAdded"]}})
    await execute_command(websocket, {
        "method": "session.unsubscribe",
        "channel": "CHANNEL_1",
        "params": {
            "events": ["log.entryAdded"]}})

    # Subscribe in `CHANNEL_2`.
    await execute_command(websocket, {
        "method": "session.subscribe",
        "channel": "CHANNEL_2",
        "params": {
            "events": ["log.entryAdded"]}})

    await execute_command(websocket, {
        "method": "script.evaluate",
        "params": {
            "expression": "console.log('SOME_MESSAGE')",
            "target": {"context": context_id},
            "awaitPromise": True}})

    # Assert event received in `CHANNEL_2`.
    resp = await read_JSON_message(websocket)
    recursive_compare({
        "method": "log.entryAdded",
        "params": any_value,
        "channel": "CHANNEL_2"},
        resp)


@pytest.mark.asyncio
async def test_subscribeToMultipleChannels_eventsReceivedInProperOrder(
      websocket, context_id):
    await subscribe(websocket, "log.entryAdded", None,
                    "999_FIRST_SUBSCRIBED_CHANNEL")
    await subscribe(websocket, "log.entryAdded", context_id,
                    "000_SECOND_SUBSCRIBED_CHANNEL")
    await subscribe(websocket, "log.entryAdded", context_id,
                    "555_THIRD_SUBSCRIBED_CHANNEL")
    # Re-subscribe with specific BrowsingContext.
    await subscribe(websocket, "log.entryAdded", context_id,
                    "000_SECOND_SUBSCRIBED_CHANNEL")
    # Re-subscribe.
    await subscribe(websocket, "log.entryAdded", None,
                    "999_FIRST_SUBSCRIBED_CHANNEL")

    await execute_command(websocket, {
        "method": "session.subscribe",
        "channel": "000_SECOND_SUBSCRIBED_CHANNEL",
        "params": {
            "events": ["log.entryAdded"]}})
    # Subscribe with a context. The initial subscription should still have
    # higher priority.
    await execute_command(websocket, {
        "method": "session.subscribe",
        "channel": "999_FIRST_SUBSCRIBED_CHANNEL",
        "params": {
            "events": ["log.entryAdded"],
            "cointext": context_id
        }})

    await execute_command(websocket, {
        "method": "script.evaluate",
        "channel": "SOME_OTHER_CHANNEL",
        "params": {
            "expression": "console.log('SOME_MESSAGE')",
            "target": {"context": context_id},
            "awaitPromise": True}})

    resp = await read_JSON_message(websocket)
    recursive_compare({
        "method": "log.entryAdded",
        "channel": "999_FIRST_SUBSCRIBED_CHANNEL",
        "params": any_value},
        resp)

    resp = await read_JSON_message(websocket)
    recursive_compare({
        "method": "log.entryAdded",
        "channel": "000_SECOND_SUBSCRIBED_CHANNEL",
        "params": any_value},
        resp)

    resp = await read_JSON_message(websocket)
    recursive_compare({
        "method": "log.entryAdded",
        "channel": "555_THIRD_SUBSCRIBED_CHANNEL",
        "params": any_value},
        resp)