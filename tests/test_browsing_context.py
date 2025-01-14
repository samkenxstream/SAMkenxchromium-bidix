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

import pytest
from anys import ANY_DICT, ANY_STR
from test_helpers import (ANY_TIMESTAMP, AnyExtending, execute_command,
                          get_tree, goto_url, read_JSON_message,
                          send_JSON_command, subscribe, wait_for_event)


@pytest.mark.asyncio
async def test_browsingContext_subscribeToAllBrowsingContextEvents_eventReceived(
        websocket):
    await subscribe(websocket, "browsingContext")

    await send_JSON_command(websocket, {
        "method": "browsingContext.create",
        "params": {
            "type": "tab"
        }
    })

    await wait_for_event(websocket, "browsingContext.domContentLoaded")


@pytest.mark.asyncio
async def test_browsingContext_noInitialLoadEvents(websocket, html):
    # Due to the nature, the test does not always fail, even if the
    # implementation does not guarantee the initial context to be fully loaded.
    # The test asserts there was no initial "browsingContext.load" emitted
    # during the following steps:
    # 1. Subscribe for the "browsingContext.load" event.
    # 2. Get the currently open context.
    # 3. Navigate to some url.
    # 4. Verify the new page is loaded.

    url = html("<h2>test</h2>")

    await send_JSON_command(
        websocket, {
            "id": 1,
            "method": "session.subscribe",
            "params": {
                "events": ["browsingContext.load"]
            }
        })

    resp = await read_JSON_message(websocket)
    assert resp["id"] == 1

    await send_JSON_command(websocket, {
        "id": 2,
        "method": "browsingContext.getTree",
        "params": {}
    })

    resp = await read_JSON_message(websocket)
    assert resp[
        "id"] == 2, "The message should be result of command `browsingContext.getTree` with `id`: 2"
    context_id = resp["result"]["contexts"][0]["context"]

    await send_JSON_command(
        websocket, {
            "id": 3,
            "method": "browsingContext.navigate",
            "params": {
                "url": url,
                "wait": "none",
                "context": context_id
            }
        })

    resp = await read_JSON_message(websocket)
    assert resp["id"] == 3
    navigation = resp["result"]["navigation"]

    # Wait for the navigated page to be loaded.
    resp = await read_JSON_message(websocket)
    assert {
        'method': 'browsingContext.load',
        'params': {
            'context': context_id,
            'navigation': navigation,
            'timestamp': ANY_TIMESTAMP,
            'url': url
        }
    } == resp


@pytest.mark.asyncio
async def test_browsingContext_getTree_contextReturned(websocket, context_id):
    result = await get_tree(websocket)

    assert result == {
        "contexts": [{
            "context": context_id,
            "children": [],
            "parent": None,
            "url": "about:blank"
        }]
    }


@pytest.mark.asyncio
async def test_browsingContext_getTreeWithRoot_contextReturned(
        websocket, context_id):
    result = await execute_command(websocket, {
        "method": "browsingContext.create",
        "params": {
            "type": "tab"
        }
    })
    new_context_id = result["context"]

    result = await get_tree(websocket)

    assert len(result['contexts']) == 2

    result = await get_tree(websocket, new_context_id)

    assert result == {
        "contexts": [{
            "context": new_context_id,
            "parent": None,
            "url": "about:blank",
            "children": []
        }]
    }


@pytest.mark.asyncio
async def test_navigateToPageWithHash_contextInfoUpdated(
        websocket, context_id, html):
    url = html("<h2>test</h2>")
    url_with_hash_1 = url + "#1"

    # Initial navigation.
    await goto_url(websocket, context_id, url_with_hash_1, "complete")

    result = await get_tree(websocket)

    assert result == {
        "contexts": [{
            "context": context_id,
            "children": [],
            "parent": None,
            "url": url_with_hash_1
        }]
    }


