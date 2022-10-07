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
async def test_consoleLog_textAndArgs(websocket, context_id):
    await subscribe(websocket, "log.entryAdded")

    # Send command.
    await send_JSON_command(websocket, {
        "id": 33,
        "method": "script.evaluate",
        "params": {
            "expression": "console.log("
                          "window, "
                          "undefined, "
                          "null,"
                          "42, "
                          "'text', "
                          "false, "
                          "123n, "
                          "/abc/g, "
                          "[1, 'str'], "
                          "{a:1}, "
                          "new Map([['key1', 'value1']]), "
                          "new Set(['value1']))",
            "target": {"context": context_id},
            "awaitPromise": True}})

    # Wait for responses
    event_response = await wait_for_event(websocket, "log.entryAdded")

    # Assert "log.entryAdded" event emitted.
    recursive_compare({
        "method": "log.entryAdded",
        "params": {
            # BaseLogEntry
            "level": "info",
            "source": {
                "realm": any_string,
                "context": context_id
            },
            "text": "window "
                    "undefined "
                    "null "
                    "42 "
                    "text "
                    "false "
                    "123 "
                    "/abc/g "
                    "Array(2) "
                    "Object(1) "
                    "Map(1) "
                    "Set(1)",
            "timestamp": any_timestamp,
            "stackTrace": {
                "callFrames": [{
                    "url": "",
                    "functionName": "",
                    "lineNumber": 0,
                    "columnNumber": 8}]},
            # ConsoleLogEntry
            "type": "console",
            "method": "log",
            "args": [
                {'type': 'window'},
                {'type': 'undefined'},
                {'type': 'null'},
                {'type': 'number', 'value': 42},
                {'type': 'string', 'value': 'text'},
                {'type': 'boolean', 'value': False},
                {"type": "bigint", "value": "123"},
                {"type": "regexp", "value": {"pattern": "abc", "flags": "g"}},
                {"type": "array", "value": [
                    {"type": "number", "value": 1},
                    {"type": "string", "value": "str"}]},
                {"type": "object", "value": [[
                    "a",
                    {"type": "number", "value": 1}]]},
                {"type": "map", "value": [[
                    "key1",
                    {"type": "string", "value": "value1"}]]},
                {"type": "set", "value": [
                    {"type": "string", "value": "value1"}]}
            ]}},
        event_response)


@pytest.mark.asyncio
async def test_consoleInfo_levelAndMethodAreCorrect(websocket, context_id):
    await subscribe(websocket, "log.entryAdded")
    # Send command.
    await send_JSON_command(websocket, {
        "method": "script.evaluate",
        "params": {
            "expression": "console.info('some log message')",
            "target": {"context": context_id},
            "awaitPromise": True}})

    # Wait for responses
    event_response = await wait_for_event(websocket, "log.entryAdded")

    # Assert method "info".
    assert event_response["method"] == "log.entryAdded"
    assert event_response["params"]["method"] == "info"
    assert event_response["params"]["level"] == "info"


@pytest.mark.asyncio
async def test_consoleDebug_levelAndMethodAreCorrect(websocket, context_id):
    await subscribe(websocket, "log.entryAdded")
    # Send command.
    await send_JSON_command(websocket, {
        "method": "script.evaluate",
        "params": {
            "expression": "console.debug('some log message')",
            "target": {"context": context_id},
            "awaitPromise": True}})

    # Wait for responses
    event_response = await wait_for_event(websocket, "log.entryAdded")

    # Assert method "error".
    assert event_response["method"] == "log.entryAdded"
    assert event_response["params"]["method"] == "debug"
    assert event_response["params"]["level"] == "debug"


@pytest.mark.asyncio
async def test_consoleWarn_levelAndMethodAreCorrect(websocket, context_id):
    await subscribe(websocket, "log.entryAdded")
    # Send command.
    await send_JSON_command(websocket, {
        "method": "script.evaluate",
        "params": {
            "expression": "console.warn('some log message')",
            "target": {"context": context_id},
            "awaitPromise": True}})

    # Wait for responses
    event_response = await wait_for_event(websocket, "log.entryAdded")

    # Assert method "error".
    assert event_response["method"] == "log.entryAdded"
    # Method is `console.warn`, while the level is `warning`.
    assert event_response["params"]["method"] == "warn"
    assert event_response["params"]["level"] == "warning"


@pytest.mark.asyncio
async def test_consoleError_levelAndMethodAreCorrect(websocket, context_id):
    await subscribe(websocket, "log.entryAdded")
    # Send command.
    await send_JSON_command(websocket, {
        "method": "script.evaluate",
        "params": {
            "expression": "console.error('some log message')",
            "target": {"context": context_id},
            "awaitPromise": True}})

    # Wait for responses
    event_response = await wait_for_event(websocket, "log.entryAdded")

    # Assert method "error".
    assert event_response["method"] == "log.entryAdded"
    assert event_response["params"]["method"] == "error"
    assert event_response["params"]["level"] == "error"


@pytest.mark.asyncio
async def test_consoleLog_logEntryAddedFormatOutput(websocket, context_id):
    await subscribe(websocket, "log.entryAdded")
    format_string = "format specifier, string: %s, integer: %d, " \
                    "negative: %i, float: %f, %o, %O, %c EOL"
    string_arg = "'SOME_STRING'"
    number_arg = "1"
    negative_number_arg = "-2"
    float_arg = "1.234"
    obj_arg = "{id: 1, 'font-size': '20px'}"

    expected_text = 'format specifier, string: SOME_STRING, integer: 1, ' \
                    'negative: -2, float: 1.234, ' \
                    '{\"id\":1,\"font-size\":\"20px\"}, ' \
                    '{\"id\":1,\"font-size\":\"20px\"}, ' \
                    '{\"id\":1,\"font-size\":\"20px\"} EOL'

    # Send command.
    await send_JSON_command(websocket, {
        "id": 55,
        "method": "script.evaluate",
        "params": {
            "expression": f"console.log('"
                          f"{format_string}', "
                          f"{string_arg}, "
                          f"{number_arg}, "
                          f"{negative_number_arg}, "
                          f"{float_arg}, "
                          f"{obj_arg}, "
                          f"{obj_arg}, "
                          f"{obj_arg})",
            "target": {"context": context_id},
            "awaitPromise": True}})

    # Wait for responses
    response = await wait_for_event(websocket, "log.entryAdded")

    assert response["params"]["text"] == expected_text


@pytest.mark.asyncio
async def test_exceptionThrown_logEntryAddedEventEmitted(websocket, context_id):
    await subscribe(websocket, "log.entryAdded")
    # Send command.
    command = {
        "id": 14,
        "method": "browsingContext.navigate",
        "params": {
            "url": "data:text/html,<script>throw new Error('some error')</script>",
            "wait": "interactive",
            "context": context_id}}
    await send_JSON_command(websocket, command)

    # Wait for responses
    event_response = await wait_for_event(websocket, "log.entryAdded")

    # Assert "log.entryAdded" event emitted.
    recursive_compare(
        {
            "method": "log.entryAdded",
            "params": {
                # BaseLogEntry
                "level": "error",
                "source": {
                    "realm": any_string,
                    "context": context_id
                },
                "text": "Error: some error",
                "timestamp": any_timestamp,
                "stackTrace": {
                    "callFrames": [{
                        "url": "",
                        "functionName": "",
                        "lineNumber": 0,
                        "columnNumber": 14}]},
                # ConsoleLogEntry
                "type": "javascript"}},
        event_response)