@pytest.mark.asyncio
async def test_browsingContext_addAndRemoveNestedContext_contextAddedAndRemoved(
        websocket, context_id, url_cross_origin, html, iframe):
    page_with_nested_iframe = html(iframe(url_cross_origin))
    await goto_url(websocket, context_id, page_with_nested_iframe, "complete")

    result = await get_tree(websocket)

    assert {
        "contexts": [{
            "context": context_id,
            "children": [{
                "context": ANY_STR,
                "url": url_cross_origin,
                "children": []
            }],
            "parent": None,
            "url": page_with_nested_iframe
        }]
    } == result

    # Remove nested iframe.
    await execute_command(
        websocket, {
            "method": "script.evaluate",
            "params": {
                "expression": "document.querySelector('iframe').remove()",
                "awaitPromise": True,
                "target": {
                    "context": context_id,
                }
            }
        })

    result = await get_tree(websocket)

    assert {
        "contexts": [{
            "context": context_id,
            "children": [],
            "parent": None,
            "url": page_with_nested_iframe
        }]
    } == result


# TODO: make offline.
@pytest.mark.asyncio
async def test_browsingContext_afterNavigation_getTreeWithNestedCrossOriginContexts_contextsReturned(
        websocket, context_id, html, iframe):
    nested_iframe = 'https://example.com/'
    another_nested_iframe = 'https://example.org/'
    page_with_nested_iframe = html(iframe(nested_iframe))
    another_page_with_nested_iframe = html(iframe(another_nested_iframe))

    await goto_url(websocket, context_id, page_with_nested_iframe, "complete")
    await goto_url(websocket, context_id, another_page_with_nested_iframe,
                   "complete")

    result = await get_tree(websocket)

    assert {
        "contexts": [{
            "context": context_id,
            "children": [{
                "context": ANY_STR,
                "url": another_nested_iframe,
                "children": []
            }],
            "parent": None,
            "url": another_page_with_nested_iframe
        }]
    } == result


@pytest.mark.asyncio
async def test_browsingContext_afterNavigation_getTreeWithNestedContexts_contextsReturned(
        websocket, context_id, html, iframe):
    nested_iframe = html('<h2>IFRAME</h2>')
    another_nested_iframe = html('<h2>ANOTHER_IFRAME</h2>')
    page_with_nested_iframe = html('<h1>MAIN_PAGE</h1>' +
                                   iframe(nested_iframe))
    another_page_with_nested_iframe = html('<h1>ANOTHER_MAIN_PAGE</h1>' +
                                           iframe(another_nested_iframe))

    await goto_url(websocket, context_id, page_with_nested_iframe, "complete")

    result = await get_tree(websocket)

    assert {
        "contexts": [{
            "context": context_id,
            "children": [{
                "context": ANY_STR,
                "url": nested_iframe,
                "children": []
            }],
            "parent": None,
            "url": page_with_nested_iframe
        }]
    } == result

    await goto_url(websocket, context_id, another_page_with_nested_iframe,
                   "complete")

    result = await get_tree(websocket)
    assert {
        "contexts": [{
            "context": context_id,
            "children": [{
                "context": ANY_STR,
                "url": another_nested_iframe,
                "children": []
            }],
            "parent": None,
            "url": another_page_with_nested_iframe
        }]
    } == result


@pytest.mark.asyncio
async def test_browsingContext_create_eventContextCreatedEmitted(
        websocket, context_id):
    await subscribe(websocket, [
        "browsingContext.contextCreated", "browsingContext.domContentLoaded",
        "browsingContext.load"
    ])

    await send_JSON_command(websocket, {
        "id": 9,
        "method": "browsingContext.create",
        "params": {
            "type": "tab"
        }
    })

    # Read event messages. The order can vary in headless and headful modes, so
    # sort is needed:
    # * `browsingContext.contextCreated` event.
    # * `browsingContext.domContentLoaded` event.
    # * `browsingContext.load` event.
    messages = [
        await read_JSON_message(websocket), await read_JSON_message(websocket),
        await read_JSON_message(websocket)
    ]

    messages.sort(key=lambda x: x["method"] if "method" in x else "")
    [context_created_event, dom_content_loaded_event, load_event] = messages

    # Read the `browsingContext.create` command result. It should be sent after
    # all the loading events.
    command_result = await read_JSON_message(websocket)

    new_context_id = command_result['result']['context']

    # Assert command done.
    assert command_result == {"id": 9, "result": {'context': new_context_id}}

    # Assert "browsingContext.contextCreated" event emitted.
    assert {
        "method": "browsingContext.contextCreated",
        "params": {
            "context": new_context_id,
            "url": "about:blank",
            "children": None,
            "parent": None
        }
    } == context_created_event

    # Assert "browsingContext.domContentLoaded" event emitted.
    assert {
        "method": "browsingContext.domContentLoaded",
        "params": {
            "context": new_context_id,
            "navigation": ANY_STR,
            "timestamp": ANY_TIMESTAMP,
            "url": "about:blank"
        }
    } == dom_content_loaded_event

    # Assert "browsingContext.load" event emitted.
    assert {
        "method": "browsingContext.load",
        "params": {
            "context": new_context_id,
            "navigation": ANY_STR,
            "timestamp": ANY_TIMESTAMP,
            "url": "about:blank"
        }
    } == load_event


@pytest.mark.asyncio
async def test_browsingContext_createWithNestedSameOriginContexts_eventContextCreatedEmitted(
        websocket, context_id, html, iframe):
    nested_iframe = html('<h1>PAGE_WITHOUT_CHILD_IFRAMES</h1>')
    intermediate_page = html('<h1>PAGE_WITH_1_CHILD_IFRAME</h1>' +
                             iframe(nested_iframe.replace('"', '&quot;')))
    top_level_page = html('<h1>PAGE_WITH_2_CHILD_IFRAMES</h1>' +
                          iframe(intermediate_page.replace('"', '&quot;')))

    await subscribe(websocket, ["browsingContext.contextCreated"])

    await send_JSON_command(
        websocket, {
            "method": "browsingContext.navigate",
            "params": {
                "url": top_level_page,
                "wait": "complete",
                "context": context_id
            }
        })

    events = []
    while len(events) < 2:
        resp = await read_JSON_message(websocket)
        if "method" in resp and resp[
                "method"] == "browsingContext.contextCreated":
            events.append(resp)

    tree = await get_tree(websocket)

    assert {
        "contexts": [{
            "context": ANY_STR,
            "parent": None,
            "url": top_level_page,
            "children": [
                {
                    "context": ANY_STR,
                    # It's not guaranteed the nested page is already loaded.
                    "url": ANY_STR,
                    "children": [{
                        "context": ANY_STR,
                        # It's not guaranteed the nested page is already loaded.
                        "url": ANY_STR,
                        "children": []
                    }]
                },
            ]
        }]
    } == tree

    intermediate_page_context_id = tree["contexts"][0]["children"][0][
        "context"]
    nested_iframe_context_id = \
        tree["contexts"][0]["children"][0]["children"][0]["context"]
    assert events[0] == {
        "method": "browsingContext.contextCreated",
        "params": {
            'context': intermediate_page_context_id,
            'parent': context_id,
            'children': None,
            'url': 'about:blank'
        }
    }

    assert events[1] == {
        "method": "browsingContext.contextCreated",
        "params": {
            'context': nested_iframe_context_id,
            'parent': intermediate_page_context_id,
            'children': None,
            'url': 'about:blank'
        }
    }


@pytest.mark.asyncio
async def test_browsingContext_close_browsingContext_closed(
        websocket, context_id):
    await subscribe(websocket, ["browsingContext.contextDestroyed"])

    await send_JSON_command(
        websocket, {
            "id": 12,
            "method": "browsingContext.close",
            "params": {
                "context": context_id
            }
        })

    # Assert "browsingContext.contextCreated" event emitted.
    resp = await read_JSON_message(websocket)
    assert resp == {
        "method": "browsingContext.contextDestroyed",
        "params": {
            "context": context_id,
            "parent": None,
            "url": "about:blank",
            "children": None
        }
    }

    # Assert command done.
    resp = await read_JSON_message(websocket)
    assert resp == {"id": 12, "result": {}}

    result = await get_tree(websocket)

    # Assert context is closed.
    assert result == {'contexts': []}


@pytest.mark.asyncio
async def test_browsingContext_navigateWaitNone_navigated(
        websocket, context_id, html):
    await subscribe(
        websocket,
        ["browsingContext.domContentLoaded", "browsingContext.load"])

    await send_JSON_command(
        websocket, {
            "id": 13,
            "method": "browsingContext.navigate",
            "params": {
                "url": html("<h2>test</h2>"),
                "wait": "none",
                "context": context_id
            }
        })

    # Assert command done.
    resp = await read_JSON_message(websocket)
    navigation_id = resp["result"]["navigation"]
    assert resp == {
        "id": 13,
        "result": {
            "navigation": navigation_id,
            "url": html("<h2>test</h2>")
        }
    }

    # Wait for `browsingContext.load` event.
    resp = await read_JSON_message(websocket)
    assert resp == {
        "method": "browsingContext.load",
        "params": {
            "context": context_id,
            "navigation": navigation_id,
            "timestamp": ANY_TIMESTAMP,
            "url": html("<h2>test</h2>")
        }
    }

    # Wait for `browsingContext.domContentLoaded` event.
    resp = await read_JSON_message(websocket)
    assert resp == {
        "method": "browsingContext.domContentLoaded",
        "params": {
            "context": context_id,
            "navigation": navigation_id,
            "timestamp": ANY_TIMESTAMP,
            "url": html("<h2>test</h2>")
        }
    }


@pytest.mark.asyncio
async def test_browsingContext_navigateWaitInteractive_navigated(
        websocket, context_id, html):
    await subscribe(
        websocket,
        ["browsingContext.domContentLoaded", "browsingContext.load"])

    await send_JSON_command(
        websocket, {
            "id": 14,
            "method": "browsingContext.navigate",
            "params": {
                "url": html("<h2>test</h2>"),
                "wait": "interactive",
                "context": context_id
            }
        })

    # Wait for `browsingContext.load` event.
    resp = await read_JSON_message(websocket)
    navigation_id = resp["params"]["navigation"]
    assert resp == {
        "method": "browsingContext.load",
        "params": {
            "context": context_id,
            "navigation": navigation_id,
            "timestamp": ANY_TIMESTAMP,
            "url": html("<h2>test</h2>")
        }
    }

    # Wait for `browsingContext.domContentLoaded` event.
    resp = await read_JSON_message(websocket)
    assert resp == {
        "method": "browsingContext.domContentLoaded",
        "params": {
            "context": context_id,
            "navigation": navigation_id,
            "timestamp": ANY_TIMESTAMP,
            "url": html("<h2>test</h2>"),
        }
    }

    # Assert command done.
    resp = await read_JSON_message(websocket)
    assert resp == {
        "id": 14,
        "result": {
            "navigation": navigation_id,
            "url": html("<h2>test</h2>")
        }
    }


@pytest.mark.asyncio
async def test_browsingContext_navigateWaitComplete_navigated(
        websocket, context_id, html):
    await subscribe(
        websocket,
        ["browsingContext.domContentLoaded", "browsingContext.load"])

    await send_JSON_command(
        websocket, {
            "id": 15,
            "method": "browsingContext.navigate",
            "params": {
                "url": html("<h2>test</h2>"),
                "wait": "complete",
                "context": context_id
            }
        })

    # Wait for `browsingContext.load` event.
    resp = await read_JSON_message(websocket)
    navigation_id = resp["params"]["navigation"]
    assert resp == {
        "method": "browsingContext.load",
        "params": {
            "context": context_id,
            "navigation": navigation_id,
            "timestamp": ANY_TIMESTAMP,
            "url": html("<h2>test</h2>")
        }
    }

    # Assert command done.
    resp = await read_JSON_message(websocket)
    assert resp == {
        "id": 15,
        "result": {
            "navigation": navigation_id,
            "url": html("<h2>test</h2>")
        }
    }

    # Wait for `browsingContext.domContentLoaded` event.
    resp = await read_JSON_message(websocket)
    assert resp == {
        "method": "browsingContext.domContentLoaded",
        "params": {
            "context": context_id,
            "navigation": navigation_id,
            "timestamp": ANY_TIMESTAMP,
            "url": html("<h2>test</h2>")
        }
    }


@pytest.mark.asyncio
async def test_browsingContext_navigateSameDocumentNavigation_waitNone_navigated(
        websocket, context_id, html):
    url = html("<h2>test</h2>")
    url_with_hash_1 = url + "#1"
    url_with_hash_2 = url + "#2"

    # Initial navigation.
    await goto_url(websocket, context_id, url, "complete")

    resp = await goto_url(websocket, context_id, url_with_hash_1, "none")
    assert resp == {'navigation': None, 'url': url_with_hash_1}

    resp = await goto_url(websocket, context_id, url_with_hash_2, "none")
    assert resp == {'navigation': None, 'url': url_with_hash_2}


@pytest.mark.asyncio
async def test_browsingContext_navigateSameDocumentNavigation_waitInteractive_navigated(
        websocket, context_id, html):
    url = html("<h2>test</h2>")
    url_with_hash_1 = url + "#1"
    url_with_hash_2 = url + "#2"

    # Initial navigation.
    await goto_url(websocket, context_id, url, "complete")

    resp = await goto_url(websocket, context_id, url_with_hash_1,
                          "interactive")
    assert resp == {'navigation': None, 'url': url_with_hash_1}

    result = await get_tree(websocket, context_id)

    assert {
        "contexts": [{
            "context": context_id,
            "children": [],
            "parent": None,
            "url": url_with_hash_1
        }]
    } == result

    resp = await goto_url(websocket, context_id, url_with_hash_2,
                          "interactive")
    assert resp == {'navigation': None, 'url': url_with_hash_2}

    result = await get_tree(websocket, context_id)

    assert {
        "contexts": [{
            "context": context_id,
            "children": [],
            "parent": None,
            "url": url_with_hash_2
        }]
    } == result


@pytest.mark.asyncio
async def test_browsingContext_navigateSameDocumentNavigation_waitComplete_navigated(
        websocket, context_id, html):
    url = html("<h2>test</h2>")
    url_with_hash_1 = url + "#1"
    url_with_hash_2 = url + "#2"

    # Initial navigation.
    await goto_url(websocket, context_id, url, "complete")

    resp = await goto_url(websocket, context_id, url_with_hash_1, "complete")
    assert resp == {'navigation': None, 'url': url_with_hash_1}

    result = await get_tree(websocket, context_id)

    assert {
        "contexts": [{
            "context": context_id,
            "children": [],
            "parent": None,
            "url": url_with_hash_1
        }]
    } == result

    resp = await goto_url(websocket, context_id, url_with_hash_2, "complete")
    assert resp == {'navigation': None, 'url': url_with_hash_2}

    result = await get_tree(websocket, context_id)

    assert {
        "contexts": [{
            "context": context_id,
            "children": [],
            "parent": None,
            "url": url_with_hash_2
        }]
    } == result


@pytest.mark.asyncio
async def test_browsingContext_reload_waitNone(websocket, context_id, html):
    url = html()

    await subscribe(
        websocket,
        ["browsingContext.domContentLoaded", "browsingContext.load"])

    await goto_url(websocket, context_id, url)

    await send_JSON_command(
        websocket, {
            "method": "browsingContext.reload",
            "params": {
                "context": context_id,
                "wait": "none",
            }
        })

    # Assert command done.
    response = await read_JSON_message(websocket)
    assert response["result"] == {}

    # Wait for `browsingContext.load` event.
    response = await read_JSON_message(websocket)
    assert response == {
        "method": "browsingContext.load",
        "params": {
            "context": context_id,
            "navigation": ANY_STR,
            "timestamp": ANY_TIMESTAMP,
            "url": url,
        }
    }

    # Wait for `browsingContext.domContentLoaded` event.
    response = await read_JSON_message(websocket)
    assert response == {
        "method": "browsingContext.domContentLoaded",
        "params": {
            "context": context_id,
            "navigation": ANY_STR,
            "timestamp": ANY_TIMESTAMP,
            "url": url,
        }
    }


@pytest.mark.asyncio
async def test_browsingContext_reload_waitInteractive(websocket, context_id,
                                                      html):
    url = html()

    await subscribe(
        websocket,
        ["browsingContext.domContentLoaded", "browsingContext.load"])

    await goto_url(websocket, context_id, url)

    await send_JSON_command(
        websocket, {
            "method": "browsingContext.reload",
            "params": {
                "context": context_id,
                "wait": "interactive",
            }
        })

    # Wait for `browsingContext.load` event.
    response = await read_JSON_message(websocket)
    assert response == {
        "method": "browsingContext.load",
        "params": {
            "context": context_id,
            "navigation": ANY_STR,
            "timestamp": ANY_TIMESTAMP,
            "url": url,
        }
    }

    # Wait for `browsingContext.domContentLoaded` event.
    response = await read_JSON_message(websocket)
    assert response == {
        "method": "browsingContext.domContentLoaded",
        "params": {
            "context": context_id,
            "navigation": ANY_STR,
            "timestamp": ANY_TIMESTAMP,
            "url": url,
        }
    }

    # Assert command done.
    response = await read_JSON_message(websocket)
    assert response["result"] == {}


@pytest.mark.asyncio
async def test_browsingContext_reload_waitComplete(websocket, context_id,
                                                   html):
    url = html()

    await subscribe(
        websocket,
        ["browsingContext.domContentLoaded", "browsingContext.load"])

    await goto_url(websocket, context_id, url)

    await send_JSON_command(
        websocket, {
            "method": "browsingContext.reload",
            "params": {
                "context": context_id,
                "wait": "complete",
            }
        })

    # Wait for `browsingContext.load` event.
    response = await read_JSON_message(websocket)
    assert response == {
        "method": "browsingContext.load",
        "params": {
            "context": context_id,
            "navigation": ANY_STR,
            "timestamp": ANY_TIMESTAMP,
            "url": url,
        }
    }

    # Assert command done.
    response = await read_JSON_message(websocket)
    assert response["result"] == {}

    # Wait for `browsingContext.domContentLoaded` event.
    response = await read_JSON_message(websocket)
    assert response == {
        "method": "browsingContext.domContentLoaded",
        "params": {
            "context": context_id,
            "navigation": ANY_STR,
            "timestamp": ANY_TIMESTAMP,
            "url": url,
        }
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("ignoreCache", [True, False])
async def test_browsingContext_ignoreCache(websocket, context_id, ignoreCache):
    if not ignoreCache:
        pytest.xfail(
            reason="TODO: Find a way to distinguish cache hits from misses.")

    url = "https://example.com/"

    await subscribe(websocket, [
        "network.beforeRequestSent",
        "network.responseCompleted",
    ])

    await goto_url(websocket, context_id, url)

    id = await send_JSON_command(
        websocket, {
            "method": "browsingContext.reload",
            "params": {
                "context": context_id,
                "ignoreCache": ignoreCache,
                "wait": "complete",
            }
        })

    response = await read_JSON_message(websocket)
    assert response == {
        "method": "network.beforeRequestSent",
        "params": {
            "context": context_id,
            "initiator": ANY_DICT,
            "navigation": ANY_STR,
            "redirectCount": 0,
            "request": ANY_DICT,
            "timestamp": ANY_TIMESTAMP,
        },
    }

    response = await read_JSON_message(websocket)
    assert response == {
        "method": "network.responseCompleted",
        "params": {
            "context": context_id,
            "navigation": ANY_STR,
            "redirectCount": 0,
            "request": ANY_DICT,
            "response": AnyExtending({"fromCache": not ignoreCache}),
            "timestamp": ANY_TIMESTAMP,
        },
    }

    # Assert command done.
    response = await read_JSON_message(websocket)
    assert response == {
        "id": id,
        "result": {},
    }
